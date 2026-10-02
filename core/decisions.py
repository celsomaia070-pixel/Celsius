"""Decision layer for Celsius (Jev-style "System One" contracts).

A thin, provider-agnostic wrapper around local decision models (e.g. Kev,
``kev.serve`` at http://127.0.0.1:8009). It speaks the TypeSafe ``/v1/systemone``
wire format but never depends on their cloud API: the provider address is
configurable and 100% local by default.

Design rules:

* When the layer is disabled (``DecisionLayerSettings.enabled=False``) every call
  returns an empty result tagged with ``provider="off"`` immediately, so
  upstream code keeps its exact current behavior.
* On any provider error/timeout the client degrades to an empty result tagged
  with ``provider="fallback"`` instead of raising, so integrations never break
  when the local model server is down. Repeated failures are throttled so one
  missing server cannot flood the log.
* The gates express a "keep the current behavior, only add approval above a
  threshold" posture. The **mandatory** confirmations live in
  ``core.tool_policy``; this layer can only add more, never remove.
* A probabilistic model does not eliminate hallucinations. Every answer here is
  a *structured decision with a probability/confidence* that callers must
  validate; nothing in this module is treated as ground truth.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from core.decision_calibration import (
    DecisionRecorder,
    _now_iso,
    default_outcomes_path,
    load_outcomes,
)
from core.metrics import MetricNames, get_metrics
from core.settings import DecisionLayerSettings, get_settings
from core.tool_policy import (
    ToolGuardDecision,
    assess_tool,
    summarize_arguments,
)

logger = logging.getLogger(__name__)

#: Consecutive failures logged at WARNING before we drop to DEBUG for a while.
_FAILURE_LOG_WINDOW_SECONDS = 120.0

#: Upper bound on models scored in one routing pass (one cheap JEV round trip).
MAX_ROUTE_CANDIDATES = 6


# ── Question types ──────────────────────────────────────────


@dataclass(frozen=True)
class NoulQuestion:
    """Yes/no decision: returns the probability of 'yes'."""

    instructions: str | None = None

    @property
    def type(self) -> str:
        return "noul"

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": "noul"}
        if self.instructions:
            payload["instructions"] = self.instructions
        return payload


@dataclass(frozen=True)
class ChoiceQuestion:
    """Pick one of several options."""

    criteria: Mapping[str, str | None] = field(default_factory=dict)
    instructions: str | None = None

    @property
    def type(self) -> str:
        return "choice"

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": "choice"}
        if self.instructions:
            payload["instructions"] = self.instructions
        payload["criteria"] = dict(self.criteria)
        return payload


@dataclass(frozen=True)
class ScoreQuestion:
    """Rate on an ordered scale (level indices start at 0)."""

    criteria: Sequence[str] = field(default_factory=list)
    instructions: str | None = None

    @property
    def type(self) -> str:
        return "score"

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": "score"}
        if self.instructions:
            payload["instructions"] = self.instructions
        payload["criteria"] = list(self.criteria)
        return payload


Question: TypeAlias = NoulQuestion | ChoiceQuestion | ScoreQuestion


@dataclass(frozen=True)
class DecisionRequest:
    """One decision pass: shared state plus one or more questions."""

    state: str | Mapping[str, str]
    questions: Mapping[str, Question]


# ── Answer types ────────────────────────────────────────────


@dataclass(frozen=True)
class NoulAnswer:
    type: str = "noul"
    noul: float = 0.0


@dataclass(frozen=True)
class ChoiceAnswer:
    type: str = "choice"
    choice: str = ""
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass(frozen=True)
class ScoreAnswer:
    type: str = "score"
    score: float = 0.0
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    legend: dict[str, str] = field(default_factory=dict)


Answer: TypeAlias = NoulAnswer | ChoiceAnswer | ScoreAnswer


@dataclass(frozen=True)
class DecisionResult:
    """Output of a decision pass with provenance for observability."""

    answers: Mapping[str, Answer]
    provider: str
    model: str = ""
    elapsed_ms: float = 0.0
    outcome: str = "ok"

    @property
    def resolved(self) -> bool:
        """True when the provider returned answers that upstream code can use."""
        return self.outcome == "ok" and bool(self.answers)


@dataclass(frozen=True)
class DecisionHealth:
    """Reachability report for the local decision server.

    ``reachable`` is a transport fact, not a quality claim: a reachable kev can
    still be wrong, and its answers are always probabilities.
    """

    enabled: bool
    reachable: bool
    base_url: str
    model: str
    detail: str
    models: tuple[str, ...] = ()
    checked_at: float = 0.0
    error: str = ""

    @property
    def state(self) -> str:
        if not self.enabled:
            return "off"
        return "available" if self.reachable else "unavailable"

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "reachable": self.reachable,
            "state": self.state,
            "base_url": self.base_url,
            "model": self.model,
            "models": list(self.models),
            "detail": self.detail,
            "error": self.error,
            "checked_at": self.checked_at,
        }


def parse_answers(payload: Mapping[str, Any]) -> dict[str, Answer]:
    """Map a /v1/systemone response body onto typed answers.

    ``payload["answers"]`` maps question ids to answer objects; a missing or
    malformed answer is omitted (never raised).
    """

    def _choice(data: Mapping[str, Any]) -> ChoiceAnswer:
        return ChoiceAnswer(
            choice=str(data.get("choice", "")),
            probabilities=_rfloat_map(data.get("probabilities")),
            confidence=_coord(data.get("confidence")),
        )

    def _score(data: Mapping[str, Any]) -> ScoreAnswer:
        legend_raw = data.get("legend")
        legend = (
            {str(k): str(v) for k, v in legend_raw.items()} if isinstance(legend_raw, dict) else {}
        )
        return ScoreAnswer(
            score=_coord(data.get("score")),
            probabilities=_rfloat_map(data.get("probabilities")),
            confidence=_coord(data.get("confidence")),
            legend=legend,
        )

    def _one(qid: str, data: Any) -> Answer | None:
        if not isinstance(data, dict):
            return None
        qtype = str(data.get("type", ""))
        if qtype == "noul":
            return NoulAnswer(noul=_coord(data.get("noul")))
        if qtype == "choice":
            return _choice(data)
        if qtype == "score":
            return _score(data)
        return None

    raw = payload.get("answers")
    if not isinstance(raw, dict):
        return {}
    answers: dict[str, Answer] = {}
    for qid, data in raw.items():
        parsed = _one(str(qid), data)
        if parsed is not None:
            answers[str(qid)] = parsed
    return answers


def _coord(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _rfloat_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {str(k): _coord(v) for k, v in value.items()}


# ── Providers ───────────────────────────────────────────────


class DecisionProvider:
    """Contract implemented by decision backends.

    ``decide`` must return the typed answers or ``None`` to signal the caller
    should keep its current behavior.
    """

    def decide(self, request: DecisionRequest, *, timeout_ms: int) -> dict[str, Answer] | None:
        raise NotImplementedError


class OffProvider(DecisionProvider):
    """Provider used when the decision layer is disabled (fast no-op)."""

    def decide(self, request: DecisionRequest, *, timeout_ms: int) -> dict[str, Answer] | None:
        return None


class HttpDecisionProvider(DecisionProvider):
    """Talk to a local ``kev.serve`` (or any /v1/systemone) endpoint over HTTP."""

    def __init__(self, base_url: str = "http://127.0.0.1:8009", *, model: str = "kev-latest"):
        parsed = urllib.parse.urlsplit(base_url.rstrip("/"))
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("O servidor JEV/KEV deve usar uma URL HTTP local sem credenciais.")
        try:
            is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = parsed.hostname.casefold() == "localhost"
        if not is_loopback:
            raise ValueError("O servidor JEV/KEV deve permanecer no loopback local.")
        self._base_url = parsed.geturl().rstrip("/")
        self._model = model
        self._endpoint = f"{self._base_url}/v1/systemone"
        self._last_failure_log = 0.0
        self._consecutive_failures = 0

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def _log_failure(self, exc: BaseException) -> None:
        """Log the first failure loudly, then throttle to DEBUG.

        A stopped ``kev.serve`` must not turn every chat turn into a WARNING.
        """
        self._consecutive_failures += 1
        now = time.monotonic()
        first = self._consecutive_failures == 1
        throttled = now - self._last_failure_log < _FAILURE_LOG_WINDOW_SECONDS
        self._last_failure_log = now
        if first:
            logger.warning(
                "Jev/Kev indisponivel em %s (%s). Seguindo com as politicas "
                "deterministicas; o Celsius continua funcionando.",
                self._endpoint,
                exc,
            )
        elif not throttled:
            logger.warning(
                "Jev/Kev ainda indisponivel em %s (%s) apos %d falhas.",
                self._endpoint,
                exc,
                self._consecutive_failures,
            )
        else:
            logger.debug(
                "Jev/Kev indisponivel (%s) [%d falhas consecutivas]",
                exc,
                self._consecutive_failures,
            )

    def decide(self, request: DecisionRequest, *, timeout_ms: int) -> dict[str, Answer] | None:
        payload: dict[str, Any] = {
            "state": request.state,
            "model": self._model,
            "questions": {qid: q.to_payload() for qid, q in request.questions.items()},
        }
        body = json.dumps(payload).encode("utf-8")
        http_req = urllib.request.Request(
            self._endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = max(0.001, timeout_ms / 1000.0)
        try:
            with urllib.request.urlopen(http_req, timeout=timeout) as response:  # nosec B310
                raw = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            self._log_failure(exc)
            return None
        self._consecutive_failures = 0
        return parse_answers(raw)

    def list_models(self, *, timeout_ms: int = 1500) -> tuple[tuple[str, ...], str]:
        """Probe ``GET /v1/models``; returns ``(model_names, error)``."""
        url = f"{self._base_url}/v1/models"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(  # nosec B310 - endpoint validated as loopback HTTP
                req, timeout=max(0.001, timeout_ms / 1000.0)
            ) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            return (), f"{type(exc).__name__}: {exc}"
        items = raw.get("models") if isinstance(raw, dict) else None
        names = tuple(
            str(item.get("name"))
            for item in (items or [])
            if isinstance(item, dict) and item.get("name")
        )
        return names, ""


# ── High-level facade ───────────────────────────────────────


class DecisionClient:
    """Facade the rest of Celsius calls; degrades gracefully by design."""

    def __init__(
        self,
        settings: DecisionLayerSettings | None = None,
        *,
        provider: DecisionProvider | None = None,
        recorder: DecisionRecorder | None = None,
    ) -> None:
        self._settings = settings or DecisionLayerSettings()
        self._injected_provider = provider
        self._recorder = recorder
        self._health_cache: tuple[float, DecisionHealth] | None = None

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    def record(self, entry: dict[str, Any]) -> None:
        """Persist a decision outcome for later calibration (§9).

        Never raises and only writes when the layer is enabled and a recorder
        is attached, so recording is pure observability.
        """
        if not self.enabled or self._recorder is None:
            return
        with contextlib.suppress(Exception):
            self._recorder.append(entry)

    def health(self, *, force: bool = False) -> DecisionHealth:
        """Verify the local decision server is usable.

        Cached for ``settings.health_cache_seconds`` so the UI status indicator
        never turns into a poll loop. Never raises.
        """
        if not self._settings.enabled:
            return DecisionHealth(
                enabled=False,
                reachable=False,
                base_url=self._settings.normalized_endpoint(),
                model=self._settings.model,
                detail="Camada de decisao desativada; o Celsius usa as politicas padrao.",
            )
        now = time.monotonic()
        if not force and self._health_cache is not None:
            cached_at, cached = self._health_cache
            window = max(0.0, self._settings.health_cache_seconds)
            if now - cached_at <= window:
                return cached
        health = self._probe_health()
        self._health_cache = (now, health)
        return health

    def _probe_health(self) -> DecisionHealth:
        base_url = self._settings.normalized_endpoint()
        provider = self._injected_provider
        if isinstance(provider, HttpDecisionProvider):
            names, error = provider.list_models()
        else:
            names, error = (), ""
            if provider is not None and not isinstance(provider, OffProvider):
                # An injected fake provider cannot answer a probe; assume OK so
                # tests and offline mode are not reported as "unavailable".
                names, error = (self._settings.model,), ""
        reachable = not error
        if not reachable:
            detail = (
                f"Servidor de decisao fora do ar em {base_url} ({error}). "
                "O Celsius continua com as politicas deterministicas."
            )
        elif names and self._settings.model not in names:
            detail = (
                f"Servidor de decisao respondeu em {base_url}, mas nao anuncia o modelo "
                f"'{self._settings.model}'. Servidos: {', '.join(names)}."
            )
        else:
            detail = f"Servidor de decisao disponivel em {base_url}."
        return DecisionHealth(
            enabled=True,
            reachable=reachable,
            base_url=base_url,
            model=self._settings.model,
            models=names,
            detail=detail,
            checked_at=time.time(),
            error=error,
        )

    def make_outcome(
        self,
        *,
        kind: str,
        label: str,
        value: float,
        predicted: bool,
        **extra: Any,
    ) -> dict[str, Any]:
        """Build a uniform outcome record for the JSONL log."""
        entry: dict[str, Any] = {
            "created_at": _now_iso(),
            "kind": kind,
            "decision": label,
            "value": round(value, 4),
            "predicted": predicted,
            "provider": self._settings.provider,
            "model": self._settings.model,
        }
        entry.update(extra)
        return entry

    def decide(
        self,
        request: DecisionRequest,
        *,
        timeout_ms: int | None = None,
    ) -> DecisionResult:
        metrics = get_metrics()
        if not self.enabled:
            return DecisionResult(answers={}, provider="off", outcome="disabled")

        provider = self._injected_provider or HttpDecisionProvider(
            self._settings.base_url, model=self._settings.model
        )
        effective_timeout = timeout_ms if timeout_ms is not None else self._settings.timeout_ms
        started = time.perf_counter()
        try:
            answers = provider.decide(request, timeout_ms=effective_timeout)
        except Exception as exc:  # noqa: BLE001 - provider must never break the caller
            elapsed = (time.perf_counter() - started) * 1000.0
            logger.warning("decision provider raised: %s", exc)
            metrics.inc(MetricNames.DECISION_REQUESTS_TOTAL, status="error")
            metrics.observe(MetricNames.DECISION_LATENCY_SECONDS, elapsed / 1000.0)
            return DecisionResult(
                answers={}, provider="fallback", elapsed_ms=elapsed, outcome="error"
            )

        elapsed = (time.perf_counter() - started) * 1000.0
        metrics.observe(MetricNames.DECISION_LATENCY_SECONDS, elapsed / 1000.0)
        if answers is None:
            metrics.inc(MetricNames.DECISION_REQUESTS_TOTAL, status="fallback")
            return DecisionResult(
                answers={}, provider="fallback", elapsed_ms=elapsed, outcome="error"
            )
        metrics.inc(MetricNames.DECISION_REQUESTS_TOTAL, status="ok")
        return DecisionResult(
            answers=answers,
            provider=self._settings.provider,
            model=self._settings.model,
            elapsed_ms=elapsed,
            outcome="ok",
        )


# ── Gates ───────────────────────────────────────────────────


@dataclass(frozen=True)
class NoulGate:
    """Outcome of a noul guard for a single tool/action.

    ``requires_approval`` means "route to human approval"; ``certain`` tells
    whether the model was clearly above the threshold or inside the uncertainty
    band (escalation either way, for safety).
    """

    requires_approval: bool
    certain: bool
    probability: float


def noul_gate(
    probability: float,
    *,
    threshold: float = 0.70,
    band: float = 0.15,
) -> NoulGate:
    """Classify a noul probability against a threshold with an uncertainty band.

    Above ``threshold - band`` the answer is treated as "risky: require
    approval" (definite risk above ``threshold``, anxious-but-possible inside
    the band). This never *removes* app approvals; it can only add them.
    """
    floor = max(0.0, min(1.0, threshold - band))
    if probability >= floor:
        return NoulGate(
            requires_approval=True,
            certain=probability >= threshold,
            probability=min(1.0, max(0.0, probability)),
        )
    return NoulGate(
        requires_approval=False,
        certain=False,
        probability=min(1.0, max(0.0, probability)),
    )


@dataclass(frozen=True)
class ScoreGate:
    """Horizontal gate for RAG chunk relevance.

    ``keep`` decides whether the chunk moves on; ``normalized`` is the score on
    a 0..1 scale for logging and calibration.
    """

    keep: bool
    normalized: float


def score_gate(
    score: float,
    n_levels: int,
    *,
    threshold: float = 0.60,
    band: float = 0.05,
) -> ScoreGate:
    """Say whether a ``score`` (0-based mean level index) passes a threshold.

    Borderline values inside ``threshold - band`` are kept (pruning is
    conservative). ``n_levels`` must be >= 2.
    """
    n_levels = max(2, int(n_levels))
    normalized = score / float(n_levels - 1)
    return ScoreGate(
        keep=bool(normalized >= threshold - band),
        normalized=min(1.0, max(0.0, normalized)),
    )


def decide_tool_guard(
    client: DecisionClient,
    settings: DecisionLayerSettings,
    *,
    tool: str,
    arguments: dict[str, Any],
) -> NoulGate:
    """Ask the decision model whether one tool call must go to human approval.

    This is the *probabilistic half* of the guard only: it returns
    ``requires_approval=False`` when the layer is disabled, the provider fails or
    the answer is empty, so upstream deterministic policy is never weakened. Use
    :func:`evaluate_tool_call` for the binding verdict (policy + JEV).
    """
    if not client.enabled:
        return NoulGate(requires_approval=False, certain=False, probability=0.0)

    state = {
        "tipo_acao": tool,
        "argumentos": json.dumps(arguments, ensure_ascii=False, default=str)[:400],
    }
    questions: dict[str, Question] = {
        "altera_dados": NoulQuestion(
            "Esta acao altera, cria ou apaga dados persistidos do usuario ou empresa?"
        ),
        "irreversivel": NoulQuestion("Esta acao e irreversivel ou dificil de desfazer?"),
        "rede": NoulQuestion("Esta acao envia dados para fora do computador ou acessa a internet?"),
        "destrutiva": NoulQuestion(
            "Esta acao parece destrutiva ou perigosa para executar sem confirmacao?"
        ),
    }

    result = client.decide(
        DecisionRequest(state=state, questions=questions),
        timeout_ms=settings.timeout_ms,
    )
    if not result.resolved:
        return NoulGate(requires_approval=False, certain=False, probability=0.0)

    probs = [answer.noul for answer in result.answers.values() if isinstance(answer, NoulAnswer)]
    max_prob = max(probs) if probs else 0.0
    gate = noul_gate(
        max_prob,
        threshold=settings.guard_risk_threshold,
        band=settings.guard_uncertainty_band,
    )
    logger.info(
        "decision guard tool=%s max_prob=%.3f requires_approval=%s provider=%s",
        tool,
        gate.probability,
        gate.requires_approval,
        result.provider,
    )
    client.record(
        client.make_outcome(
            kind="tool_guard",
            label="requires_approval",
            value=gate.probability,
            predicted=gate.requires_approval,
            tool=tool,
            certain=gate.certain,
            elapsed_ms=round(result.elapsed_ms, 3),
        )
    )
    return gate


def evaluate_tool_call(
    client: DecisionClient,
    settings: DecisionLayerSettings,
    *,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> ToolGuardDecision:
    """Binding verdict for one tool call: deterministic policy + optional JEV.

    The invariant is *monotonicity*: JEV may add a confirmation, never remove
    one. A tool with no declared policy (or a policy that raises) fails closed.
    """
    args = dict(arguments or {})
    assessment = assess_tool(tool, args)
    policy_requires = assessment.requires_confirmation
    summary = summarize_arguments(args)

    if not client.enabled:
        return ToolGuardDecision(
            tool=tool,
            requires_confirmation=policy_requires,
            risk=assessment.risk,
            reason=assessment.reason,
            source="policy",
            args_summary=summary,
            assessment=assessment,
            policy_requires_confirmation=policy_requires,
        )

    gate = decide_tool_guard(client, settings, tool=tool, arguments=args)
    if gate.requires_approval:
        source = "policy+jev" if policy_requires else "jev"
    elif policy_requires:
        # Jev did not object; the deterministic policy is the binding reason.
        source = "policy"
        if client.health(force=False).state == "unavailable":
            source = "fallback"
    else:
        # Both layers agree the call is safe.
        source = "policy+jev"

    return ToolGuardDecision(
        tool=tool,
        requires_confirmation=policy_requires or gate.requires_approval,
        risk=assessment.risk,
        reason=(assessment.reason if policy_requires else "Jev sinalizou risco adicional."),
        source=source,
        probability=gate.probability,
        args_summary=summary,
        assessment=assessment,
        policy_requires_confirmation=policy_requires,
    )


@dataclass(frozen=True)
class RagGateResult:
    """Verdict for one RAG chunk.

    ``keep`` is what callers must honor. ``pruned`` is informational and is only
    ever ``True`` when pruning was explicitly enabled *and* calibrated, so
    "keep the text" stays the default posture.
    """

    keep: bool
    normalized: float = 0.0
    pruned: bool = False
    reason: str = ""
    calibrated: bool = False

    def __bool__(self) -> bool:
        return self.keep


def rag_samples_available(settings: DecisionLayerSettings) -> int:
    """Count labeled ``rag_gate`` examples already recorded (§9 calibration)."""
    try:
        entries = load_outcomes(default_outcomes_path())
    except (OSError, ValueError):  # pragma: no cover - defensive
        return 0
    return sum(1 for entry in entries if entry.get("kind") == "rag_gate")


def evaluate_rag_chunk(
    client: DecisionClient,
    settings: DecisionLayerSettings,
    *,
    query: str,
    chunk: str,
) -> RagGateResult:
    """Score one chunk against the query, pruning only when it is safe to do so.

    Default posture: **keep**. Pruning requires all of:

    * ``rag_prune_enabled=True`` (off by default);
    * ``rag_calibration_mode=False`` (i.e. calibration finished);
    * at least ``rag_min_samples`` labeled examples recorded;
    * a score clearly below the threshold (``rag_prune_margin``).
    """
    if not client.enabled:
        return RagGateResult(keep=True, reason="Camada de decisao desativada.")

    state = {
        "consulta": query[:500],
        "trecho": chunk[:1200],
    }
    question = ScoreQuestion(
        criteria=("irrelevante", "parcialmente relevante", "relevante"),
        instructions="O quanto este trecho do documento ajuda a responder a consulta?",
    )
    result = client.decide(
        DecisionRequest(state=state, questions={"relevancia": question}),
        timeout_ms=settings.timeout_ms,
    )
    answer = result.answers.get("relevancia")
    if not isinstance(answer, ScoreAnswer) or answer.score is None:
        return RagGateResult(keep=True, reason="Jev nao respondeu; trecho mantido.")

    gate = score_gate(
        answer.score,
        len(question.criteria),
        threshold=settings.rag_relevance_threshold,
        band=0.05,
    )
    samples = rag_samples_available(settings)
    calibrated = not settings.rag_calibration_mode or samples >= settings.rag_min_samples
    pruning_active = settings.rag_prune_enabled and calibrated
    clearly_irrelevant = (
        gate.normalized < settings.rag_relevance_threshold - settings.rag_prune_margin
    )
    prune = pruning_active and clearly_irrelevant

    if prune:
        reason = f"Trecho irrelevante (score {gate.normalized:.2f}) com calibracao concluida."
    elif not settings.rag_prune_enabled:
        reason = "Poda desativada: trecho mantido (padrao seguro)."
    elif not calibrated:
        reason = f"Calibrando RAG ({samples}/{settings.rag_min_samples} exemplos): trecho mantido."
    else:
        reason = f"Trecho nao claramente irrelevivel (score {gate.normalized:.2f}): mantido."

    logger.info(
        "decision rag chunk score=%.2f normalized=%.3f keep=%s prune=%s samples=%d provider=%s",
        answer.score,
        gate.normalized,
        not prune,
        prune,
        samples,
        result.provider,
    )
    client.record(
        client.make_outcome(
            kind="rag_gate",
            label="keep",
            value=gate.normalized,
            predicted=not prune,
            score=answer.score,
            samples=samples,
            elapsed_ms=round(result.elapsed_ms, 3),
        )
    )
    return RagGateResult(
        keep=not prune,
        normalized=gate.normalized,
        pruned=prune,
        reason=reason,
        calibrated=calibrated,
    )


def decide_keep_chunk(
    client: DecisionClient,
    settings: DecisionLayerSettings,
    *,
    query: str,
    chunk: str,
) -> bool:
    """Boolean convenience wrapper over :func:`evaluate_rag_chunk`."""
    return evaluate_rag_chunk(client, settings, query=query, chunk=chunk).keep


# ── Module-level defaults ───────────────────────────────────

_client: DecisionClient | None = None


# ── Model routing ───────────────────────────────────────────


@dataclass(frozen=True)
class ModelChoice:
    """JEV's pick of the best local model for a task."""

    model_id: str
    score: float
    normalized: float
    confidence: float = 0.0
    runner_up: str = ""
    margin: float = 0.0
    reason: str = ""


