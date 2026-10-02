"""Embedding model helpers for Celsius.

Keep user-facing aliases stable while loading the real provider model ids.
"""

from __future__ import annotations

import threading
from typing import Any

from core.operation_control import cancellable_lock, check_control

EMBEDDING_MODEL_ALIASES = {
    "qwen3-embedding-0.6b": "Qwen/Qwen3-Embedding-0.6B",
    "qwen3-embedding-4b": "Qwen/Qwen3-Embedding-4B",
}
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_CACHE_LOCK = threading.RLock()


def resolve_embedding_model_name(model_name: str) -> str:
    """Return the loadable SentenceTransformer model id for *model_name*."""
    normalized = (model_name or "").strip()
    return EMBEDDING_MODEL_ALIASES.get(normalized.lower(), normalized)


def create_sentence_transformer(model_name: str):
    """Return one shared SentenceTransformer instance per resolved model."""
    from sentence_transformers import SentenceTransformer

    resolved_name = resolve_embedding_model_name(model_name)
    with cancellable_lock(_MODEL_CACHE_LOCK):
        model = _MODEL_CACHE.get(resolved_name)
        if model is None:
            model = SentenceTransformer(
                resolved_name,
                local_files_only=True,
            )
            check_control()
            _MODEL_CACHE[resolved_name] = model
        return model


def clear_sentence_transformer_cache() -> None:
    """Clear shared models for controlled shutdowns and isolated tests."""
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.clear()


def try_get_sentence_transformer(model_name: str) -> Any | None:
    """Return the shared model, or ``None`` when it cannot be loaded.

    Several call sites (sub-agent classification, tool retrieval, mode routing)
    need the same model and must all degrade to a lexical path rather than
    fail. They share this accessor so the singleton and its failure handling
    live in one place instead of being re-implemented per caller.
    """
    try:
        return create_sentence_transformer(model_name)
    except Exception:
        return None
