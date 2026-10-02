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
from core.model_catalog import (
    DEFAULT_LLM_MODEL,
    VISION_LLM_MODEL,
)
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
    tool_limit: int | None = None  # caps schemas sent; None = no cap
    excluded_tools: tuple[str, ...] = ()  # tools this model must never receive
    default_n_ctx: int | None = None  # recommended context size for this model
    default_n_gpu_layers: int | None = None  # recommended GPU offload for this model


@dataclass
class RoutingDecision:
    """Output of the router: which model to use, why, and with what confidence."""

    model_id: str
    complexity: Complexity
    confidence: float
    reason: str
    score: float = 0.0
    switched: bool = True
    deferred_model_id: str | None = None
    notice: str | None = None


# Conversation is "fresh" (safe to swap the loaded model without meaningful
# context loss) while its history stays below this many estimated tokens.
FRESH_CONTEXT_TOKENS = 1200


# ── Model profiles (known models) ────────────────────────────

MODEL_PROFILES: dict[str, ModelProfile] = {
    "qwen3-8b-q4km": ModelProfile(
        name="Qwen3 8B Instruct",
        max_context=131072,
        supports_tools=True,
        speed_rating=0.78,
        quality_rating=0.78,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "qwen3-14b-q4km": ModelProfile(
        name="Qwen3 14B Instruct",
        max_context=131072,
        supports_tools=True,
        speed_rating=0.48,
        quality_rating=0.88,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "qwen2.5-vl-3b-q4km": ModelProfile(
        name="Qwen2.5 VL 3B",
        max_context=32768,
        supports_vision=True,
        supports_tools=True,
        speed_rating=0.88,
        quality_rating=0.65,
        tool_limit=8,
    ),
    "deepseek-r1-distill-qwen-7b-q4km": ModelProfile(
        name="DeepSeek R1 Distill Qwen 7B",
        max_context=32768,
        supports_tools=True,
        speed_rating=0.58,
        quality_rating=0.82,
        tool_limit=10,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "deepseek-r1-distill-qwen-14b-q4km": ModelProfile(
        name="DeepSeek R1 Distill Qwen 14B",
        max_context=32768,
        supports_tools=True,
        speed_rating=0.38,
        quality_rating=0.9,
        tool_limit=10,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "llama3.2-3b-q5km": ModelProfile(
        name="Llama 3.2 3B",
        max_context=8192,
        speed_rating=1.0,
        quality_rating=0.35,
        tool_limit=6,
        excluded_tools=("abrir_no_navegador", "gerar_grafico"),
        default_n_ctx=8192,
    ),
    "qwen2.5-3b-q8": ModelProfile(
        name="Qwen2.5 3B",
        max_context=32768,
        speed_rating=0.95,
        quality_rating=0.4,
        tool_limit=6,
        excluded_tools=("abrir_no_navegador", "gerar_grafico"),
        default_n_ctx=8192,
    ),
    "qwen3.5-35b-a3b-q4km": ModelProfile(
        name="Qwen3.5 35B-A3B",
        max_context=131072,
        speed_rating=0.85,
        quality_rating=0.8,
        tool_limit=12,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "qwen2.5-vl-7b-q4km": ModelProfile(
        name="Qwen2.5 VL 7B",
        max_context=32768,
        supports_vision=True,
        supports_tools=True,
        speed_rating=0.7,
        quality_rating=0.75,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "qwen2.5-vl-7b-q5km": ModelProfile(
        name="Qwen2.5 VL 7B Q5",
        max_context=32768,
        supports_vision=True,
        supports_tools=True,
        speed_rating=0.65,
        quality_rating=0.78,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "qwen2.5-vl-7b-q6k": ModelProfile(
        name="Qwen2.5 VL 7B Q6",
        max_context=32768,
        supports_vision=True,
        supports_tools=True,
        speed_rating=0.6,
        quality_rating=0.80,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "qwen2.5-coder-7b-q5km": ModelProfile(
        name="Qwen2.5 Coder 7B",
        max_context=32768,
        supports_tools=True,
        speed_rating=0.7,
        quality_rating=0.72,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "qwen2.5-coder-14b-q4km": ModelProfile(
        name="Qwen2.5 Coder 14B",
        max_context=32768,
        supports_tools=True,
        speed_rating=0.5,
        quality_rating=0.82,
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "gemma3-4b-q4km": ModelProfile(
        name="Gemma 3 4B",
        max_context=131072,
        supports_vision=True,
        speed_rating=0.9,
        quality_rating=0.6,
        tool_limit=6,
        excluded_tools=("abrir_no_navegador",),
        default_n_ctx=16384,
        default_n_gpu_layers=-1,
    ),
    "qwen2.5-omni-7b-q4km": ModelProfile(
        name="Qwen2.5 Omni 7B",
        max_context=32768,
        supports_vision=True,
        speed_rating=0.7,
        quality_rating=0.7,
        tool_limit=8,
        default_n_ctx=16384,
    ),
}


def get_model_profile(model_id: str) -> ModelProfile | None:
    """Return the profile for *model_id*, or ``None`` if unknown."""
    return MODEL_PROFILES.get(model_id)


def model_runtime_defaults(model_id: str) -> tuple[int | None, int | None]:
    """Return the per-model recommended ``(n_ctx, n_gpu_layers)``.

    Either value may be ``None``, meaning "use the caller-provided default".
    """
    profile = MODEL_PROFILES.get(model_id)
    if profile is None:
        return None, None
    return profile.default_n_ctx, profile.default_n_gpu_layers


def model_start_kwargs(model_id: str) -> dict[str, Any]:
    """Resolve the runtime kwargs for *model_id* (``n_ctx`` / ``n_gpu_layers``).

    Per-model profile defaults win when defined; otherwise the global
    ``settings.model`` values are used. Mirrors ``get_manager`` semantics so
    startup and hot-swap agree on the model's context/layers.
    """
    n_ctx, n_gpu_layers = model_runtime_defaults(model_id)
    start_kwargs: dict[str, Any] = {}
    if n_ctx is not None:
        start_kwargs["n_ctx"] = n_ctx
    if n_gpu_layers is not None:
        start_kwargs["n_gpu_layers"] = n_gpu_layers
    if start_kwargs:
        return start_kwargs
    cfg = getattr(get_settings(), "model", None)
    if cfg is not None:
        if getattr(cfg, "num_ctx", None):
            start_kwargs["n_ctx"] = cfg.num_ctx
        if getattr(cfg, "n_gpu_layers", None) is not None:
            start_kwargs["n_gpu_layers"] = cfg.n_gpu_layers
    return start_kwargs


def apply_model_tool_policy(tools: list[Any], model_id: str) -> list[Any]:
    """Trim tool schemas to what *model_id* can handle reliably.

    Uses the model profile to drop excluded tools and cap the total number
    of schemas sent to the model (small/reasoning models degrade when forced
    to choose among many tools). Unknown models are returned unchanged.
    """
    profile = MODEL_PROFILES.get(model_id)
    if profile is None:
        return tools
    if profile.excluded_tools:
        excluded = set(profile.excluded_tools)
        tools = [t for t in tools if getattr(t, "nome", None) not in excluded]
    if profile.tool_limit is not None and len(tools) > profile.tool_limit:
        tools = tools[: profile.tool_limit]
    return tools


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

_DEEP_ANALYSIS_KEYWORDS: list[tuple[str, str]] = [
    (r"\b(estrategia|estrategico|planejamento|viabilidade|cenario|cenarios)\b", "strategy"),
    (r"\b(raciocine|analise profunda|pensamento profundo|decisao|decidir)\b", "deep-reasoning"),
    (r"\b(financeiro|fluxo de caixa|margem|lucro|prejuizo|investimento)\b", "business-finance"),
    (r"\b(comparar fornecedores|otimizar compras|previsao|projecao)\b", "business-planning"),
]

_VISION_KEYWORDS: list[tuple[str, str]] = [
    (r"\b(imagem|foto|print|screenshot|nota fiscal|scan|escaneado)\b", "image"),
    (r"\b(tabela no pdf|layout|grafico no documento|documento visual)\b", "visual-document"),
]

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


def _has_keyword(lower: str, keywords: list[tuple[str, str]]) -> bool:
    return any(re.search(pattern, lower) for pattern, _label in keywords)


def _needs_vision_model(has_image: bool) -> bool:
    """Use a vision model only when pixels will actually be sent to it."""
    return has_image


def _needs_reasoning_model(lower: str) -> bool:
    return _has_keyword(lower, _DEEP_ANALYSIS_KEYWORDS)


def _model_file_exists(settings: Any, model_id: str) -> bool:
    try:
        return bool(settings.get_model_path(model_id).exists())
    except Exception:
        return False


def _available_model_id(settings: Any, preferred_model_id: str) -> str:
    fallback_ids = [
        getattr(settings, "llm_model", ""),
        getattr(settings, "default_llm_model", DEFAULT_LLM_MODEL),
        DEFAULT_LLM_MODEL,
    ]
    candidates = [preferred_model_id, *fallback_ids]
    seen: set[str] = set()
    for model_id in candidates:
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        if _model_file_exists(settings, model_id):
            return model_id
    return preferred_model_id


_FAST_MODEL_MISSING_WARNED = False


def _warn_once_fast_model_missing(preferred: str, resolved: str) -> None:
    global _FAST_MODEL_MISSING_WARNED
    if _FAST_MODEL_MISSING_WARNED:
        return
    _FAST_MODEL_MISSING_WARNED = True
    logger.warning(
        "Modelo rapido %s nao esta baixado; queries simples usarao %s (mais lento). "
        "Baixe o %s na selecao de modelos para acelerar respostas simples.",
        preferred,
        resolved,
        preferred,
    )


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
        has_image: bool = False,
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

            # Celsius runs with a SINGLE LLM: qwen2.5-vl-7b.
            # Complexity / fast / quality / reasoning escalation is intentionally
            # disabled so only ONE model is ever loaded into GPU memory
            # (fits the 8 GB RX 7600; no spill to CPU, no second manager).
            settings = get_settings()
            model_id = settings.llm_model or getattr(settings, "vision_llm_model", VISION_LLM_MODEL)
            resolved_model_id = _available_model_id(settings, model_id)
            model_id = resolved_model_id

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
        has_image: bool = False,
        available_models: list[str] | None = None,
    ) -> list[RoutingDecision]:
        """Return an ordered list of models to try (cascade).

        The first entry is always the primary pick.  Subsequent entries
        are escalation candidates in quality-descending order.  The caller
        decides when to escalate based on response quality heuristics.
        """
        primary = self.route(query, has_document, has_image)
        cascade: list[RoutingDecision] = [primary]

        # Celsius runs with a SINGLE LLM (qwen2.5-vl-7b): escalation to
        # fast/quality/reasoning cascades is intentionally disabled so a
        # second model is never started (avoids VRAM spill to CPU).
        return cascade

    def get_profile(self, model_id: str) -> ModelProfile | None:
        """Get capability profile for a model."""
        return get_model_profile(model_id)

    def get_model_for_query(
        self,
        query: str,
        has_document: bool = False,
        has_image: bool = False,
    ) -> str:
        """Legacy API: return just the model_id string."""
        return self.route(query, has_document, has_image).model_id


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
        self._active_model_id: str | None = None
        self._pending_ideal_model: str | None = None

    def get_manager(self, model_id: str) -> Any:
        """Get the appropriate LlamaManager for a model ID.

        Lazily starts the fast model when routing to it and the file exists.
        Any other model (e.g. picked by JEV or pinned by the client) is loaded
        on the main manager, replacing the previous model. Falls back to the
        currently loaded model on failure so inferencing still works.
        """
        settings = get_settings()
        start_kwargs = model_start_kwargs(model_id)

        if model_id == getattr(settings, "fast_llm_model", None):
            if self.fast_manager._started:
                return self.fast_manager
            try:
                if self.fast_manager.start(model_id=model_id, **start_kwargs):
                    return self.fast_manager
            except Exception as exc:
                logger.warning(
                    "Nao foi possivel iniciar o modelo rapido %s (%s); usando o modelo principal.",
                    model_id,
                    exc,
                )
            return self.main_manager

        main = self.main_manager
        try:
            needs_start = not main._started or main.current_model_id != model_id
            if needs_start and main.start(model_id=model_id, **start_kwargs):
                return main
        except Exception as exc:
            logger.warning(
                "Nao foi possivel carregar %s; mantendo o modelo carregado (%s).",
                model_id,
                exc,
            )
        return main

    def route_and_invoke(
        self,
        query: str,
        has_document: bool = False,
        has_image: bool = False,
        *,
        est_tokens: int = 0,
        **kwargs: Any,
    ) -> tuple[str, Any]:
        """Pick the LLM and return (model_id, manager).

        Decision precedence:
        1. the client pinned a specific model in the UI (``model_client_choice``);
        2. JEV picks among the downloaded models (when the decision layer is
           enabled and ``model_routing`` is on);
        3. the keyword router (fast vs. main model) as before.

        The picked model is only actually loaded when it differs from the model
        already active on the main manager AND the swap is safe for the current
        conversation (``est_tokens`` below ``FRESH_CONTEXT_TOKENS``), the client
        pinned it, or the current model lacks a capability the message requires
        (e.g. an image without vision). Otherwise the current model is kept and
        the ideal one stays pending for the next fresh conversation.
        """
        settings = get_settings()
        base = self.router.route(query, has_document, has_image)

        picked_id = base.model_id
        reason = "auto"
        if getattr(settings, "model_client_choice", False) and settings.llm_model:
            picked_id = settings.llm_model
            reason = "client"
        else:
            decision = getattr(settings, "decision", None)
            if decision is not None and decision.enabled and decision.model_routing:
                candidates = self._installed_models(settings)
                if len(candidates) >= 2:
                    from core.decisions import decide_llm_model, get_decision_client

                    try:
                        picked = decide_llm_model(
                            get_decision_client(),
                            decision,
                            query=query,
                            models=candidates,
                            has_document=has_document,
                            has_image=has_image,
                        )
                    except Exception as exc:  # noqa: BLE001 - nunca derruba o fluxo
                        logger.warning("JEV model routing falhou: %s", exc)
                        picked = None
                    if picked is not None and picked.model_id in self._installed_ids(settings):
                        picked_id = picked.model_id
                        reason = "jev"

        current_id = self._active_model_id or getattr(self.main_manager, "current_model_id", None)

        # Pre-warm: apply a model that was deferred (kept to preserve context)
        # the moment a fresh conversation makes the swap safe. When the JEV or
        # the router re-picked the same model, the swap is recorded as
        # "prewarm"; a newer pick for a *different* model supersedes the stale
        # pending one. A client pin always wins over the pending model.
        pending = self._pending_ideal_model
        if (
            pending is not None
            and pending in self._installed_ids(settings)
            and est_tokens <= FRESH_CONTEXT_TOKENS
        ):
            if reason == "client":
                self._pending_ideal_model = None
            elif picked_id == pending:
                self._pending_ideal_model = None
                if pending != current_id:
                    reason = "prewarm"
            elif reason == "auto":
                self._pending_ideal_model = None
                if pending != current_id:
                    picked_id = pending
                    reason = "prewarm"
            else:
                self._pending_ideal_model = None

        model_id, switched, deferred_id, notice = self._apply_switch_policy(
            current_id,
            picked_id,
            reason,
            est_tokens=est_tokens,
            has_image=has_image,
        )
        if deferred_id is not None:
            self._pending_ideal_model = deferred_id

        manager = self.get_manager(model_id)
        self._active_model_id = model_id
        self._current_complexity = base.complexity
        self._last_decision = RoutingDecision(
            model_id=model_id,
            complexity=base.complexity,
            confidence=base.confidence,
            reason=reason,
            score=base.score,
            switched=switched,
            deferred_model_id=deferred_id,
            notice=notice,
        )
        return model_id, manager

    def _apply_switch_policy(
        self,
        current_id: str | None,
        picked_id: str,
        reason: str,
        *,
        est_tokens: int,
        has_image: bool,
    ) -> tuple[str, bool, str | None, str | None]:
        """Decide whether to swap the loaded model to ``picked_id``.

        Swapping destroys the KV-cache/context, so it only happens for short
        conversations (``est_tokens`` at or below ``FRESH_CONTEXT_TOKENS``),
        when the client pinned a model, or when the current model cannot handle
        a capability the message requires. Otherwise keep the current model and
        remember the ideal one for a future fresh conversation.
        """
        if picked_id == current_id or current_id is None:
            return picked_id, False, None, None

        if reason == "client":
            return picked_id, True, None, None

        if reason == "prewarm":
            notice = (
                f"Apliquei o modelo adiado ({picked_id}): a conversa nova "
                "esta curta, entao troquei sem perder contexto."
            )
            return picked_id, True, None, notice

        if has_image and not self._supports_vision(current_id) and self._supports_vision(picked_id):
            notice = (
                f"Troquei para {picked_id}: a pergunta usa imagem e o modelo "
                "atual nao possui visao."
            )
            return picked_id, True, None, notice

        if est_tokens <= FRESH_CONTEXT_TOKENS:
            notice = (
                f"Troquei para {picked_id}. A conversa era curta e o contexto "
                "foi reiniciado para este modelo."
            )
            return picked_id, True, None, notice

        notice = (
            f"O JEV sugeriu '{picked_id}', mas mantive '{current_id}' para "
            "preservar o contexto desta conversa. O novo modelo sera aplicado "
            "na proxima conversa ou se voce escolher manualmente no seletor."
        )
        return current_id, False, picked_id, notice

    @staticmethod
    def _supports_vision(model_id: str) -> bool:
        """Heuristic capability check, tolerant of unknown/renamed model IDs."""
        profile = MODEL_PROFILES.get(model_id)
        if profile is not None:
            return profile.supports_vision
        lowered = model_id.lower()
        return "vl" in lowered or "vision" in lowered

    @staticmethod
    def _installed_models(settings: Any) -> list[Any]:
        from core.config import discover_installed_models

        dirs = [settings.get_resources_dir()]
        bundled = getattr(settings, "bundled_resources_dir", None)
        if bundled is not None and bundled.is_dir():
            dirs.append(bundled)
        return discover_installed_models(*dirs)

    @staticmethod
    def _installed_ids(settings: Any) -> set[str]:
        return {m.id for m in MultiModelManager._installed_models(settings)}

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
