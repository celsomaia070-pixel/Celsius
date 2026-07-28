"""Circuit Breaker implementation for external service calls.

States:
- CLOSED: normal operation, requests pass through
- OPEN: failures exceeded threshold, requests are rejected immediately
- HALF_OPEN: cooldown expired, allowing a probe request

Usage:
    @circuit_breaker(failure_threshold=5, recovery_timeout=60)
    def call_external_service():
        ...
"""

import functools
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Thread-safe circuit breaker for protecting external calls."""

    name: str
    failure_threshold: int = 5
    recovery_timeout: int = 60
    expected_exceptions: tuple = (Exception,)

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _last_state_change: float = field(default_factory=time.time, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and time.time() - self._last_failure_time >= self.recovery_timeout
            ):
                self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def _transition_to(self, new_state: CircuitState) -> None:
        old = self._state
        self._state = new_state
        self._last_state_change = time.time()
        logger.info(
            "[CircuitBreaker:%s] %s -> %s (failures=%d)",
            self.name,
            old.value,
            new_state.value,
            self._failure_count,
        )

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._success_count += 1
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if (
                self._state == CircuitState.HALF_OPEN
                or self._failure_count >= self.failure_threshold
            ):
                self._transition_to(CircuitState.OPEN)

    def allow_request(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return True
        # OPEN: reject
        return False

    def reset(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._success_count = 0
            self._transition_to(CircuitState.CLOSED)

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure": self._last_failure_time,
            "recovery_timeout": self.recovery_timeout,
        }


# Global registry
_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exceptions: tuple = (Exception,),
) -> CircuitBreaker:
    """Get or create a named circuit breaker (singleton per name)."""
    with _registry_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                expected_exceptions=expected_exceptions,
            )
        return _breakers[name]


def circuit_breaker(
    name: str | None = None,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
):
    """Decorator that wraps a function with circuit breaker protection."""

    def decorator(func):
        cb_name = name or f"{func.__module__}.{func.__qualname__}"
        cb = get_circuit_breaker(cb_name, failure_threshold, recovery_timeout)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not cb.allow_request():
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{cb.name}' is OPEN. "
                    f"Service unavailable. Retry after {cb.recovery_timeout}s."
                )
            try:
                result = func(*args, **kwargs)
                cb.record_success()
                return result
            except cb.expected_exceptions:
                cb.record_failure()
                raise

        wrapper.circuit_breaker = cb
        return wrapper

    return decorator


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker is in OPEN state."""

    pass


def get_all_breakers() -> list[dict]:
    """Return status of all registered circuit breakers."""
    return [cb.get_status() for cb in _breakers.values()]
