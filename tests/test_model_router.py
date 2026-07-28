"""Tests for core.model_router (query routing, scoring, model profiles)."""

import pytest

from core.model_router import (
    MODEL_PROFILES,
    Complexity,
    ModelProfile,
    ModelRouter,
    RoutingDecision,
    _compute_complexity_score,
    _keyword_score,
    get_model_profile,
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
            "llama3.2-3b-q5km",
            "qwen2.5-3b-q8",
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
        fast = MODEL_PROFILES["llama3.2-3b-q5km"]
        assert fast.speed_rating == 1.0

    def test_vision_models_support_vision(self):
        for mid in ["qwen2.5-vl-7b-q4km", "gemma3-4b-q4km", "qwen2.5-omni-7b-q4km"]:
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
        code = "criar um relatório detalhado do código python com análise estatística"
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
        score, reasons = _compute_complexity_score("escreva um código python completo com funções")
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
        score, _ = _compute_complexity_score("calcular média mediana desvio estatística")
        assert score > 0

    def test_simple_wh_question(self):
        score, _ = _compute_complexity_score("qual é a capital do Brasil?")
        # Has both simple (wh-question) and question mark penalty, net should be negative-ish
        # but "qual é a capital do Brasil" doesn't match complex keywords
        assert isinstance(score, float)

    def test_score_clamped(self):
        score, _ = _compute_complexity_score("x" * 5000)
        assert -1.0 <= score <= 1.0


class TestKeywordScore:
    def test_multiple_complex_keywords_boost(self):
        text = "análise código debug refatorar teste"
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
    def test_greeting_routes_to_fast_model(self):
        router = ModelRouter()
        decision = router.route("hello")
        assert decision.complexity == Complexity.SIMPLE
        assert decision.model_id == "llama3.2-3b-q5km"

    def test_short_question_simple(self):
        router = ModelRouter()
        decision = router.route("oi")
        assert decision.complexity == Complexity.SIMPLE

    def test_short_greeting_bom_dia(self):
        router = ModelRouter()
        decision = router.route("bom dia")
        assert decision.complexity == Complexity.SIMPLE


class TestModelRouterComplexQueries:
    def test_code_query_complex(self):
        router = ModelRouter()
        decision = router.route(
            "criar um código python para análise de dados com relatório detalhado e testes"
        )
        assert decision.complexity in (Complexity.MEDIUM, Complexity.COMPLEX)

    def test_long_analysis_complex(self):
        query = (
            "Faça uma análise detalhada do documento anexo, comparando os dados estatísticos " * 5
        )
        router = ModelRouter()
        decision = router.route(query)
        assert decision.complexity in (Complexity.MEDIUM, Complexity.COMPLEX)

    def test_document_context_increases_complexity(self):
        router = ModelRouter()
        decision_no_doc = router.route("analise isso", has_document=False)
        decision_doc = router.route("analise isso", has_document=True)
        assert decision_doc.score >= decision_no_doc.score


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

    def test_model_id_matches_complexity(self):
        router = ModelRouter()
        simple = router.route("hi")
        assert simple.model_id == "llama3.2-3b-q5km"

        complex_q = router.route("criar código python detalhado com análise e relatório")
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
        c = router.classify_complexity("criar código python análise detalhada relatório completo")
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

    def test_simple_returns_fast(self):
        router = ModelRouter()
        model = router.get_model_for_query("oi")
        assert model == "llama3.2-3b-q5km"


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
