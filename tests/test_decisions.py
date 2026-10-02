"""Tests for the decision layer (core/decisions.py).

The layer is behavior-preserving: with ``enabled=False`` (the default) it must
return an empty ``off`` result and never touch any provider. Provider errors
must degrade to ``fallback`` instead of raising.
"""

from __future__ import annotations

import json

import pytest

from core.decisions import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionClient,
    DecisionProvider,
    DecisionRequest,
    HttpDecisionProvider,
    ModelChoice,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreGate,
    ScoreQuestion,
    decide_llm_model,
    decide_tool_guard,
    decide_keep_chunk,
    noul_gate,
    parse_answers,
    score_gate,
)
from core.settings import DecisionLayerSettings


def _request() -> DecisionRequest:
    return DecisionRequest(
        state={"consulta": "qual a nota?", "chunk_1": "media final deve ser 7,0"},
        questions={
            "alterar_dados": NoulQuestion("Esta acao apaga dados do usuario?"),
            "departamento": ChoiceQuestion(
                {"billing": "cobrancas", "shipping": "entregas"}, "Qual time?"
            ),
            "urgencia": ScoreQuestion(["baixa", "alta"], "Nivel de urgencia"),
        },
    )


class TestQuestionsToPayload:
    def test_noul_payload_omits_empty_instructions(self) -> None:
        assert NoulQuestion().to_payload() == {"type": "noul"}
        assert NoulQuestion("pergunta?").to_payload() == {
            "type": "noul",
            "instructions": "pergunta?",
        }

    def test_choice_and_score_payloads(self) -> None:
        choice = ChoiceQuestion({"a": "opcao a", "b": None}, "escolha").to_payload()
        assert choice["type"] == "choice"
        assert choice["criteria"] == {"a": "opcao a", "b": None}
        score = ScoreQuestion(["x", "y"], "nivel").to_payload()
        assert score["type"] == "score"
        assert score["criteria"] == ["x", "y"]


class TestParseAnswers:
    def test_full_response(self) -> None:
        payload = {
            "answers": {
                "alterar_dados": {"type": "noul", "noul": 0.77},
                "departamento": {
                    "type": "choice",
                    "choice": "billing",
                    "confidence": 0.6,
                    "probabilities": {"billing": 0.7, "shipping": 0.3},
                },
                "urgencia": {
                    "type": "score",
                    "score": 1.2,
                    "confidence": 0.8,
                    "legend": {"0": "baixa", "1": "alta"},
                    "probabilities": {"0": 0.4, "1": 0.6},
                },
            }
        }
        answers = parse_answers(payload)
        assert isinstance(answers["alterar_dados"], NoulAnswer)
        assert answers["alterar_dados"].noul == pytest.approx(0.77)
        assert isinstance(answers["departamento"], ChoiceAnswer)
        assert answers["departamento"].choice == "billing"
        assert isinstance(answers["urgencia"], ScoreAnswer)
        assert answers["urgencia"].legend == {"0": "baixa", "1": "alta"}

    def test_missing_or_malformed_answers_are_dropped(self) -> None:
        answers = parse_answers(
            {
                "answers": {
                    "ok": {"type": "noul", "noul": 0.5},
                    "broken": "not-a-dict",
                    "unknown_type": {"type": "weird", "x": 1},
                }
            }
        )
        assert set(answers) == {"ok"}


class TestOffProvider:
    def test_disabled_client_never_calls_provider(self) -> None:
        settings = DecisionLayerSettings(enabled=False)

        class BoomProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:  # pragma: no cover
                raise AssertionError("provider must not be called when disabled")

        client = DecisionClient(settings, provider=BoomProvider())
        result = client.decide(_request())
        assert result.provider == "off"
        assert result.outcome == "disabled"
        assert result.resolved is False
        assert result.answers == {}

    def test_default_settings_are_disabled(self) -> None:
        client = DecisionClient()
        assert client.enabled is False


