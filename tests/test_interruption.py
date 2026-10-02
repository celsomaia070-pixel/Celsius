"""Tests for cooperative interruption of assistant responses."""

from ai.interruption import INTERRUPTED_MARKER, marcar_interrompida


class TestMarcarInterrompida:
    def test_adds_marker_to_partial_text(self):
        texto = marcar_interrompida("Primeira parte da resposta")
        assert texto.startswith("Primeira parte da resposta")
        assert texto.endswith(INTERRUPTED_MARKER)

    def test_empty_text_becomes_marker_only(self):
        assert marcar_interrompida("   ") == INTERRUPTED_MARKER

    def test_does_not_duplicate_marker(self):
        once = marcar_interrompida("Texto")
        assert marcar_interrompida(once) == once


def test_loop_react_stops_after_first_chunk(monkeypatch):
    import ai.react

    class FakeLlama:
        def create_chat_completion(self, **_kwargs):
            return iter(
                [
                    {"choices": [{"delta": {"content": "Primeira parte "}}]},
                    {"choices": [{"delta": {"content": "segunda parte"}}]},
                    {"choices": [{"delta": {"content": "terceira parte"}}]},
                ]
            )

    class FakeManager:
        def route_and_invoke(self, *_args, **_kwargs):
            return "gemma3-4b-q4km", FakeLlama()

        def get_current_complexity(self):
            return "simple"

        def get_last_decision(self):
            return None

    monkeypatch.setattr(ai.react, "get_multi_model_manager", lambda: FakeManager())
    monkeypatch.setattr(ai.react, "_agenda_prompt_context", lambda: "")

    state = {"cancel": False}

    def on_chunk(_text):
        state["cancel"] = True

    response, _steps = ai.react.loop_react(
        {
            "pergunta": "Resuma o documento",
            "documento": "conteudo local",
            "nome_documento": "nota.txt",
            "memorias_relevantes": [],
        },
        fn_chunk=on_chunk,
        should_cancel=lambda: state["cancel"],
    )

    assert "Primeira parte" in response
    assert "segunda parte" not in response
    assert response.rstrip().endswith(INTERRUPTED_MARKER)


def test_loop_react_returns_marker_when_already_cancelled(monkeypatch):
    import ai.react

    monkeypatch.setattr(ai.react, "_agenda_prompt_context", lambda: "")

    response, _steps = ai.react.loop_react(
        {
            "pergunta": "Resuma o documento",
            "documento": "conteudo local",
            "nome_documento": "nota.txt",
            "memorias_relevantes": [],
        },
        should_cancel=lambda: True,
    )

    assert response == INTERRUPTED_MARKER
