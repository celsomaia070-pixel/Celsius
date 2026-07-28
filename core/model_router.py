"""Enhanced model router with keyword-based classifier, scoring, and model cascade.

Provides query complexity classification with confidence scores, supports
model cascade (try fast model first, escalate on low quality), and logs
all routing decisions for observability.  Backward-compatible with the
existing ``get_multi_model_manager()`` API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.metrics import MetricNames, get_metrics
from core.settings import get_settings
from core.telemetry import trace_span

logger = __import__("logging").getLogger(__name__)


# ── Enums & data classes ──────────────────────────────────────


class Complexity(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass(frozen=True)
class ModelProfile:
    """Describes a model's capabilities for routing decisions."""

    name: str
    max_context: int
    supports_vision: bool = False
    supports_tools: bool = False
    speed_rating: float = 1.0  # 1.0 = fastest
    quality_rating: float = 0.5  # 0-1


@dataclass
class RoutingDecision:
    """Output of the router: which model to use, why, and with what confidence."""

    model_id: str
    complexity: Complexity
    confidence: float
    reason: str
    score: float = 0.0


# ── Model profiles (known models) ────────────────────────────

MODEL_PROFILES: dict[str, ModelProfile] = {
    "llama3.2-3b-q5km": ModelProfile(
        name="Llama 3.2 3B",
        max_context=8192,
        speed_rating=1.0,
        quality_rating=0.35,
    ),
    "qwen2.5-3b-q8": ModelProfile(
        name="Qwen2.5 3B",
        max_context=32768,
        speed_rating=0.95,
        quality_rating=0.4,
    ),
    "qwen3.5-35b-a3b-q4km": ModelProfile(
        name="Qwen3.5 35B-A3B",
        max_context=131072,
        speed_rating=0.85,
        quality_rating=0.8,
    ),
    "qwen2.5-vl-7b-q4km": ModelProfile(
        name="Qwen2.5 VL 7B",
        max_context=32768,
        supports_vision=True,
        supports_tools=True,
        speed_rating=0.7,
        quality_rating=0.75,
    ),
    "qwen2.5-vl-7b-q5km": ModelProfile(
        name="Qwen2.5 VL 7B Q5",
        max_context=32768,
        supports_vision=True,
        supports_tools=True,
        speed_rating=0.65,
        quality_rating=0.78,
    ),
    "qwen2.5-vl-7b-q6k": ModelProfile(
        name="Qwen2.5 VL 7B Q6",
        max_context=32768,
        supports_vision=True,
        supports_tools=True,
        speed_rating=0.6,
        quality_rating=0.80,
    ),
    "qwen2.5-coder-7b-q5km": ModelProfile(
        name="Qwen2.5 Coder 7B",
        max_context=32768,
        supports_tools=True,
        speed_rating=0.7,
        quality_rating=0.72,
    ),
    "qwen2.5-coder-14b-q4km": ModelProfile(
        name="Qwen2.5 Coder 14B",
        max_context=32768,
        supports_tools=True,
        speed_rating=0.5,
        quality_rating=0.82,
    ),
    "gemma3-4b-q4km": ModelProfile(
        name="Gemma 3 4B",
        max_context=131072,
        supports_vision=True,
        speed_rating=0.9,
        quality_rating=0.6,
    ),
    "qwen2.5-omni-7b-q4km": ModelProfile(
        name="Qwen2.5 Omni 7B",
        max_context=32768,
        supports_vision=True,
        speed_rating=0.7,
        quality_rating=0.7,
    ),
}


def get_model_profile(model_id: str) -> ModelProfile | None:
    """Return the profile for *model_id*, or ``None`` if unknown."""
    return MODEL_PROFILES.get(model_id)


# ── Scoring engine ────────────────────────────────────────────


@dataclass
class _ScoringWeights:
    """Tuneable weights for the scoring system."""

    query_length_short: float = -0.3
    query_length_long: float = 0.4
    keyword_match: float = 0.15
    document_presence: float = 0.5
    multi_language: float = 0.1
    question_mark: float = -0.05
    greeting: float = -0.2


_DEFAULT_WEIGHTS = _ScoringWeights()