class TestEnabledClient:
    def test_returns_typed_answers(self) -> None:
        settings = DecisionLayerSettings(enabled=True, provider="local")

        class FakeProvider:
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                assert isinstance(request.state, dict)
                assert timeout_ms == settings.timeout_ms
                return {
                    "alterar_dados": NoulAnswer(noul=0.9),
                    "departamento": ChoiceAnswer(choice="billing"),
                    "urgencia": ScoreAnswer(score=1.2),
                }

        result = DecisionClient(settings, provider=FakeProvider()).decide(_request())
        assert result.outcome == "ok"
        assert result.resolved is True
        assert result.provider == "local"
        assert result.answers["alterar_dados"].noul == pytest.approx(0.9)

    def test_provider_error_degrades_to_fallback(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class ExplodingProvider:
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                raise ConnectionError("server down")

        result = DecisionClient(settings, provider=ExplodingProvider()).decide(_request())
        assert result.provider == "fallback"
        assert result.outcome == "error"
        assert result.resolved is False

    def test_provider_none_degrades_to_fallback(self) -> None:
        settings = DecisionLayerSettings(enabled=True, timeout_ms=50)

        class NothingProvider:
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return None

        result = DecisionClient(settings, provider=NothingProvider()).decide(_request())
        assert result.provider == "fallback"
        assert result.resolved is False


class TestHttpDecisionProvider:
    def test_unreachable_endpoint_returns_none(self) -> None:
        provider = HttpDecisionProvider("http://127.0.0.1:9", model="kev-latest")
        assert provider.decide(_request(), timeout_ms=200) is None

    def test_serializes_payload_and_parses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_urlopen(req, timeout=0.0):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["timeout"] = timeout

            class FakeResp:
                def read(self):
                    return json.dumps(
                        {
                            "answers": {
                                "alterar_dados": {"type": "noul", "noul": 0.66},
                                "departamento": {
                                    "type": "choice",
                                    "choice": "shipping",
                                    "confidence": 0.5,
                                    "probabilities": {"shipping": 0.5},
                                },
                            }
                        }
                    ).encode("utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return FakeResp()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        provider = HttpDecisionProvider("http://127.0.0.1:8009", model="kev-latest")
        answers = provider.decide(_request(), timeout_ms=1234)

        assert captured["url"] == "http://127.0.0.1:8009/v1/systemone"
        assert captured["timeout"] == pytest.approx(1.234)
        body = captured["body"]
        assert body["model"] == "kev-latest"
        assert body["state"] == _request().state
        assert set(body["questions"]) == {
            "alterar_dados",
            "departamento",
            "urgencia",
        }
        assert body["questions"]["alterar_dados"]["type"] == "noul"
        assert answers is not None
        assert answers["alterar_dados"].noul == pytest.approx(0.66)


class TestNoulGate:
    def test_below_floor_is_approved(self) -> None:
        gate = noul_gate(0.30, threshold=0.70, band=0.15)
        assert gate.requires_approval is False

    def test_inside_band_escalates_but_not_certain(self) -> None:
        gate = noul_gate(0.62, threshold=0.70, band=0.15)
        assert gate.requires_approval is True
        assert gate.certain is False

    def test_above_threshold_is_certain_risk(self) -> None:
        gate = noul_gate(0.77, threshold=0.70, band=0.15)
        assert gate.requires_approval is True
        assert gate.certain is True

    def test_probability_is_clamped(self) -> None:
        assert noul_gate(-0.5).probability >= 0.0
        assert noul_gate(1.5).probability <= 1.0


class TestScoreGate:
    def test_keeps_relevant_chunk(self) -> None:
        gate = score_gate(1.2, 3, threshold=0.60, band=0.05)
        assert gate.keep is True
        assert gate.normalized == pytest.approx(0.6)

    def test_drops_irrelevant_chunk(self) -> None:
        gate = score_gate(0.2, 3, threshold=0.60, band=0.05)
        assert gate.keep is False

    def test_borderline_is_kept(self) -> None:
        gate = score_gate(1.1, 3, threshold=0.60, band=0.05)
        assert gate.keep is True

    def test_two_levels(self) -> None:
        assert score_gate(1.0, 2).normalized == pytest.approx(1.0)
        assert score_gate(0.0, 2).normalized == pytest.approx(0.0)


class TestDecideToolGuard:
    def test_disabled_layer_never_approves_nor_calls_provider(self) -> None:
        settings = DecisionLayerSettings(enabled=False)

        class BoomProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:  # pragma: no cover
                raise AssertionError("provider must not run when disabled")

        client = DecisionClient(settings, provider=BoomProvider())
        gate = decide_tool_guard(client, settings, tool="salvar_memoria", arguments={"texto": "x"})
        assert gate.requires_approval is False
        assert gate.certain is False

    def test_risky_tool_requires_approval(self) -> None:
        settings = DecisionLayerSettings(enabled=True, guard_risk_threshold=0.70)

        class RiskyProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                assert isinstance(request.state, dict)
                assert request.state.get("tipo_acao") == "salvar_memoria"
                assert any(q.instructions for q in request.questions.values())
                return {
                    "altera_dados": NoulAnswer(noul=0.85),
                    "irreversivel": NoulAnswer(noul=0.62),
                    "rede": NoulAnswer(noul=0.10),
                    "destrutiva": NoulAnswer(noul=0.20),
                }

        client = DecisionClient(settings, provider=RiskyProvider())
        gate = decide_tool_guard(client, settings, tool="salvar_memoria", arguments={"texto": "x"})
        assert gate.requires_approval is True

    def test_safe_tool_is_not_flagged(self) -> None:
        settings = DecisionLayerSettings(enabled=True, guard_risk_threshold=0.70)

        class SafeProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {
                    "altera_dados": NoulAnswer(noul=0.10),
                    "irreversivel": NoulAnswer(noul=0.05),
                    "rede": NoulAnswer(noul=0.05),
                    "destrutiva": NoulAnswer(noul=0.02),
                }

        client = DecisionClient(settings, provider=SafeProvider())
        gate = decide_tool_guard(client, settings, tool="informacoes_sistema", arguments={})
        assert gate.requires_approval is False

    def test_provider_failure_keeps_current_behavior(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class DownProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                raise ConnectionError("kev not running")

        client = DecisionClient(settings, provider=DownProvider())
        gate = decide_tool_guard(client, settings, tool="salvar_memoria", arguments={"texto": "x"})
        assert gate.requires_approval is False
        assert gate.certain is False


class TestDecideKeepChunk:
    def test_disabled_layer_never_prunes(self) -> None:
        settings = DecisionLayerSettings(enabled=False)

        class BoomProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                raise AssertionError("provider must not run when disabled")

        client = DecisionClient(settings, provider=BoomProvider())
        assert decide_keep_chunk(client, settings, query="q", chunk="x") is True

    def test_relevant_chunk_is_kept(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class RelevantProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                assert "trecho" in request.state
                return {"relevancia": ScoreAnswer(score=1.8)}

        client = DecisionClient(settings, provider=RelevantProvider())
        assert decide_keep_chunk(client, settings, query="q", chunk="x") is True

    def test_irrelevant_chunk_is_still_kept_while_pruning_is_disabled(self) -> None:
        """Safety default: the gate scores but never drops a chunk."""
        settings = DecisionLayerSettings(enabled=True)

        class IrrelevantProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {"relevancia": ScoreAnswer(score=0.4)}

        client = DecisionClient(settings, provider=IrrelevantProvider())
        assert decide_keep_chunk(client, settings, query="q", chunk="x") is True

    def test_pruning_requires_explicit_opt_in_and_calibration(self, monkeypatch) -> None:
        settings = DecisionLayerSettings(
            enabled=True, rag_prune_enabled=True, rag_calibration_mode=True
        )

        class IrrelevantProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {"relevancia": ScoreAnswer(score=0.4)}

        client = DecisionClient(settings, provider=IrrelevantProvider())
        monkeypatch.setattr(
            "core.decisions.rag_samples_available", lambda _settings: settings.rag_min_samples
        )
        assert decide_keep_chunk(client, settings, query="q", chunk="x") is False

    def test_calibration_keeps_chunk_until_enough_samples(self, monkeypatch) -> None:
        settings = DecisionLayerSettings(
            enabled=True, rag_prune_enabled=True, rag_calibration_mode=True, rag_min_samples=30
        )

        class IrrelevantProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {"relevancia": ScoreAnswer(score=0.4)}

        client = DecisionClient(settings, provider=IrrelevantProvider())
        monkeypatch.setattr("core.decisions.rag_samples_available", lambda _settings: 3)
        assert decide_keep_chunk(client, settings, query="q", chunk="x") is True

    def test_borderline_chunk_is_never_pruned(self, monkeypatch) -> None:
        """Only chunks *clearly* below the threshold may be dropped."""
        settings = DecisionLayerSettings(
            enabled=True, rag_prune_enabled=True, rag_calibration_mode=False
        )

        class BorderlineProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {"relevancia": ScoreAnswer(score=1.4)}  # normalized 0.70

        client = DecisionClient(settings, provider=BorderlineProvider())
        monkeypatch.setattr("core.decisions.rag_samples_available", lambda _settings: 999)
        assert decide_keep_chunk(client, settings, query="q", chunk="x") is True

    def test_provider_failure_keeps_chunk(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class DownProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                raise ConnectionError("kev not running")

        client = DecisionClient(settings, provider=DownProvider())
        assert decide_keep_chunk(client, settings, query="q", chunk="x") is True

    def test_missing_answer_keeps_chunk(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class EmptyProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {}

        client = DecisionClient(settings, provider=EmptyProvider())
        assert decide_keep_chunk(client, settings, query="q", chunk="x") is True


class TestDecideLlmModel:
    @staticmethod
    def _candidates() -> list:
        from types import SimpleNamespace

        return [
            SimpleNamespace(id="model-a", name="Modelo A", quant="Q4_K_M", size_gb=4.0),
            SimpleNamespace(id="model-b", name="Modelo B", quant="Q4_K_M", size_gb=7.0),
            SimpleNamespace(id="model-c", name="Modelo C", quant="Q6_K", size_gb=9.0),
        ]

    def test_disabled_returns_none(self) -> None:
        settings = DecisionLayerSettings(enabled=False)
        client = DecisionClient(settings, provider=DecisionProvider())
        assert decide_llm_model(client, settings, query="q", models=self._candidates()) is None

    def test_model_routing_turned_off_returns_none(self) -> None:
        settings = DecisionLayerSettings(enabled=True, model_routing=False)
        client = DecisionClient(settings, provider=DecisionProvider())
        assert decide_llm_model(client, settings, query="q", models=self._candidates()) is None

    def test_too_few_candidates_returns_none(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class SilentProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {}

        client = DecisionClient(settings, provider=SilentProvider())
        assert decide_llm_model(client, settings, query="q", models=self._candidates()[:1]) is None

    def test_picks_highest_scored_model(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class PickProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                answers = {}
                for qid in request.questions:
                    model_id = qid.split("_", 1)[1]
                    answers[qid] = ScoreAnswer(score=2.0 if model_id == "model-b" else 1.0)
                return answers

        client = DecisionClient(settings, provider=PickProvider())
        choice = decide_llm_model(
            client, settings, query="analise o codigo", models=self._candidates()
        )
        assert choice is not None
        assert choice.model_id == "model-b"
        assert choice.normalized == 1.0

    def test_low_scores_return_none_to_fall_back_to_router(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class LowProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {qid: ScoreAnswer(score=0.0) for qid in request.questions}

        client = DecisionClient(settings, provider=LowProvider())
        assert (
            decide_llm_model(client, settings, query="analise", models=self._candidates()) is None
        )

    def test_provider_failure_returns_none(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class DownProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                raise ConnectionError("kev not running")

        client = DecisionClient(settings, provider=DownProvider())
        assert (
            decide_llm_model(client, settings, query="analise", models=self._candidates()) is None
        )


class TestModelRoutingGates:
    """Auto routing must only commit when the choice is real and confident."""

    @staticmethod
    def _models() -> list:
        from types import SimpleNamespace

        return [
            SimpleNamespace(id="model-a", name="A", quant="Q4_K_M", size_gb=4.0),
            SimpleNamespace(id="model-b", name="B", quant="Q4_K_M", size_gb=7.0),
        ]

    def _client(self, settings, scores):
        class Provider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {
                    qid: ScoreAnswer(score=scores.get(qid.split("_", 1)[1], 0.0))
                    for qid in request.questions
                }

        return DecisionClient(settings, provider=Provider())

    def test_a_tie_keeps_the_current_model(self) -> None:
        settings = DecisionLayerSettings(enabled=True)
        client = self._client(settings, {"model-a": 2.0, "model-b": 2.0})
        assert decide_llm_model(client, settings, query="q", models=self._models()) is None

    def test_low_confidence_keeps_the_current_model(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class LowConfidenceProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {
                    qid: ScoreAnswer(score=2.0 if qid.endswith("model-b") else 1.0, confidence=0.1)
                    for qid in request.questions
                }

        client = DecisionClient(settings, provider=LowConfidenceProvider())
        assert decide_llm_model(client, settings, query="q", models=self._models()) is None

    def test_only_one_scored_model_is_not_a_decision(self) -> None:
        settings = DecisionLayerSettings(enabled=True)

        class PartialProvider(DecisionProvider):
            def decide(
                self, request: DecisionRequest, *, timeout_ms: int
            ) -> dict[str, Answer] | None:
                return {"modelo_model-b": ScoreAnswer(score=2.0)}

        client = DecisionClient(settings, provider=PartialProvider())
        assert decide_llm_model(client, settings, query="q", models=self._models()) is None

    def test_declined_routes_are_audited(self) -> None:
        settings = DecisionLayerSettings(enabled=True)
        entries: list[dict] = []

        class Recorder:
            def append(self, entry: dict) -> None:
                entries.append(entry)

        client = self._client(settings, {"model-a": 2.0, "model-b": 2.0})
        client._recorder = Recorder()  # noqa: SLF001 - wiring the audit sink
        decide_llm_model(client, settings, query="q", models=self._models())
        assert entries and entries[0]["decision"] == "declined"
        assert "margem" in entries[0]["reason"]

    def test_margin_and_runner_up_are_reported_on_acceptance(self) -> None:
        settings = DecisionLayerSettings(enabled=True)
        client = self._client(settings, {"model-a": 1.0, "model-b": 2.0})
        choice = decide_llm_model(
            client, settings, query="q", models=self._models(), current_model="model-a"
        )
        assert choice is not None
        assert choice.model_id == "model-b"
        assert choice.runner_up == "model-a"
        assert choice.margin == pytest.approx(0.5)

    def test_switching_to_the_model_already_in_use_is_a_no_op(self) -> None:
        settings = DecisionLayerSettings(enabled=True)
        client = self._client(settings, {"model-a": 1.0, "model-b": 2.0})
        assert (
            decide_llm_model(
                client, settings, query="q", models=self._models(), current_model="model-b"
            )
            is None
        )

    def test_models_that_cannot_read_documents_are_excluded(self) -> None:
        from types import SimpleNamespace

        settings = DecisionLayerSettings(enabled=True)
        client = self._client(settings, {"text-only": 2.0, "vision": 2.0})
        models = [
            SimpleNamespace(
                id="text-only", capabilities=SimpleNamespace(declared=frozenset({"text"}))
            ),
            SimpleNamespace(
                id="vision", capabilities=SimpleNamespace(declared=frozenset({"text", "document"}))
            ),
        ]
        # Only one candidate survives capability filtering -> no auto switch.
        assert (
            decide_llm_model(client, settings, query="q", models=models, has_document=True) is None
        )

    def test_missing_capability_metadata_stays_eligible(self) -> None:
        from types import SimpleNamespace

        settings = DecisionLayerSettings(enabled=True)
        client = self._client(settings, {"plain-a": 1.0, "plain-b": 2.0})
        models = [SimpleNamespace(id="plain-a"), SimpleNamespace(id="plain-b")]
        assert (
            decide_llm_model(client, settings, query="q", models=models, has_document=True)
            is not None
        )


class TestDecisionHealth:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///tmp/kev",
            "https://127.0.0.1:8009",
            "http://example.com:8009",
            "http://user:password@127.0.0.1:8009",
        ],
    )
    def test_http_provider_rejects_non_local_or_unsafe_urls(self, url: str) -> None:
        from core.decisions import HttpDecisionProvider

        with pytest.raises(ValueError):
            HttpDecisionProvider(url)

    def test_disabled_layer_reports_off_without_probing(self) -> None:
        client = DecisionClient(DecisionLayerSettings(enabled=False))
        health = client.health()
        assert health.state == "off"
        assert health.reachable is False

    def test_http_provider_probe_reports_models(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from core import decisions as decisions_mod

        def fake_urlopen(req, timeout=0.0):
            class FakeResp:
                def read(self):
                    return json.dumps(
                        {"models": [{"name": "kev-latest"}, {"name": "jev-latest"}]}
                    ).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return FakeResp()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        provider = decisions_mod.HttpDecisionProvider("http://127.0.0.1:8009")
        names, error = provider.list_models()
        assert names == ("kev-latest", "jev-latest")
        assert error == ""

    def test_unreachable_server_is_reported_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core import decisions as decisions_mod

        def boom(req, timeout=0.0):
            raise OSError("connection refused")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        provider = decisions_mod.HttpDecisionProvider("http://127.0.0.1:8009")
        names, error = provider.list_models()
        assert names == ()
        assert "connection refused" in error

    def test_health_is_cached_between_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from core import decisions as decisions_mod

        calls: list[str] = []

        def counting_urlopen(req, timeout=0.0):
            calls.append(req.full_url)

            class FakeResp:
                def read(self):
                    return json.dumps({"models": [{"name": "kev-latest"}]}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return FakeResp()

        monkeypatch.setattr("urllib.request.urlopen", counting_urlopen)
        client = DecisionClient(
            DecisionLayerSettings(enabled=True, health_cache_seconds=60.0),
            provider=decisions_mod.HttpDecisionProvider("http://127.0.0.1:8009"),
        )
        assert client.health().reachable is True
        assert client.health().reachable is True
        assert len(calls) == 1
        assert client.health(force=True).reachable is True
        assert len(calls) == 2

    def test_unannounced_model_is_flagged_but_reachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core import decisions as decisions_mod

        def fake_urlopen(req, timeout=0.0):
            class FakeResp:
                def read(self):
                    return json.dumps({"models": [{"name": "outro-modelo"}]}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return FakeResp()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        client = DecisionClient(
            DecisionLayerSettings(enabled=True, model="kev-latest"),
            provider=decisions_mod.HttpDecisionProvider("http://127.0.0.1:8009"),
        )
        health = client.health()
        assert health.reachable is True
        assert "kev-latest" in health.detail
        assert health.as_dict()["state"] == "available"

    def test_repeated_failures_are_logged_once_at_warning(self, monkeypatch, caplog) -> None:
        import logging

        from core import decisions as decisions_mod

        def boom(req, timeout=0.0):
            raise OSError("connection refused")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        provider = decisions_mod.HttpDecisionProvider("http://127.0.0.1:8009")
        with caplog.at_level(logging.WARNING, logger="core.decisions"):
            for _ in range(5):
                provider.decide(_request(), timeout_ms=50)
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
