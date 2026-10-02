"""Calibration tooling for the decision layer (DECISION_LAYER.md §9).

The decision layer records every gate/route outcome to a JSONL file when
``CELSIUS_DECISION_RECORD_OUTCOMES=true`` (and the layer is enabled). This
module provides the pieces to *use* that log for gradual activation:

* ``DecisionRecorder``: cheap, thread-safe JSONL appender. Never raises: an
  outcome log is observability, not a hard dependency.
* ``load_outcomes``: replay the log (skipping corrupt lines).
* ``accuracy``/``balanced_accuracy``: how well a candidate threshold separates
  labeled probes.
* ``recommend_*_threshold``: grid-search the best threshold over labeled
  entries and return a small report for tuning ``GUARD_RISK_THRESHOLD`` and
  ``RAG_RELEVANCE_THRESHOLD``.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.settings import get_settings

logger = __import__("logging").getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_outcomes_path() -> Path:
    """Location of the decision outcome log next to the app logs."""
    settings = get_settings()
    logs_dir = getattr(settings, "logs_dir", None) or Path("logs")
    return Path(logs_dir) / "decision_outcomes.jsonl"


class DecisionRecorder:
    """Thread-safe JSONL appender for decision outcomes.

    Every entry is appended atomically on its own line. Failures (bad path,
    disk full, ...) are logged and never propagated to callers.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def append(self, entry: dict[str, Any]) -> None:
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False, default=str))
                    handle.write("\n")
            except OSError as exc:
                logger.warning("decisao: falha ao gravar resultado: %s", exc)


def load_outcomes(path: Path | str) -> list[dict[str, Any]]:
    """Replay the JSONL outcome log, skipping lines that fail to parse."""
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("decisao: linha %d invalida no log (ignorada)", line_number)
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def accuracy(entries: list[dict[str, Any]], *, threshold: float, key: str = "probability") -> float:
    """Fraction of labeled entries the threshold classifies correctly.

    A positive label (``label=1``) is predicted when ``value >= threshold``.
    """
    if not entries:
        return 0.0
    correct = 0
    for entry in entries:
        predicted = float(entry.get(key, 0.0)) >= threshold
        correct += int(predicted == bool(entry.get("label")))
    return correct / len(entries)


def balanced_accuracy(
    entries: list[dict[str, Any]], *, threshold: float, key: str = "probability"
) -> float:
    """Mean of sensitivity and specificity, so class imbalance is harmless."""
    positives = [e for e in entries if bool(e.get("label"))]
    negatives = [e for e in entries if not bool(e.get("label"))]
    if not positives or not negatives:
        return accuracy(entries, threshold=threshold, key=key)
    tp = sum(1.0 for e in positives if float(e.get(key, 0.0)) >= threshold) / len(positives)
    tn = sum(1.0 for e in negatives if float(e.get(key, 0.0)) < threshold) / len(negatives)
    return (tp + tn) / 2.0


def _float_value(entry: dict[str, Any], key: str) -> float:
    try:
        return float(entry.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class ThresholdReport:
    """Suggested threshold plus the metrics measured at it."""

    kind: str
    threshold: float
    balanced_accuracy: float
    accuracy: float
    n: int
    n_positive: int
    n_negative: int
    grid: tuple[float, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "threshold": round(self.threshold, 3),
            "balanced_accuracy": round(self.balanced_accuracy, 3),
            "accuracy": round(self.accuracy, 3),
            "n": self.n,
            "n_positive": self.n_positive,
            "n_negative": self.n_negative,
            "grid": [round(g, 3) for g in self.grid],
        }


def _best_threshold(
    entries: list[dict[str, Any]],
    *,
    grid: tuple[float, ...],
    key: str,
    kind: str,
) -> ThresholdReport:
    best_t, best_bacc = grid[0], -1.0
    for candidate in grid:
        candidate_bacc = balanced_accuracy(entries, threshold=candidate, key=key)
        if candidate_bacc > best_bacc:
            best_t, best_bacc = candidate, candidate_bacc
    return ThresholdReport(
        kind=kind,
        threshold=best_t,
        balanced_accuracy=best_bacc,
        accuracy=accuracy(entries, threshold=best_t, key=key),
        n=len(entries),
        n_positive=sum(1 for e in entries if bool(e.get("label"))),
        n_negative=sum(1 for e in entries if not bool(e.get("label"))),
        grid=grid,
    )


def recommend_guard_threshold(
    entries: list[dict[str, Any]],
    *,
    grid: tuple[float, ...] | None = None,
) -> ThresholdReport:
    """Find the ``noul >= threshold`` cut that best matches ``label`` entries.

    Produces a ``threshold`` to try as ``CELSIUS_DECISION_GUARD_RISK_THRESHOLD``.
    """
    scan = grid or tuple(round(0.50 + 0.05 * i, 2) for i in range(10))
    return _best_threshold(entries, grid=scan, key="probability", kind="guard")


def recommend_score_threshold(
    entries: list[dict[str, Any]],
    *,
    grid: tuple[float, ...] | None = None,
) -> ThresholdReport:
    """Calibrate ``RAG_RELEVANCE_THRESHOLD`` from ``normalized >= threshold`` labels."""
    scan = grid or tuple(round(0.10 + 0.05 * i, 2) for i in range(17))
    return _best_threshold(entries, grid=scan, key="normalized", kind="rag_score")


def report_pretty(report: ThresholdReport) -> str:
    """One-line formatted summary for terminals/status messages."""
    return (
        f"[{report.kind}] threshold sugerido={report.threshold:.2f} "
        f"(balanced_acc={report.balanced_accuracy:.2f}, acc={report.accuracy:.2f}, "
        f"n={report.n}, pos={report.n_positive}, neg={report.n_negative})"
    )


def summarize_outcomes(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-kind rollups of the recorded outcomes for day-to-day tuning.

    Returns stats like the fraction of tool guards that asked for approval
    (guard 'false positive' noise) and the fraction of RAG chunks pruned.
    """
    per_kind: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        per_kind.setdefault(str(entry.get("kind")), []).append(entry)

    summary: dict[str, dict[str, Any]] = {}
    for kind, items in per_kind.items():
        predicted_true = sum(1 for e in items if bool(e.get("predicted")))
        summary[kind] = {
            "n": len(items),
            "predicted_true": predicted_true,
            "rate": round(predicted_true / len(items), 4) if items else 0.0,
            "mean_value": round(sum(_float_value(e, "value") for e in items) / len(items), 4)
            if items
            else 0.0,
        }
    return summary