def _compute_complexity_score(
    query: str,
    has_document: bool = False,
    weights: _ScoringWeights = _DEFAULT_WEIGHTS,
) -> tuple[float, list[str]]:
    """Return (score, [reasons]) in range roughly [-1, 1].

    score < -0.2  → simple
    -0.2 ≤ score ≤ 0.3 → medium
    score > 0.3 → complex
    """
    reasons: list[str] = []
    score = 0.0
    lower = query.lower()
    token_estimate = len(query) / 3.5

    # ── query length ──────────────────────────────────────────
    if token_estimate < 8:
        score += weights.query_length_short
        reasons.append(f"short query ({token_estimate:.0f} tokens)")
    elif token_estimate > 80:
        score += weights.query_length_long
        reasons.append(f"long query ({token_estimate:.0f} tokens)")

    # ── keyword matches ───────────────────────────────────────
    kw_score, kw_reasons = _keyword_score(lower)
    score += kw_score
    reasons.extend(kw_reasons)

    # ── document presence ─────────────────────────────────────
    if has_document:
        score += weights.document_presence
        reasons.append("document attached")

    # ── question mark ─────────────────────────────────────────
    if "?" in query:
        score += weights.question_mark
        reasons.append("question format")

    # ── greeting detection ────────────────────────────────────
    greetings = re.match(r"^(oi|olá|ola|hi|hello|hey|bom dia|boa tarde|boa noite)\b", lower)
    if greetings and token_estimate < 15:
        score += weights.greeting
        reasons.append("greeting detected")

    # clamp
    score = max(-1.0, min(1.0, score))
    return score, reasons


def _keyword_score(lower: str) -> tuple[float, list[str]]:
    """Keyword-based scoring. Returns (score_increment, reasons)."""
    score = 0.0
    reasons: list[str] = []

    # Complex patterns (positive score)
    complex_hits = 0
    for pattern, label in _COMPLEX_KEYWORDS:
        if re.search(pattern, lower):
            complex_hits += 1
            reasons.append(f"keyword: {label}")

    if complex_hits >= 3:
        score += 0.5
    elif complex_hits >= 2:
        score += 0.3
    elif complex_hits == 1:
        score += 0.15

    # Simple patterns (negative score)
    simple_hits = 0
    for pattern, label in _SIMPLE_KEYWORDS:
        if re.search(pattern, lower):
            simple_hits += 1
            reasons.append(f"keyword: {label}")

    if simple_hits >= 2 and complex_hits == 0:
        score -= 0.25
    elif simple_hits >= 1 and complex_hits == 0:
        score -= 0.1

    return score, reasons


# ── Keyword banks ─────────────────────────────────────────────

_COMPLEX_KEYWORDS: list[tuple[str, str]] = [
    (r"\b(analis[ae]|explic[ae]|compar[ae]|resum[ae]|relat[oó]rio)\b", "analysis"),
    (
        r"\b(c[oó]digo|programa|script|fun[çc][aã]o|classe|algoritmo|python|javascript|typescript)\b",
        "code",
    ),
    (r"\b(pesquisar|buscar|navegar|indexar|extrair)\b", "tool-use"),
    (r"\b(documento|pdf|arquivo|imagem|audio|anexo)\b", "document"),
    (r"\b(passo a passo|detalhadamente|completo|minuciosamente)\b", "detailed"),
    (r"\b(fazer|criar|gerar)\s+(um\s+)?(relat[oó]rio|relatório)\b", "report"),
    (r"\b(entender|compreender)\s+(como|o\s+que|por\s+que|por\s+que)\b", "understand"),
    (r"\b(preco|noticia|noticias|atual|hoje|agora|ultim[ao])\b", "realtime"),
    (r"\b(debug|depurar|erro|exception|stacktrace|traceback)\b", "debug"),
    (r"\b(refactor|refatorar|otimizar|performance|complexidade)\b", "refactor"),
    (r"\b(teste|test|unittest|pytest|assert|validar)\b", "testing"),
    (r"\b(soma|media|mediana|desvio|variancia|correlacao|regressao|estatistic)\b", "statistics"),
    (r"\b(grafico|chart|plot|visualiz|dashboard)\b", "visualization"),
]

_SIMPLE_KEYWORDS: list[tuple[str, str]] = [
    (r"^(oi|ola|hi|hello|hey|obrigad|valeu|thanks)\b", "greeting"),
    (r"^\w+\s*\?$", "single-question"),
    (r"\b(qual|quem|onde|quando|quantos?|quantas?)\b", "wh-question"),
    (r"\b(definicao|definição|significado|o que (e|é))\b", "definition"),
]


# ── ModelRouter ───────────────────────────────────────────────