#: Minimum normalized adequacy for JEV to commit to a model pick. Below this
#: the caller keeps its normal (router) behavior.
MIN_MODEL_ADEQUACY = 0.45


def model_supports(model: Any, *, has_document: bool = False, has_image: bool = False) -> bool:
    """Whether a model is even eligible for this task.

    Models with no capability metadata are treated as eligible: the router is
    the authority there, and refusing to route on missing metadata would
    silently disable automatic switching. A model that *explicitly* declares it
    cannot read documents/images is excluded.
    """
    caps = getattr(model, "capabilities", None)
    declared = getattr(caps, "declared", None) if caps is not None else None
    if declared is None and isinstance(caps, (set, frozenset, list, tuple)):
        declared = set(caps)
    if not declared:
        return True
    if has_document and "document" not in declared and "rag" not in declared:
        return False
    if has_image and "image" not in declared and "vision" not in declared:
        return False
    return True


def _selectable(
    models: Sequence[Any],
    *,
    has_document: bool,
    has_image: bool,
) -> list[Any]:
    """Candidates that can actually serve the task, capped for one round trip."""
    eligible = [
        m
        for m in models
        if getattr(m, "id", "")
        and getattr(m, "download_required", False) is not True
        and model_supports(m, has_document=has_document, has_image=has_image)
    ]
    return eligible[:MAX_ROUTE_CANDIDATES]


