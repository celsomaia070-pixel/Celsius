"""Dependency Injection Container for Celsius.

Uses lazy imports to avoid circular dependencies and missing modules.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Lazy container - avoids import-time failures
_container: Any = None


class _LazyContainer:
    """Lazy dependency container that defers imports until first access."""

    def __init__(self):
        self._services: dict[str, Any] = {}
        self._singletons: dict[str, Any] = {}
        self._factories: dict[str, Any] = {}
        self._initialized = False
        self._lock = threading.Lock()

    def _ensure_initialized(self):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            logger.debug("Lazy container initialized")

    def get_service(self, name: str) -> Any:
        if name in self._singletons:
            return self._singletons[name]

        self._ensure_initialized()

        factory = self._factories.get(name)
        if factory is None:
            raise KeyError(f"Service '{name}' not registered")

        instance = factory()
        self._singletons[name] = instance
        return instance

    def register(self, name: str, factory) -> None:
        self._factories[name] = factory

    def reset(self) -> None:
        with self._lock:
            self._singletons.clear()
            self._initialized = False


def _create_container() -> _LazyContainer:
    container = _LazyContainer()

    # Register lazy factories — imports happen only when service is first accessed
    container.register("settings", lambda: _import_settings())
    container.register("memory_service", lambda: _import_memory_service())
    container.register("rag_service", lambda: _import_rag_service())
    container.register("llama_manager", lambda: _import_llama_manager())
    container.register("multi_model_manager", lambda: _import_multi_model_manager())
    container.register("conversation_manager", lambda: _import_conversation_manager())

    return container


def _import_settings():
    from core.settings import get_settings

    return get_settings()


def _import_memory_service():
    from core.memory import get_memory_service

    return get_memory_service()


def _import_rag_service():
    from ai.rag import get_rag_service

    return get_rag_service()


def _import_llama_manager():
    from core.llama_cpp import get_llama_manager

    return get_llama_manager()


def _import_multi_model_manager():
    from core.llama_cpp import get_multi_model_manager

    return get_multi_model_manager()


def _import_conversation_manager():
    from core.conversations import get_conversation_manager

    return get_conversation_manager()


def get_container() -> _LazyContainer:
    """Get the global application container."""
    global _container
    if _container is None:
        _container = _create_container()
    return _container


def reset_container() -> None:
    """Reset the global container (mainly for testing)."""
    global _container
    if _container is not None:
        _container.reset()
        _container = None
