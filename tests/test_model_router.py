"""Tests for core.model_router (query routing, scoring, model profiles)."""

from types import SimpleNamespace

import pytest

from core.model_router import (
    MODEL_PROFILES,
    Complexity,
    ModelProfile,
    ModelRouter,
    RoutingDecision,
    _compute_complexity_score,
    _keyword_score,
    apply_model_tool_policy,
    get_model_profile,
    model_runtime_defaults,
    model_start_kwargs,
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class TestRoutingDecision:
    def test_creation(self):
        d = RoutingDecision(
            model_id="test-model",
            complexity=Complexity.SIMPLE,
            confidence=0.9,
            reason="short query",
            score=-0.5,
        )
        assert d.model_id == "test-model"
        assert d.complexity == Complexity.SIMPLE
        assert d.confidence == 0.9
        assert d.reason == "short query"
        assert d.score == -0.5

    def test_default_score(self):
        d = RoutingDecision(model_id="m", complexity=Complexity.MEDIUM, confidence=0.5, reason="r")
        assert d.score == 0.0


class TestModelProfile:
    def test_creation(self):
        p = ModelProfile(
            name="Test Model",
            max_context=8192,
            supports_vision=True,
            supports_tools=False,
            speed_rating=1.0,
            quality_rating=0.5,
        )
        assert p.name == "Test Model"
        assert p.max_context == 8192
        assert p.supports_vision is True
        assert p.supports_tools is False

    def test_defaults(self):
        p = ModelProfile(name="M", max_context=4096)
        assert p.supports_vision is False
        assert p.supports_tools is False
        assert p.speed_rating == 1.0
        assert p.quality_rating == 0.5

    def test_frozen(self):
        p = ModelProfile(name="M", max_context=4096)
        with pytest.raises(AttributeError):
            p.name = "Changed"


class TestComplexityEnum:
    def test_values(self):
        assert Complexity.SIMPLE == "simple"
        assert Complexity.MEDIUM == "medium"
        assert Complexity.COMPLEX == "complex"

    def test_members(self):
        assert len(Complexity) == 3


# ---------------------------------------------------------------------------
# Model profiles registry
# ---------------------------------------------------------------------------


class TestModelProfiles:
    def test_profiles_exist(self):
        assert len(MODEL_PROFILES) >= 8

    def test_known_models(self):
        for mid in [
            "qwen3-8b-q4km",
            "qwen2.5-vl-7b-q4km",
            "qwen2.5-coder-7b-q5km",
            "gemma3-4b-q4km",
        ]:
            assert mid in MODEL_PROFILES

    def test_get_model_profile(self):
        p = get_model_profile("qwen2.5-vl-7b-q4km")
        assert p is not None
        assert p.supports_vision is True

    def test_get_model_profile_unknown(self):
        assert get_model_profile("nonexistent-model") is None

    def test_fast_model_is_fastest(self):
        fast = MODEL_PROFILES["gemma3-4b-q4km"]
        assert fast.speed_rating == 0.9

    def test_vision_models_support_vision(self):
        for mid in ["qwen2.5-vl-3b-q4km", "qwen2.5-vl-7b-q4km", "gemma3-4b-q4km"]:
            p = MODEL_PROFILES.get(mid)
            if p:
                assert p.supports_vision is True


# ---------------------------------------------------------------------------
# _compute_complexity_score
# ---------------------------------------------------------------------------


class TestComputeComplexityScore:
    def test_short_query_simple(self):
        score, reasons = _compute_complexity_score("hi")
        assert score < 0
        assert any("short" in r for r in reasons)

    def test_long_query_complex(self):
        long_text = " ".join(["word"] * 300)
        score, reasons = _compute_complexity_score(long_text)
        assert score > 0
        assert any("long" in r for r in reasons)

    def test_question_mark_penalty(self):
        score_q, _ = _compute_complexity_score("hello?")
        score_nq, _ = _compute_complexity_score("hello")
        assert score_q < score_nq

    def test_greeting_detection(self):
        score, reasons = _compute_complexity_score("hello")
        assert score < 0
        assert any("greeting" in r for r in reasons)

    def test_greeting_oi(self):
        score, _ = _compute_complexity_score("oi")
        assert score < 0

    def test_greeting_bom_dia(self):
        score, _ = _compute_complexity_score("bom dia")
        assert score < 0

    def test_document_context_increases_score(self):
        score_no_doc, _ = _compute_complexity_score("analyze this", has_document=False)
        score_doc, _ = _compute_complexity_score("analyze this", has_document=True)
        assert score_doc > score_no_doc

    def test_complex_keywords_positive(self):
        code = "criar um relatÃ³rio detalhado do cÃ³digo python com anÃ¡lise estatÃ­stica"
        score, reasons = _compute_complexity_score(code)
        assert score > 0
        assert any("keyword" in r for r in reasons)

    def test_analysis_keyword(self):
        score, reasons = _compute_complexity_score(
            "fazer uma analise completa e detalhada de dados"
        )
        assert any("analysis" in r for r in reasons)
        assert "keyword: analysis" in reasons

    def test_code_keyword(self):
        score, reasons = _compute_complexity_score(
            "escreva um cÃ³digo python completo com funÃ§Ãµes"
        )
        assert any("code" in r for r in reasons)

    def test_document_keyword(self):
        score, _ = _compute_complexity_score("extraia texto do documento pdf")
        assert score > 0

    def test_debug_keyword(self):
        score, _ = _compute_complexity_score("depurar erro exception traceback")
        assert score > 0

    def test_refactor_keyword(self):
        score, _ = _compute_complexity_score("refatorar otimizar performance")
        assert score > 0

    def test_test_keyword(self):
        score, _ = _compute_complexity_score("criar teste unittest pytest assert")
        assert score > 0

    def test_statistics_keyword(self):
        score, _ = _compute_complexity_score("calcular mÃ©dia mediana desvio estatÃ­stica")
        assert score > 0

    def test_simple_wh_question(self):
        score, _ = _compute_complexity_score("qual Ã© a capital do Brasil?")
        # Has both simple (wh-question) and question mark penalty, net should be negative-ish
        # but "qual Ã© a capital do Brasil" doesn't match complex keywords
        assert isinstance(score, float)

    def test_score_clamped(self):
        score, _ = _compute_complexity_score("x" * 5000)
        assert -1.0 <= score <= 1.0


class TestKeywordScore:
    def test_multiple_complex_keywords_boost(self):
        text = "anÃ¡lise cÃ³digo debug refatorar teste"
        score, reasons = _keyword_score(text)
        assert score > 0.3
        assert len(reasons) >= 3

    def test_single_complex_keyword(self):
        score, reasons = _keyword_score("analise detalhada de dados estatisticos")
        assert len(reasons) >= 1
        assert score >= 0

    def test_greeting_simple(self):
        score, reasons = _keyword_score("oi obrigado")
        assert score < 0
        assert any("greeting" in r for r in reasons)


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------


class TestModelRouterSimpleQueries:
    def test_greeting_routes_to_single_model(self, monkeypatch):
        monkeypatch.setattr("core.model_router._model_file_exists", lambda *_: True)
        router = ModelRouter()
        decision = router.route("hello")
        # Celsius runs with a SINGLE LLM (qwen2.5-vl-7b) — SIMPLE queries
        # no longer escalate to gemma3-4b; everything uses the main model.
        assert decision.complexity == Complexity.SIMPLE
        assert decision.model_id == "qwen2.5-vl-7b-q4km"

    def test_short_question_simple(self):
        router = ModelRouter()
        decision = router.route("oi")
        assert decision.complexity == Complexity.SIMPLE

    def test_short_greeting_bom_dia(self):
        router = ModelRouter()
        decision = router.route("bom dia")
        assert decision.complexity == Complexity.SIMPLE

    def test_missing_fast_model_falls_back_to_installed_default(self, monkeypatch):
        def model_exists(_settings, model_id):
            return model_id == "qwen2.5-vl-7b-q4km"

        monkeypatch.setattr("core.model_router._model_file_exists", model_exists)
        router = ModelRouter()
        decision = router.route("hello")

        assert decision.complexity == Complexity.SIMPLE
        assert decision.model_id == "qwen2.5-vl-7b-q4km"


class TestModelRouterComplexQueries:
    def test_code_query_complex(self):
        router = ModelRouter()
        decision = router.route(
            "criar um cÃ³digo python para anÃ¡lise de dados com relatÃ³rio detalhado e testes"
        )
        assert decision.complexity in (Complexity.MEDIUM, Complexity.COMPLEX)

    def test_long_analysis_complex(self):
        query = (
            "FaÃ§a uma anÃ¡lise detalhada do documento anexo, comparando os dados estatÃ­sticos " * 5
        )
        router = ModelRouter()
        decision = router.route(query)
        assert decision.complexity in (Complexity.MEDIUM, Complexity.COMPLEX)

    def test_document_context_increases_complexity(self):
        router = ModelRouter()
        decision_no_doc = router.route("analise isso", has_document=False)
        decision_doc = router.route("analise isso", has_document=True)
        assert decision_doc.score >= decision_no_doc.score

    def test_text_document_uses_active_default_model(self, monkeypatch):
        monkeypatch.setattr("core.model_router._model_file_exists", lambda *_: True)
        router = ModelRouter()
        decision = router.route("analise este documento", has_document=True)

        assert decision.model_id == "qwen2.5-vl-7b-q4km"
        assert decision.complexity == Complexity.COMPLEX

    def test_image_routes_to_vision_model(self, monkeypatch):
        monkeypatch.setattr("core.model_router._model_file_exists", lambda *_: True)
        router = ModelRouter()
        decision = router.route(
            "descreva o anexo",
            has_document=True,
            has_image=True,
        )

        assert decision.model_id == "qwen2.5-vl-7b-q4km"

    def test_deep_analysis_routes_to_single_model(self, monkeypatch):
        monkeypatch.setattr("core.model_router._model_file_exists", lambda *_: True)
        router = ModelRouter()
        decision = router.route("faca uma analise profunda de viabilidade financeira")

        # Celsius runs with a SINGLE LLM (qwen2.5-vl-7b): reasoning escalation
        # is intentionally disabled, so every query — regardless of complexity —
        # routes to the same model.
        assert decision.model_id == "qwen2.5-vl-7b-q4km"

    def test_balanced_general_query_routes_to_qwen25_vl(self):
        router = ModelRouter()
        decision = router.route("explique como organizar o estoque da empresa")

        assert decision.model_id == "qwen2.5-vl-7b-q4km"


class TestModelRouterMediumQueries:
    def test_medium_query(self):
        router = ModelRouter()
        # A query that's not clearly simple or complex
        decision = router.route("What is the capital of France? Explain briefly.")
        assert decision.complexity in (Complexity.SIMPLE, Complexity.MEDIUM)


class TestModelRouterDecisionDetails:
    def test_has_reason(self):
        router = ModelRouter()
        decision = router.route("hello")
        assert len(decision.reason) > 0

    def test_score_is_number(self):
        router = ModelRouter()
        decision = router.route("test query")
        assert isinstance(decision.score, float)

    def test_confidence_range(self):
        router = ModelRouter()
        for q in ["hi", "analyze code in detail", "hello?"]:
            decision = router.route(q)
            assert 0.0 <= decision.confidence <= 1.0

    def test_model_id_always_single_qwen25_vl(self, monkeypatch):
        monkeypatch.setattr("core.model_router._model_file_exists", lambda *_: True)
        router = ModelRouter()
        simple = router.route("hi")
        # A single LLM means EVERY query (simple or complex) maps to
        # qwen2.5-vl-7b — no gemma3 fast model, no qwen3-14b quality model.
        assert simple.model_id == "qwen2.5-vl-7b-q4km"

        complex_q = router.route(
            "criar codigo python detalhado com analise, relatorio completo, "
            "debug, testes, performance, estatistica e dashboard"
        )
        assert complex_q.complexity == Complexity.COMPLEX
        assert complex_q.model_id == "qwen2.5-vl-7b-q4km"


class TestModelRouterClassifyComplexity:
    def test_returns_complexity_enum(self):
        router = ModelRouter()
        c = router.classify_complexity("hello")
        assert isinstance(c, Complexity)

    def test_simple_classification(self):
        router = ModelRouter()
        assert router.classify_complexity("oi") == Complexity.SIMPLE

    def test_complex_classification(self):
        router = ModelRouter()
        c = router.classify_complexity(
            "criar cÃ³digo python anÃ¡lise detalhada relatÃ³rio completo"
        )
        assert c in (Complexity.MEDIUM, Complexity.COMPLEX)


class TestModelRouterGetProfile:
    def test_known_model(self):
        router = ModelRouter()
        p = router.get_profile("qwen2.5-vl-7b-q4km")
        assert p is not None
        assert p.supports_vision is True

    def test_unknown_model(self):
        router = ModelRouter()
        assert router.get_profile("no-such-model") is None


class TestModelRouterGetModelForQuery:
    def test_returns_string(self):
        router = ModelRouter()
        model = router.get_model_for_query("hi")
        assert isinstance(model, str)

    def test_simple_returns_single_model(self, monkeypatch):
        monkeypatch.setattr("core.model_router._model_file_exists", lambda *_: True)
        router = ModelRouter()
        model = router.get_model_for_query("oi")
        # Celsius runs with a SINGLE LLM — simple queries use the same
        # qwen2.5-vl-7b as everything else (no gemma3 fast escalation).
        assert model == "qwen2.5-vl-7b-q4km"


class TestModelRouterCascade:
    def test_high_confidence_no_cascade(self):
        router = ModelRouter(cascade_enabled=True, cascade_min_confidence=0.6)
        cascade = router.route_with_cascade("hi")
        assert len(cascade) == 1

    def test_cascade_disabled(self):
        router = ModelRouter(cascade_enabled=False)
        cascade = router.route_with_cascade("analyze code in detail")
        assert len(cascade) == 1

    def test_cascade_returns_list(self):
        router = ModelRouter(cascade_enabled=True, cascade_min_confidence=0.99)
        cascade = router.route_with_cascade("analyze code in detail")
        assert isinstance(cascade, list)
        assert len(cascade) >= 1
        assert isinstance(cascade[0], RoutingDecision)

    def test_cascade_first_is_primary(self):
        router = ModelRouter(cascade_enabled=True, cascade_min_confidence=0.99)
        primary = router.route("analyze code in detail")
        cascade = router.route_with_cascade("analyze code in detail")
        assert cascade[0].model_id == primary.model_id


class _FakeLlamaManager:
    def __init__(self, current: str = "qwen2.5-vl-7b-q4km"):
        self._started = True
        self.current_model_id = current

    def start(self, model_id=None, **kwargs):
        self.current_model_id = model_id
        return True

    def stop(self):
        self._started = False


def _router_settings(**overrides):
    from pathlib import Path
    from types import SimpleNamespace

    base = {
        "llm_model": "qwen2.5-vl-7b-q4km",
        "default_llm_model": "qwen2.5-vl-7b-q4km",
        "fast_llm_model": "gemma3-4b-q4km",
        "model_client_choice": False,
        "decision": None,
        "get_resources_dir": lambda: Path("."),
        "bundled_resources_dir": Path("."),
        "get_model_path": lambda model_id: Path(".") / (model_id + ".gguf"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_manager(monkeypatch, settings, *, current: str = "qwen2.5-vl-7b-q4km"):
    from core.model_router import MultiModelManager

    monkeypatch.setattr("core.model_router.get_settings", lambda: settings)
    mm = MultiModelManager.__new__(MultiModelManager)
    mm.main_manager = _FakeLlamaManager(current)
    mm.fast_manager = _FakeLlamaManager()
    mm.router = ModelRouter()
    mm._current_complexity = None
    mm._last_decision = None
    mm._active_model_id = None
    mm._pending_ideal_model = None
    return mm


class _CapturingFakeLlamaManager(_FakeLlamaManager):
    def __init__(self, current: str = "qwen2.5-vl-7b-q4km"):
        super().__init__(current)
        self.start_calls: list[tuple[str | None, dict]] = []

    def start(self, model_id=None, **kwargs):
        self.start_calls.append((model_id, kwargs))
        return super().start(model_id, **kwargs)


def _installed_examples():
    from types import SimpleNamespace

    return [
        SimpleNamespace(id="qwen2.5-vl-7b-q4km", name="Qwen2.5 VL 7B", quant="Q4_K_M", size_gb=4.5),
        SimpleNamespace(id="qwen3-8b-q4km", name="Qwen3 8B", quant="Q4_K_M", size_gb=5.2),
    ]


class TestMultiModelManagerRouting:
    def test_client_pin_wins_over_jev(self, monkeypatch):
        from core.decisions import ModelChoice
        from core.model_router import MultiModelManager
        from core.settings import DecisionLayerSettings

        settings = _router_settings(
            model_client_choice=True,
            decision=DecisionLayerSettings(enabled=True),
        )
        mm = _make_manager(monkeypatch, settings)

        def boom(*args, **kwargs):
            raise AssertionError("JEV must not run when the client pinned a model")

        monkeypatch.setattr("core.decisions.decide_llm_model", boom)
        monkeypatch.setattr("core.decisions.get_decision_client", lambda: None)

        model_id, _ = mm.route_and_invoke("analise profunda do codigo")
        assert model_id == "qwen2.5-vl-7b-q4km"
        assert mm._last_decision.reason == "client"

    def test_jev_picks_among_installed_when_unpinned(self, monkeypatch):
        from core.decisions import ModelChoice
        from core.model_router import MultiModelManager
        from core.settings import DecisionLayerSettings

        settings = _router_settings(decision=DecisionLayerSettings(enabled=True))
        mm = _make_manager(monkeypatch, settings)
        monkeypatch.setattr(
            MultiModelManager,
            "_installed_models",
            staticmethod(lambda s: _installed_examples()),
        )
        monkeypatch.setattr(
            "core.decisions.decide_llm_model",
            lambda *args, **kwargs: ModelChoice(
                model_id="qwen3-8b-q4km", score=2.0, normalized=1.0
            ),
        )
        monkeypatch.setattr("core.decisions.get_decision_client", lambda: None)

        model_id, _ = mm.route_and_invoke("analise profunda do codigo")
        assert model_id == "qwen3-8b-q4km"
        assert mm._last_decision.reason == "jev"

    def test_disabled_decision_falls_back_to_router(self, monkeypatch):
        from core.model_router import MultiModelManager
        from core.settings import DecisionLayerSettings

        settings = _router_settings(decision=DecisionLayerSettings(enabled=False))
        mm = _make_manager(monkeypatch, settings)

        def boom(*args, **kwargs):
            raise AssertionError("JEV must not run when decision layer is disabled")

        monkeypatch.setattr("core.decisions.decide_llm_model", boom)
        monkeypatch.setattr("core.decisions.get_decision_client", lambda: None)

        model_id, _ = mm.route_and_invoke("oi")
        assert model_id == "qwen2.5-vl-7b-q4km"
        assert mm._last_decision.reason == "auto"


class TestMultiModelManagerContextPreservation:
    """Improvement #1: avoid swapping the loaded model mid-conversation."""

    def _jev_switching_to_qwen3(self, monkeypatch):
        from core.decisions import ModelChoice
        from core.model_router import MultiModelManager
        from core.settings import DecisionLayerSettings

        settings = _router_settings(decision=DecisionLayerSettings(enabled=True))
        mm = _make_manager(monkeypatch, settings)
        monkeypatch.setattr(
            MultiModelManager,
            "_installed_models",
            staticmethod(lambda s: _installed_examples()),
        )
        monkeypatch.setattr(
            "core.decisions.decide_llm_model",
            lambda *args, **kwargs: ModelChoice(
                model_id="qwen3-8b-q4km", score=2.0, normalized=1.0
            ),
        )
        monkeypatch.setattr("core.decisions.get_decision_client", lambda: None)
        return mm

    def test_long_conversation_defers_picked_model(self, monkeypatch):
        from core.model_router import FRESH_CONTEXT_TOKENS

        mm = self._jev_switching_to_qwen3(monkeypatch)
        model_id, _ = mm.route_and_invoke(
            "analise profunda do codigo", est_tokens=FRESH_CONTEXT_TOKENS + 1
        )

        assert model_id == "qwen2.5-vl-7b-q4km"
        decision = mm._last_decision
        assert decision is not None
        assert decision.reason == "jev"
        assert decision.switched is False
        assert decision.deferred_model_id == "qwen3-8b-q4km"
        assert decision.notice and "preservar o contexto" in decision.notice

    def test_fresh_conversation_switches_model(self, monkeypatch):
        mm = self._jev_switching_to_qwen3(monkeypatch)
        model_id, _ = mm.route_and_invoke("analise profunda do codigo", est_tokens=0)

        assert model_id == "qwen3-8b-q4km"
        assert mm._last_decision.switched is True
        assert mm._last_decision.deferred_model_id is None
        assert mm._last_decision.notice and "Troquei para" in mm._last_decision.notice

    def test_image_requires_vision_switches_mid_conversation(self, monkeypatch):
        from core.decisions import ModelChoice
        from core.model_router import MultiModelManager, FRESH_CONTEXT_TOKENS
        from core.settings import DecisionLayerSettings

        settings = _router_settings(decision=DecisionLayerSettings(enabled=True))
        mm = _make_manager(monkeypatch, settings, current="qwen3-8b-q4km")
        monkeypatch.setattr(
            MultiModelManager,
            "_installed_models",
            staticmethod(lambda s: _installed_examples()),
        )
        monkeypatch.setattr(
            "core.decisions.decide_llm_model",
            lambda *args, **kwargs: ModelChoice(
                model_id="qwen2.5-vl-7b-q4km", score=2.0, normalized=1.0
            ),
        )
        monkeypatch.setattr("core.decisions.get_decision_client", lambda: None)

        model_id, _ = mm.route_and_invoke(
            "o que tem nessa imagem?",
            has_image=True,
            est_tokens=FRESH_CONTEXT_TOKENS + 1,
        )

        assert model_id == "qwen2.5-vl-7b-q4km"
        assert mm._last_decision.switched is True
        assert mm._last_decision.notice and "imagem" in mm._last_decision.notice

    def test_same_model_keeps_context_without_notice(self, monkeypatch):
        from core.model_router import MultiModelManager
        from core.settings import DecisionLayerSettings

        settings = _router_settings(decision=DecisionLayerSettings(enabled=False))
        mm = _make_manager(monkeypatch, settings)

        model_id, _ = mm.route_and_invoke("oi", est_tokens=20000)

        assert model_id == "qwen2.5-vl-7b-q4km"
        assert mm._last_decision.switched is False
        assert mm._last_decision.deferred_model_id is None
        assert mm._last_decision.notice is None

    def test_active_model_id_tracks_loaded_model(self, monkeypatch):
        mm = self._jev_switching_to_qwen3(monkeypatch)
        mm.route_and_invoke("analise profunda do codigo", est_tokens=0)
        assert mm._active_model_id == "qwen3-8b-q4km"

        mm.route_and_invoke("continuando o assunto...", est_tokens=20000)
        assert mm._active_model_id == "qwen3-8b-q4km"
        assert mm._last_decision.switched is False
        assert mm._last_decision.deferred_model_id is None


class TestModelToolPolicy:
    """Improvement #4a: per-model tool schema (cap + exclusions)."""

    def _tools(self, n: int):
        from types import SimpleNamespace

        return [SimpleNamespace(nome=f"ferramenta_{i}") for i in range(n)]

    def test_unknown_model_keeps_all_tools(self):
        tools = self._tools(20)
        out = apply_model_tool_policy(tools, "modelo-desconhecido")
        assert out == tools
        assert len(out) == 20

    def test_cap_trims_to_limit_preserving_order(self):
        tools = self._tools(20)
        out = apply_model_tool_policy(tools, "qwen2.5-3b-q8")  # tool_limit=6
        assert len(out) == 6
        assert [t.nome for t in out] == [f"ferramenta_{i}" for i in range(6)]

    def test_excluded_tools_are_dropped(self):
        from types import SimpleNamespace

        tools = [
            SimpleNamespace(nome="abrir_no_navegador"),
            SimpleNamespace(nome="pesquisar_web"),
            SimpleNamespace(nome="gerar_grafico"),
            SimpleNamespace(nome="executar_codigo"),
        ]
        out = apply_model_tool_policy(tools, "llama3.2-3b-q5km")
        names = {t.nome for t in out}
        assert "abrir_no_navegador" not in names
        assert "gerar_grafico" not in names
        assert "pesquisar_web" in names
        assert "executar_codigo" in names

    def test_cap_applied_after_exclusions(self):
        tools = self._tools(20)
        out = apply_model_tool_policy(tools, "gemma3-4b-q4km")  # tool_limit=6
        assert len(out) == 6

    def test_strong_model_keeps_full_toolset(self):
        tools = self._tools(30)
        out = apply_model_tool_policy(tools, "qwen3-8b-q4km")  # no cap
        assert len(out) == 30


class TestModelRuntimeDefaults:
    """Improvement #4b: per-model n_ctx / n_gpu_layers defaults."""

    def test_known_model_returns_full_overrides(self):
        n_ctx, n_gpu = model_runtime_defaults("qwen2.5-vl-7b-q4km")
        assert n_ctx == 16384
        assert n_gpu == -1

    def test_partial_overrides(self):
        n_ctx, n_gpu = model_runtime_defaults("qwen2.5-3b-q8")
        assert n_ctx == 8192
        assert n_gpu is None

    def test_unknown_model_returns_none(self):
        assert model_runtime_defaults("modelo-desconhecido") == (None, None)


class TestModelStartKwargs:
    """Improvement #4c: merged start kwargs for startup sites."""

    def test_profile_full_overrides_settings(self, monkeypatch):
        settings = _router_settings(model=SimpleNamespace(num_ctx=2048, n_gpu_layers=0))
        monkeypatch.setattr("core.model_router.get_settings", lambda: settings)
        kwargs = model_start_kwargs("qwen3-8b-q4km")
        assert kwargs == {"n_ctx": 16384, "n_gpu_layers": -1}

    def test_partial_profile_keeps_only_defined_keys(self, monkeypatch):
        settings = _router_settings(model=SimpleNamespace(num_ctx=2048, n_gpu_layers=0))
        monkeypatch.setattr("core.model_router.get_settings", lambda: settings)
        kwargs = model_start_kwargs("qwen2.5-3b-q8")
        assert kwargs == {"n_ctx": 8192}

    def test_unknown_model_falls_back_to_settings(self, monkeypatch):
        settings = _router_settings(model=SimpleNamespace(num_ctx=4096, n_gpu_layers=2))
        monkeypatch.setattr("core.model_router.get_settings", lambda: settings)
        assert model_start_kwargs("modelo-desconhecido") == {
            "n_ctx": 4096,
            "n_gpu_layers": 2,
        }

    def test_unknown_model_without_settings_keeps_empty(self, monkeypatch):
        monkeypatch.setattr("core.model_router.get_settings", lambda: _router_settings())
        assert model_start_kwargs("modelo-desconhecido") == {}


class TestMultiModelManagerRuntimeOptions:
    """Improvement #4b: get_manager loads each model with its profile params."""

    def _capturing_manager(self, monkeypatch, settings):
        from core.model_router import MultiModelManager

        monkeypatch.setattr("core.model_router.get_settings", lambda: settings)
        mm = MultiModelManager.__new__(MultiModelManager)
        mm.main_manager = _CapturingFakeLlamaManager()
        mm.fast_manager = _FakeLlamaManager()
        mm.router = ModelRouter()
        mm._current_complexity = None
        mm._last_decision = None
        mm._active_model_id = None
        mm._pending_ideal_model = None
        return mm

    def test_per_model_n_ctx_used_from_profile(self, monkeypatch):
        settings = _router_settings()
        mm = self._capturing_manager(monkeypatch, settings)
        mm.get_manager("qwen2.5-omni-7b-q4km")  # default_n_ctx=16384, n_gpu_layers=None
        _mid, kwargs = mm.main_manager.start_calls[0]
        assert kwargs.get("n_ctx") == 16384
        assert "n_gpu_layers" not in kwargs

    def test_profile_gpu_layers_used(self, monkeypatch):
        settings = _router_settings()
        mm = self._capturing_manager(monkeypatch, settings)
        mm.get_manager("qwen3-8b-q4km")  # default_n_ctx=16384, default_n_gpu_layers=-1
        _mid, kwargs = mm.main_manager.start_calls[0]
        assert kwargs.get("n_ctx") == 16384
        assert kwargs.get("n_gpu_layers") == -1

    def test_settings_fallback_for_unprofiled_model(self, monkeypatch):
        from types import SimpleNamespace

        settings = _router_settings(model=SimpleNamespace(num_ctx=4096, n_gpu_layers=2))
        mm = self._capturing_manager(monkeypatch, settings)
        mm.get_manager("modelo-desconhecido")
        _mid, kwargs = mm.main_manager.start_calls[0]
        assert kwargs.get("n_ctx") == 4096
        assert kwargs.get("n_gpu_layers") == 2

    def test_no_settings_model_keeps_start_defaults(self, monkeypatch):
        settings = _router_settings()
        mm = self._capturing_manager(monkeypatch, settings)
        mm.get_manager("modelo-desconhecido")
        _mid, kwargs = mm.main_manager.start_calls[0]
        assert kwargs == {}


class TestModelRouterCustomThresholds:
    def test_very_high_simple_threshold(self):
        router = ModelRouter(simple_threshold=-1.0)
        decision = router.route("hi")
        # With threshold at -1.0, fewer queries will be classified as SIMPLE
        assert decision.complexity != Complexity.COMPLEX

    def test_very_low_complex_threshold(self):
        router = ModelRouter(complex_threshold=-0.5)
        decision = router.route("hi")
        # With complex_threshold at -0.5, even simple queries may be MEDIUM
        assert decision.complexity in (Complexity.SIMPLE, Complexity.MEDIUM)


class TestPreWarmDeferredModel:
    """Improvement: apply the deferred model on the next fresh conversation."""

    def _pending_manager(self, monkeypatch, jev_model_id="qwen3-8b-q4km"):
        from core.decisions import ModelChoice
        from core.model_router import MultiModelManager
        from core.settings import DecisionLayerSettings

        settings = _router_settings(decision=DecisionLayerSettings(enabled=True))
        mm = _make_manager(monkeypatch, settings)
        mm._pending_ideal_model = "qwen3-8b-q4km"
        monkeypatch.setattr(
            MultiModelManager,
            "_installed_models",
            staticmethod(lambda s: _installed_examples()),
        )
        monkeypatch.setattr(
            "core.decisions.decide_llm_model",
            lambda *args, **kwargs: ModelChoice(model_id=jev_model_id, score=2.0, normalized=1.0),
        )
        monkeypatch.setattr("core.decisions.get_decision_client", lambda: None)
        return mm

    def test_fresh_conversation_applies_pending_model(self, monkeypatch):
        from core.model_router import FRESH_CONTEXT_TOKENS

        mm = self._pending_manager(monkeypatch)
        model_id, _ = mm.route_and_invoke(
            "analise profunda do codigo", est_tokens=FRESH_CONTEXT_TOKENS
        )

        assert model_id == "qwen3-8b-q4km"
        assert mm._pending_ideal_model is None
        assert mm._last_decision.reason == "prewarm"
        assert mm._last_decision.switched is True
        assert mm._last_decision.notice and "adiado" in mm._last_decision.notice

    def test_long_conversation_keeps_pending(self, monkeypatch):
        from core.model_router import FRESH_CONTEXT_TOKENS

        mm = self._pending_manager(monkeypatch)
        model_id, _ = mm.route_and_invoke(
            "analise profunda do codigo", est_tokens=FRESH_CONTEXT_TOKENS + 1
        )

        assert model_id == "qwen2.5-vl-7b-q4km"
        assert mm._pending_ideal_model == "qwen3-8b-q4km"
        assert mm._last_decision.switched is False

    def test_jev_choice_supersedes_pending_when_different(self, monkeypatch):
        mm = self._pending_manager(monkeypatch, jev_model_id="qwen2.5-vl-7b-q4km")

        model_id, _ = mm.route_and_invoke("pergunta complexa", est_tokens=0)

        assert model_id == "qwen2.5-vl-7b-q4km"
        assert mm._pending_ideal_model is None
        assert mm._last_decision.reason == "jev"

    def test_pending_applied_when_decision_disabled(self, monkeypatch):
        from core.model_router import FRESH_CONTEXT_TOKENS, MultiModelManager
        from core.settings import DecisionLayerSettings

        settings = _router_settings(decision=DecisionLayerSettings(enabled=False))
        mm = _make_manager(monkeypatch, settings)
        mm._pending_ideal_model = "qwen3-8b-q4km"
        monkeypatch.setattr(
            MultiModelManager,
            "_installed_models",
            staticmethod(lambda s: _installed_examples()),
        )

        model_id, _ = mm.route_and_invoke("oi", est_tokens=FRESH_CONTEXT_TOKENS)

        assert model_id == "qwen3-8b-q4km"
        assert mm._pending_ideal_model is None
        assert mm._last_decision.reason == "prewarm"

    def test_pending_consumed_when_already_loaded(self, monkeypatch):
        mm = self._pending_manager(monkeypatch)
        mm.main_manager = _FakeLlamaManager(current="qwen3-8b-q4km")
        mm._active_model_id = "qwen3-8b-q4km"

        model_id, _ = mm.route_and_invoke("analise profunda do codigo", est_tokens=0)

        assert model_id == "qwen3-8b-q4km"
        assert mm._pending_ideal_model is None
        assert mm._last_decision.reason != "prewarm"
        assert mm._last_decision.switched is False
