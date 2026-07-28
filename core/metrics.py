"""Structured metrics collection for Celsius.

Provides lightweight in-process metrics without requiring Prometheus server.
All metrics are stored in memory and can be queried via API or exported.
"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Single metric data point."""

    name: str
    value: float
    timestamp: float
    labels: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Thread-safe in-process metrics collector.

    Supports counters, gauges, and histograms.
    """

    def __init__(self):
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._timers: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.RLock()
        self._start_time = time.time()

    # --- Counters ---

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        """Increment a counter."""
        key = self._make_key(name, labels)
        with self._lock:
            self._counters[key] += value

    def dec(self, name: str, value: float = 1.0, **labels: str) -> None:
        """Decrement a counter."""
        key = self._make_key(name, labels)
        with self._lock:
            self._counters[key] -= value

    def get_counter(self, name: str, **labels: str) -> float:
        key = self._make_key(name, labels)
        return self._counters.get(key, 0.0)

    # --- Gauges ---

    def set(self, name: str, value: float, **labels: str) -> None:
        """Set a gauge value."""
        key = self._make_key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def get_gauge(self, name: str, **labels: str) -> float | None:
        key = self._make_key(name, labels)
        return self._gauges.get(key)

    # --- Histograms / Timers ---

    def observe(self, name: str, value: float, **labels: str) -> None:
        """Record a histogram observation."""
        key = self._make_key(name, labels)
        with self._lock:
            self._histograms[key].append(value)
            # Keep last 1000 observations
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]

    def timer(self, name: str, **labels: str):
        """Context manager that records elapsed time."""
        return _TimerContext(self, name, labels)

    def _record_elapsed(self, name: str, elapsed: float, labels: dict[str, str]) -> None:
        key = self._make_key(name, labels)
        with self._lock:
            self._timers[key].append(elapsed)
            if len(self._timers[key]) > 1000:
                self._timers[key] = self._timers[key][-1000:]

    # --- Query ---

    def get_histogram_stats(self, name: str, **labels: str) -> dict[str, float]:
        """Get p50/p95/p99 stats for a histogram."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, []) + self._timers.get(key, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
        values_sorted = sorted(values)
        n = len(values_sorted)
        return {
            "count": n,
            "min": values_sorted[0],
            "max": values_sorted[-1],
            "avg": sum(values_sorted) / n,
            "p50": values_sorted[int(n * 0.5)],
            "p95": values_sorted[min(int(n * 0.95), n - 1)],
            "p99": values_sorted[min(int(n * 0.99), n - 1)],
        }

    def snapshot(self) -> dict[str, Any]:
        """Export all metrics as a dict."""
        with self._lock:
            return {
                "uptime_seconds": time.time() - self._start_time,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: self.get_histogram_stats(*k.split("|", 1)[1].split(","))
                    for k in self._histograms
                },
                "timers": {
                    k: self.get_histogram_stats(*k.split("|", 1)[1].split(","))
                    for k in self._timers
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._timers.clear()
            self._start_time = time.time()

    @staticmethod
    def _make_key(name: str, labels: dict[str, str]) -> str:
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            return f"{name}|{label_str}"
        return name


class _TimerContext:
    """Context manager for timing code blocks."""

    def __init__(self, collector: MetricsCollector, name: str, labels: dict[str, str]):
        self._collector = collector
        self._name = name
        self._labels = labels
        self._start = 0.0
        self.elapsed = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self._start
        self._collector._record_elapsed(self._name, self.elapsed, self._labels)


# --- Predefined metric names ---


class MetricNames:
    """Centralized metric names for consistency."""

    # Tool execution
    TOOL_CALLS_TOTAL = "celsius_tool_calls_total"
    TOOL_ERRORS_TOTAL = "celsius_tool_errors_total"
    TOOL_DURATION_SECONDS = "celsius_tool_duration_seconds"

    # LLM inference
    LLM_REQUESTS_TOTAL = "celsius_llm_requests_total"
    LLM_TOKENS_TOTAL = "celsius_llm_tokens_total"
    LLM_INFERENCE_SECONDS = "celsius_llm_inference_seconds"

    # RAG
    RAG_SEARCH_TOTAL = "celsius_rag_search_total"
    RAG_INDEX_TOTAL = "celsius_rag_index_total"
    RAG_CHUNKS_TOTAL = "celsius_rag_chunks_total"

    # Circuit breaker
    CB_STATE = "celsius_circuit_breaker_state"

    # System
    MEMORY_USAGE_BYTES = "celsius_memory_usage_bytes"
    ACTIVE_SESSIONS = "celsius_active_sessions"
    HEALTH_CHECK_TOTAL = "celsius_health_check_total"


# Global singleton
_collector: MetricsCollector | None = None
_collector_lock = threading.Lock()


def get_metrics() -> MetricsCollector:
    global _collector
    if _collector is None:
        with _collector_lock:
            if _collector is None:
                _collector = MetricsCollector()
    return _collector
