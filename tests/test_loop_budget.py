"""Tests for the ReAct execution budget (see ``ai.loop_budget``).

These are policy tests: no model, no tools, no session. The loop wires the
policy in; what matters here is that the decision itself is explainable and
that no configuration can produce an unbounded run.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai import loop_budget
from ai.loop_budget import (
    CONVERSA,
    FERRAMENTA_SIMPLES,
    MULTI_STEP,
    TAREFA,
    LoopDetector,
    classify_complexity,
    resolve_budget,
)


def _modo(max_iterations: int = 0) -> SimpleNamespace:
    return SimpleNamespace(id="documentos", max_iterations=max_iterations)


@pytest.fixture
def settings_agent():
    """The real settings object with a small cap, so tests stay fast.

    Defaults would be fine for correctness, but a small cap makes the clamping
    tests meaningful instead of accidentally satisfied.
    """
    agent = SimpleNamespace(
        loop_hard_cap=40,
        loop_budget_conversa=6,
        loop_budget_ferramenta_simples=14,
        loop_budget_multi_step=28,
        loop_budget_task=20,
        loop_repeat_threshold=3,
    )
    return agent


# ── Complexity classification ───────────────────────────────────


class TestClassifyComplexity:
    def test_greeting_is_a_conversation(self):
        assert classify_complexity("Oi, tudo bem?").kind == CONVERSA

    def test_empty_prompt_is_a_conversation(self):
        assert classify_complexity("   ").kind == CONVERSA

    def test_general_knowledge_with_no_tools_is_a_conversation(self):
        assert classify_complexity("O que e o teorema de Bayes?").kind == CONVERSA

    def test_single_tool_request_is_a_simple_tool_task(self):
        resultado = classify_complexity("Quanto tem no estoque?", ferramentas=["consultar_estoque"])
        assert resultado.kind == FERRAMENTA_SIMPLES

    def test_sequence_marker_is_multi_step(self):
        assert classify_complexity("Leia o documento e depois salve o resumo").kind == MULTI_STEP

    def test_two_distinct_actions_are_multi_step_without_a_marker(self):
        assert classify_complexity("Resuma o relatorio e salve em disco").kind == MULTI_STEP

    def test_reading_twice_is_not_multi_step(self):
        # Two verbs from the same group are one action repeated, not two steps.
        assert (
            classify_complexity(
                "consulte o estoque e veja o saldo", ferramentas=["consultar_estoque"]
            ).kind
            == FERRAMENTA_SIMPLES
        )

    def test_reading_two_documents_is_multi_step(self):
        # ...but an explicit "e leia" is a second action and does count.
        assert (
            classify_complexity(
                "Leia o contrato e leia a planilha", ferramentas=["ler_arquivo"]
            ).kind
            == MULTI_STEP
        )

    def test_task_session_outranks_every_textual_signal(self):
        resultado = classify_complexity(
            "Oi", ferramentas=["x"] * 5, task_session=SimpleNamespace(task={})
        )
        assert resultado.kind == TAREFA

    def test_accents_and_case_do_not_change_the_class(self):
        assert classify_complexity("RESUMA o relatório e SALVE").kind == MULTI_STEP

    def test_complexity_reports_why_it_decided(self):
        assert classify_complexity("Leia, resuma e salve").signals


# ── Budget resolution ───────────────────────────────────────────


class TestResolveBudget:
    def test_conversation_gets_the_conversation_tier(self, settings_agent):
        orcamento, complexidade = resolve_budget("Oi!", settings_agent=settings_agent)
        assert complexidade.kind == CONVERSA
        assert orcamento == settings_agent.loop_budget_conversa

    def test_multi_step_gets_more_than_a_conversation(self, settings_agent):
        simples, _ = resolve_budget("Oi!", settings_agent=settings_agent)
        multi, _ = resolve_budget(
            "Leia o contrato e depois salve o resumo", settings_agent=settings_agent
        )
        assert multi > simples

    def test_mode_budget_is_authoritative_for_a_task(self, settings_agent):
        orcamento, _ = resolve_budget(
            "Qualquer coisa",
            mode=_modo(37),
            task_session=SimpleNamespace(task={}),
            settings_agent=settings_agent,
        )
        assert orcamento == 37

    def test_task_falls_back_to_the_configured_default(self, settings_agent):
        orcamento, _ = resolve_budget(
            "Qualquer coisa",
            mode=_modo(0),
            task_session=SimpleNamespace(task={}),
            settings_agent=settings_agent,
        )
        assert orcamento == settings_agent.loop_budget_task

    def test_hard_cap_overrides_a_mode_that_asks_for_more(self, settings_agent):
        orcamento, _ = resolve_budget(
            "Qualquer coisa",
            mode=_modo(99_999),
            task_session=SimpleNamespace(task={}),
            settings_agent=settings_agent,
        )
        assert orcamento == settings_agent.loop_hard_cap

    def test_hard_cap_overrides_the_multi_step_tier(self, settings_agent):
        orcamento, _ = resolve_budget(
            "Leia o contrato e depois salve o resumo", settings_agent=settings_agent
        )
        assert orcamento <= settings_agent.loop_hard_cap

    def test_budget_is_never_zero(self, settings_agent):
        orcamento, _ = resolve_budget("Oi!", settings_agent=settings_agent)
        assert orcamento >= 1

    def test_missing_mode_does_not_raise(self, settings_agent):
        orcamento, _ = resolve_budget(
            "Qualquer coisa",
            mode=None,
            task_session=SimpleNamespace(task={}),
            settings_agent=settings_agent,
        )
        assert orcamento >= 1

    def test_previous_five_iteration_leftover_is_gone(self, settings_agent):
        # The old code hardcoded 5 for every non-task turn, which truncated real
        # multi-step work rather than protecting anything.
        orcamento, _ = resolve_budget(
            "Leia o contrato e depois salve o resumo", settings_agent=settings_agent
        )
        assert orcamento > 5


# ── Loop detection ──────────────────────────────────────────────


class TestLoopDetector:
    def test_first_call_is_not_a_repetition(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        assert detector.register("ler_arquivo", {"caminho": "a.pdf"}) is None

    def test_identical_call_is_reported(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        detector.register("ler_arquivo", {"caminho": "a.pdf"})
        repeticao = detector.register("ler_arquivo", {"caminho": "a.pdf"})
        assert repeticao is not None
        assert repeticao.same_arguments
        assert repeticao.consecutive == 2

    def test_argument_order_does_not_matter(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        detector.register("buscar", {"a": 1, "b": 2})
        assert detector.register("buscar", {"b": 2, "a": 1}) is not None

    def test_different_arguments_are_not_a_repetition(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        detector.register("ler_arquivo", {"caminho": "a.pdf"})
        assert detector.register("ler_arquivo", {"caminho": "b.pdf"}) is None

    def test_different_tool_resets_the_count(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        detector.register("ler_arquivo", {"caminho": "a.pdf"})
        detector.register("ler_arquivo", {"caminho": "a.pdf"})
        detector.register("listar_documentos_rag", {})
        assert detector.register("ler_arquivo", {"caminho": "a.pdf"}) is None

    def test_revisiting_a_tool_is_not_treated_as_a_loop(self, settings_agent):
        # list -> read -> list is a sensible plan; only *consecutive* repeats
        # are a loop, otherwise oscillation would be invisible.
        detector = LoopDetector(settings_agent=settings_agent)
        detector.register("listar_documentos_rag", {})
        detector.register("ler_arquivo", {"caminho": "a.pdf"})
        assert detector.register("listar_documentos_rag", {}) is None

    def test_threshold_is_not_reached_after_a_single_repeat(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        detector.register("ler_arquivo", {"caminho": "a.pdf"})
        detector.register("ler_arquivo", {"caminho": "a.pdf"})
        assert not detector.exhausted

    def test_threshold_is_reached_after_repeated_repeats(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        for _ in range(detector.threshold):
            detector.register("ler_arquivo", {"caminho": "a.pdf"})
        assert detector.exhausted

    def test_same_error_from_different_arguments_is_flagged(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        erro = "Erro ao executar X: campo 'a' invalido"
        detector.register("salvar", {"a": 1}, erro, falhou=True)
        detector.register("salvar", {"a": 2}, erro, falhou=True)
        repeticao = detector.register("salvar", {"a": 3}, erro, falhou=True)
        assert repeticao is not None
        assert repeticao.same_error
        assert not repeticao.same_arguments

    def test_changing_error_is_not_the_same_error(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        detector.register("salvar", {"a": 1}, "Erro: campo 'a' invalido", falhou=True)
        repeticao = detector.register("salvar", {"a": 1}, "Erro: campo 'b' invalido", falhou=True)
        assert not repeticao.same_error

    def test_success_clears_a_previous_error(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        detector.register("salvar", {"a": 1}, "Erro: campo 'a' invalido", falhou=True)
        detector.register("salvar", {"a": 2}, "ok", falhou=False)
        assert detector._error is None

    def test_varying_arguments_on_the_same_error_also_exhausts(self, settings_agent):
        # A model retrying a rejected write usually nudges the arguments rather
        # than repeating them verbatim, so the signature never repeats.
        detector = LoopDetector(settings_agent=settings_agent)
        erro = "Erro ao executar salvar: campo 'a' invalido"
        for i in range(detector.threshold):
            assert not detector.exhausted or i == 0
            detector.register("salvar", {"a": i}, erro, falhou=True)
        assert detector.exhausted

    def test_unserialisable_arguments_do_not_raise(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        assert detector.register("t", {"obj": object()}) is None

    def test_nudge_names_the_tool_and_forbids_repeating(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        detector.register("ler_arquivo", {"caminho": "a.pdf"})
        repeticao = detector.register("ler_arquivo", {"caminho": "a.pdf"})
        aviso = detector.nudge(repeticao)
        assert "ler_arquivo" in aviso
        assert "nao repita" in aviso.lower() or "mude" in aviso.lower()

    def test_nudge_for_an_error_loop_asks_for_another_strategy(self, settings_agent):
        detector = LoopDetector(settings_agent=settings_agent)
        erro = "Erro ao executar salvar: campo 'a' invalido"
        for _ in range(3):
            detector.register("salvar", {"a": 1}, erro, falhou=True)
        repeticao = detector.register("salvar", {"a": 1}, erro, falhou=True)
        assert "Mude de estrategia" in detector.nudge(repeticao)


# ── Defaults must exist ─────────────────────────────────────────


def test_agent_settings_expose_every_loop_knob(settings_agent):
    for knob in (
        "loop_hard_cap",
        "loop_budget_conversa",
        "loop_budget_ferramenta_simples",
        "loop_budget_multi_step",
        "loop_budget_task",
        "loop_repeat_threshold",
    ):
        assert getattr(settings_agent, knob) is not None, knob


def test_hard_cap_is_the_largest_tier(settings_agent):
    tiers = [
        settings_agent.loop_budget_conversa,
        settings_agent.loop_budget_ferramenta_simples,
        settings_agent.loop_budget_multi_step,
        settings_agent.loop_budget_task,
    ]
    assert settings_agent.loop_hard_cap >= max(tiers)


@pytest.mark.parametrize("pergunta", ["Oi", "Leia, resuma e salve", "Quanto tem no estoque?"])
def test_resolution_never_raises_on_any_golden_shape(pergunta, settings_agent):
    orcamento, _ = resolve_budget(
        pergunta, mode=_modo(60), ferramentas=["t"], settings_agent=settings_agent
    )
    assert 1 <= orcamento <= settings_agent.loop_hard_cap


# ── Loop wiring ─────────────────────────────────────────────────


def _fake_llama(call_specs: list[dict]) -> object:
    """A llama stub that replays one scripted turn per call."""

    class FakeLlama:
        def __init__(self) -> None:
            self.turnos = 0

        def create_chat_completion(self, **kwargs):
            spec = call_specs[min(self.turnos, len(call_specs) - 1)]
            self.turnos += 1
            if spec is None:
                return iter([{"choices": [{"delta": {"content": "Resposta final"}}]}])
            return iter(
                [
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": f"call_{self.turnos}",
                                            "function": {
                                                "name": spec["name"],
                                                "arguments": spec["arguments"],
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            )

    return FakeLlama()


def _preparar_loop(
    monkeypatch, chamada: str, argumentos: str, *, max_turnos: int = 30
) -> list[int]:
    """Drive ``loop_react`` with a model that always makes the same call."""
    from ai import react

    estado = {"n": 0}

    class FakeManager:
        def route_and_invoke(self, *_a, **_k):
            estado["n"] += 1
            assert estado["n"] <= max_turnos, "o loop nao interrompeu o ciclo"
            return "gemma3-4b-q4km", _fake_llama([{"name": chamada, "arguments": argumentos}])

        def get_last_decision(self):
            return None

        def get_current_complexity(self):
            return "simple"

    monkeypatch.setattr(react, "get_multi_model_manager", lambda: FakeManager())
    monkeypatch.setattr(react, "_agenda_prompt_context", lambda: "")
    monkeypatch.setattr(
        react,
        "executar_ferramenta",
        lambda nome, args, **_k: estado.setdefault("ferramentas", []).append(nome) or "ok",
    )
    return estado


class TestLoopWiring:
    def test_a_repeating_model_is_stopped(self, monkeypatch):
        from ai import react

        _preparar_loop(monkeypatch, "informacoes_sistema", "{}")
        resposta, passos = react.loop_react({"pergunta": "Oi, tudo bem?"})

        assert "ciclo repetido" in resposta
        assert any(p.tipo == "resposta" for p in passos)

    def test_stop_happens_long_before_the_hard_cap(self, monkeypatch):
        # The point of loop detection is that the cap is not the thing that
        # ends a stuck run; 5 model calls already exceeds the old budget.
        estado = _preparar_loop(monkeypatch, "informacoes_sistema", "{}", max_turnos=12)
        react_loop = monkeypatch
        from ai import react

        react.loop_react({"pergunta": "Oi, tudo bem?"})
        assert estado["n"] <= 12

    def test_the_stop_is_logged_for_observability(self, monkeypatch, caplog):
        import logging

        from ai import react

        _preparar_loop(monkeypatch, "informacoes_sistema", "{}")
        with caplog.at_level(logging.INFO, logger="ai.react"):
            react.loop_react({"pergunta": "Oi, tudo bem?"})
        eventos = {r.getMessage() for r in caplog.records}
        assert any("loop_interrompido" in e for e in eventos)
        assert any("loop_orcamento" in e for e in eventos)

    def test_a_multi_step_request_gets_more_turns_than_a_greeting(self, monkeypatch):
        from ai import react

        contagem = {"orcamento": None}
        original = react.loop_budget.resolve_budget

        def capturing(pergunta, **kwargs):
            orcamento, complexidade = original(pergunta, **kwargs)
            contagem[complexidade.kind] = orcamento
            return orcamento, complexidade

        monkeypatch.setattr(react.loop_budget, "resolve_budget", capturing)
        _preparar_loop(monkeypatch, "informacoes_sistema", "{}")
        react.loop_react({"pergunta": "Oi, tudo bem?"})

        assert contagem["conversa"] is not None
        assert contagem["conversa"] < 5 + 10  # a real tier, not the old leftover

    def test_task_session_status_finishes_the_turn_immediately(self, monkeypatch):
        from ai import react

        estado = {"n": 0}

        class FakeManager:
            def route_and_invoke(self, *_a, **_k):
                estado["n"] += 1
                return "gemma3-4b-q4km", _fake_llama(
                    [{"name": "informacoes_sistema", "arguments": "{}"}]
                )

            def get_last_decision(self):
                return None

            def get_current_complexity(self):
                return "simple"

        class SessaoEncerrada:
            task = {"status": "completed", "result": "ja pronto", "messages": [], "prompt": {}}
            output = ""

            def before_model(self, *_a):
                return None

            def check(self):
                return None

            def save(self):
                return None

        monkeypatch.setattr(react, "get_multi_model_manager", lambda: FakeManager())
        monkeypatch.setattr(react, "_agenda_prompt_context", lambda: "")
        monkeypatch.setattr(react, "executar_ferramenta", lambda *_a, **_k: "ok")

        react.loop_react(
            {"pergunta": "Leia, resuma e salve o relatorio"}, task_session=SessaoEncerrada()
        )
        # Early stop means only the initial model selection happens (1 call),
        # not the full budget which would be 60+ generation calls.
        assert estado["n"] == 1