def decide_llm_model(
    client: DecisionClient,
    settings: DecisionLayerSettings,
    *,
    query: str,
    models: Sequence[Any],
    has_document: bool = False,
    has_image: bool = False,
    current_model: str = "",
    max_candidates: int = MAX_ROUTE_CANDIDATES,
) -> ModelChoice | None:
    """Ask the decision model which downloaded LLM best answers a task.

    One 3-level ``score`` question per candidate model rides in a single
    decision pass, so this is one (cheap) JEV round trip. Returns ``None`` — the
    caller keeps its current model — when any of these hold:

    * the layer is disabled or ``model_routing`` is off;
    * fewer than two models are *eligible* (auto routing needs a real choice);
    * the provider fails or answers nothing;
    * the best score is below ``MIN_MODEL_ADEQUACY``;
    * the margin to the runner-up is below ``model_route_min_margin`` (a tie is
      not a decision);
    * reported confidence is below ``model_route_min_confidence``.

    Confidence of ``0.0`` means the provider did not report one, so the
    confidence gate only applies when at least one candidate reported it.
    """
    if not client.enabled or not settings.model_routing:
        return None
    candidates = _selectable(models, has_document=has_document, has_image=has_image)[
        : max(1, int(max_candidates))
    ]
    if len(candidates) < 2:
        return None

    state = {
        "consulta": query[:600],
        "documento": "sim" if has_document else "nao",
        "imagem": "sim" if has_image else "nao",
    }
    questions: dict[str, ScoreQuestion] = {
        f"modelo_{m.id}": ScoreQuestion(
            criteria=("inadequado", "adequado", "ideal"),
            instructions=(
                f"Avalie o modelo LLM '{getattr(m, 'name', m.id)}' "
                f"({getattr(m, 'quant', '') or 'local'}, "
                f"{getattr(m, 'size_gb', 0)}GB). O quanto ele e adequado para "
                "responder a consulta acima? Escolha 0 se for inadequado."
            ),
        )
        for m in candidates
    }

    result = client.decide(
        DecisionRequest(state=state, questions=questions),
        timeout_ms=settings.timeout_ms,
    )
    if not result.resolved:
        return None

    scored: list[tuple[float, float, float, str]] = []
    for candidate in candidates:
        answer = result.answers.get(f"modelo_{candidate.id}")
        if not isinstance(answer, ScoreAnswer) or answer.score is None:
            continue
        n_levels = len(questions[f"modelo_{candidate.id}"].criteria)
        gate = score_gate(
            answer.score,
            n_levels,
            threshold=MIN_MODEL_ADEQUACY,
            band=0.05,
        )
        scored.append((gate.normalized, answer.score, answer.confidence, candidate.id))

    if len(scored) < 2:
        # Auto routing needs at least two usable scores to compare.
        return None
    scored.sort(reverse=True)
    best_normalized, best_score, best_confidence, best_id = scored[0]
    runner_up = scored[1]
    margin = best_normalized - runner_up[0]

    def _decline(reason: str) -> None:
        logger.info("decision model route declined (%s): %s", best_id, reason)
        client.record(
            client.make_outcome(
                kind="model_route",
                label="declined",
                value=best_normalized,
                predicted=False,
                chosen=best_id,
                reason=reason,
                margin=round(margin, 4),
                runner_up=runner_up[3],
                elapsed_ms=round(result.elapsed_ms, 3),
            )
        )

    if best_normalized < MIN_MODEL_ADEQUACY - 0.05:
        _decline(f"melhor candidatura fraca (normalized={best_normalized:.2f})")
        return None
    if margin < settings.model_route_min_margin:
        _decline(f"margem insuficiente ({margin:.2f} < {settings.model_route_min_margin:.2f})")
        return None
    reported = [entry[2] for entry in scored if entry[2] > 0.0]
    if reported and min(reported) < settings.model_route_min_confidence:
        _decline(
            f"confianca insuficiente ({min(reported):.2f} < "
            f"{settings.model_route_min_confidence:.2f})"
        )
        return None
    if current_model and current_model == best_id:
        _decline("modelo ja e o atual")
        return None

    reason = f"melhor entre {len(scored)} candidatos (margem {margin:.2f})"
    logger.info(
        "decision model route best=%s normalized=%.2f margin=%.2f provider=%s",
        best_id,
        best_normalized,
        margin,
        result.provider,
    )
    client.record(
        client.make_outcome(
            kind="model_route",
            label="accepted",
            value=best_normalized,
            predicted=True,
            chosen=best_id,
            confidence=best_confidence,
            margin=round(margin, 4),
            runner_up=runner_up[3],
            elapsed_ms=round(result.elapsed_ms, 3),
        )
    )
    return ModelChoice(
        model_id=best_id,
        score=best_score,
        normalized=best_normalized,
        confidence=best_confidence,
        runner_up=runner_up[3],
        margin=margin,
        reason=reason,
    )


def get_decision_client() -> DecisionClient:
    """Return the process-wide decision client (lazily built from settings)."""
    global _client
    if _client is None:
        settings = get_settings().decision
        recorder = (
            DecisionRecorder(default_outcomes_path())
            if settings.enabled and settings.record_outcomes
            else None
        )
        _client = DecisionClient(settings, recorder=recorder)
    return _client


def reset_decision_client() -> None:
    """Reset the cached client (used by tests and settings reload)."""
    global _client
    _client = None