@dataclass
class ModelRouter:
    """Routes queries to appropriate model based on complexity.

    Features:
    - Keyword-based classifier (enhanced from original)
    - Numeric complexity score with confidence
    - Model cascade support (try fast, escalate if quality low)
    - Decision logging for observability
    """

    simple_threshold: float = -0.2
    complex_threshold: float = 0.3
    cascade_enabled: bool = True
    cascade_min_confidence: float = 0.6

    def classify_complexity(
        self,
        query: str,
        has_document: bool = False,
    ) -> Complexity:
        """Return ``SIMPLE``, ``MEDIUM``, or ``COMPLEX``."""
        decision = self.route(query, has_document)
        return decision.complexity

    def route(
        self,
        query: str,
        has_document: bool = False,
    ) -> RoutingDecision:
        """Full routing decision with score and confidence."""
        metrics = get_metrics()

        with trace_span("model_router.route"):
            settings = get_settings()
            score, reasons = _compute_complexity_score(query, has_document)

            if score < self.simple_threshold:
                complexity = Complexity.SIMPLE
            elif score > self.complex_threshold:
                complexity = Complexity.COMPLEX
            else:
                complexity = Complexity.MEDIUM

            # Confidence: how far from the decision boundary
            if complexity == Complexity.SIMPLE:
                confidence = min(1.0, (self.simple_threshold - score + 0.5) / 0.5)
            elif complexity == Complexity.COMPLEX:
                confidence = min(1.0, (score - self.complex_threshold + 0.5) / 0.5)
            else:
                confidence = 0.5

            confidence = max(0.1, min(1.0, confidence))

            # Pick model
            if complexity == Complexity.SIMPLE:
                model_id = getattr(settings, "fast_llm_model", "llama3.2-3b-q5km")
            else:
                model_id = settings.llm_model

            reason = "; ".join(reasons) if reasons else "default routing"

            decision = RoutingDecision(
                model_id=model_id,
                complexity=complexity,
                confidence=confidence,
                reason=reason,
                score=score,
            )

            logger.info(
                "Routing decision: model=%s complexity=%s confidence=%.2f score=%.2f reason=%s",
                decision.model_id,
                decision.complexity.value,
                decision.confidence,
                decision.score,
                decision.reason,
            )
            metrics.inc(
                MetricNames.LLM_REQUESTS_TOTAL,
                model=decision.model_id,
                complexity=decision.complexity.value,
            )

            return decision

    def route_with_cascade(
        self,
        query: str,
        has_document: bool = False,
        available_models: list[str] | None = None,
    ) -> list[RoutingDecision]:
        """Return an ordered list of models to try (cascade).

        The first entry is always the primary pick.  Subsequent entries
        are escalation candidates in quality-descending order.  The caller
        decides when to escalate based on response quality heuristics.
        """
        primary = self.route(query, has_document)
        cascade: list[RoutingDecision] = [primary]

        if not self.cascade_enabled or primary.confidence >= self.cascade_min_confidence:
            return cascade

        # Low confidence → suggest escalation
        settings = get_settings()
        models = available_models or [settings.llm_model, getattr(settings, "fast_llm_model", "")]
        profiles = [
            (mid, MODEL_PROFILES.get(mid)) for mid in models if mid and mid != primary.model_id
        ]

        # Sort by quality_rating descending
        profiles.sort(key=lambda x: x[1].quality_rating if x[1] else 0, reverse=True)

        for mid, profile in profiles:
            cascade.append(
                RoutingDecision(
                    model_id=mid,
                    complexity=primary.complexity,
                    confidence=primary.confidence,
                    reason=f"cascade escalation (quality_rating={profile.quality_rating:.2f})"
                    if profile
                    else "cascade fallback",
                    score=primary.score,
                )
            )

        return cascade

    def get_profile(self, model_id: str) -> ModelProfile | None:
        """Get capability profile for a model."""
        return get_model_profile(model_id)

    def get_model_for_query(self, query: str, has_document: bool = False) -> str:
        """Legacy API: return just the model_id string."""
        return self.route(query, has_document).model_id


# ── MultiModelManager (backward compatible) ───────────────────


class MultiModelManager:
    """Manages multiple models with lazy loading.

    Drop-in replacement for the original class in ``core.llama_cpp``.
    """

    def __init__(self) -> None:
        from core.llama_cpp import LlamaManager, get_llama_manager

        self.main_manager = get_llama_manager()
        self.fast_manager = LlamaManager()
        self.router = ModelRouter()
        self._current_complexity: Complexity | None = None
        self._last_decision: RoutingDecision | None = None

    def get_manager(self, model_id: str) -> Any:
        """Get the appropriate LlamaManager for a model ID."""

        settings = get_settings()
        if model_id == getattr(settings, "fast_llm_model", None):
            if self.fast_manager._started:
                return self.fast_manager
            return self.main_manager
        return self.main_manager

    def route_and_invoke(
        self,
        query: str,
        has_document: bool = False,
        **kwargs: Any,
    ) -> tuple[str, Any]:
        """Route query to appropriate model and return (model_id, manager)."""
        decision = self.router.route(query, has_document)
        manager = self.get_manager(decision.model_id)
        self._current_complexity = decision.complexity
        self._last_decision = decision
        return decision.model_id, manager

    def get_current_complexity(self) -> str | None:
        """Get the last classification result as a string."""
        if self._current_complexity is not None:
            return self._current_complexity.value
        return None

    def get_last_decision(self) -> RoutingDecision | None:
        """Get the full routing decision from the last call."""
        return self._last_decision


# ── Module-level singleton ────────────────────────────────────

_multi_manager: MultiModelManager | None = None


def get_multi_model_manager() -> MultiModelManager:
    """Get singleton multi-model manager (backward compatible)."""
    global _multi_manager
    if _multi_manager is None:
        _multi_manager = MultiModelManager()
    return _multi_manager
