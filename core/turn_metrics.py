"""Content-free timings shared through a turn's worker context."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter

_current = ContextVar("celsius_turn_metrics", default=None)
_PHASES = {
    "lock_wait",
    "routing",
    "classification",
    "memory",
    "rag",
    "model_wait",
    "model_prepare",
    "tool_selection",
    "web",
    "browser_open",
}


@dataclass
class TurnMetrics:
    started: float = field(default_factory=perf_counter)
    phases: dict = field(default_factory=dict)
    first_token_ms: float | None = None
    first_visible_token_ms: float | None = None
    total_ms: float | None = None
    model_state: str = "not_used"

    def first_token(self):
        if self.first_token_ms is None:
            self.first_token_ms = (perf_counter() - self.started) * 1000

    def finish(self):
        self.total_ms = (perf_counter() - self.started) * 1000

    def first_visible_token(self):
        self.first_token()
        if self.first_visible_token_ms is None:
            self.first_visible_token_ms = (perf_counter() - self.started) * 1000

    def public_dict(self):
        return {
            "phases_ms": {key: round(value, 3) for key, value in self.phases.items()},
            "first_token_ms": self.first_token_ms,
            "first_visible_token_ms": self.first_visible_token_ms,
            "total_ms": self.total_ms,
            "model_state": self.model_state,
        }


@contextmanager
def bind_metrics(metrics):
    token = _current.set(metrics)
    try:
        yield
    finally:
        _current.reset(token)


@contextmanager
def phase(name, *, metrics=None):
    active = metrics or _current.get()
    start = perf_counter()
    try:
        yield
    finally:
        if active is not None and name in _PHASES:
            active.phases[name] = active.phases.get(name, 0) + (perf_counter() - start) * 1000


def current_metrics():
    return _current.get()


def track_turn(function):
    @wraps(function)
    def tracked(*args, **kwargs):
        if current_metrics() is not None:
            return function(*args, **kwargs)
        metrics = TurnMetrics()
        with bind_metrics(metrics):
            try:
                return function(*args, **kwargs)
            finally:
                metrics.finish()
                logging.getLogger("celsius.turns").info("turn_metrics %s", metrics.public_dict())

    return tracked
