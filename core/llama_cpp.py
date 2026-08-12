"""Llama.cpp Python bindings for embedded local LLM inference with Vulkan/GPU support."""

import atexit
import gc
import io
import logging
import re
import sys
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llama_cpp import Llama
from llama_cpp.llama_chat_format import Llava15ChatHandler, Qwen25VLChatHandler

from core.config import get_model_by_id
from core.inference_guard import LockedIterator
from core.metrics import MetricNames, get_metrics
from core.network_security import validate_public_http_url
from core.settings import get_settings

logger = logging.getLogger(__name__)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def _gpu_offload_supported() -> bool | None:
    """Report whether the installed llama.cpp build exposes a GPU backend."""
    try:
        from llama_cpp import llama_cpp as backend

        supports_gpu = getattr(backend, "llama_supports_gpu_offload", None)
        return bool(supports_gpu()) if callable(supports_gpu) else None
    except Exception as exc:
        logger.debug("Nao foi possivel consultar o backend de GPU: %s", exc)
        return None


class _PILImageLoaderMixin:
    """Mixin providing Pillow-based image loading for chat handlers."""

    def _load_image(self, image_url: str) -> bytes:
        max_bytes = 20 * 1024 * 1024
        if image_url.startswith("data:"):
            import base64

            header, data = image_url.split(",", 1)
            if len(data) > (max_bytes * 4 // 3) + 16:
                raise ValueError("Imagem excede o limite de 20 MB.")
            image_bytes = base64.b64decode(data)
            if len(image_bytes) > max_bytes:
                raise ValueError("Imagem excede o limite de 20 MB.")
            if PIL_AVAILABLE:
                try:
                    img = Image.open(io.BytesIO(image_bytes))
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")
                    out = io.BytesIO()
                    img.save(out, format="JPEG", quality=90)
                    return out.getvalue()
                except Exception as e:
                    logger.warning("PIL image conversion failed: %s", e)
            return image_bytes
        else:
            validated_url = validate_public_http_url(image_url)

            class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    validate_public_http_url(newurl)
                    return super().redirect_request(req, fp, code, msg, headers, newurl)

            request = urllib.request.Request(
                validated_url,
                headers={"User-Agent": "Celsius/1.0 image-loader"},
            )
            opener = urllib.request.build_opener(SafeRedirectHandler())
            with opener.open(request, timeout=10) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_bytes:
                    raise ValueError("Imagem excede o limite de 20 MB.")
                payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise ValueError("Imagem excede o limite de 20 MB.")
            return payload


class Qwen25VLChatHandlerWithPIL(_PILImageLoaderMixin, Qwen25VLChatHandler):
    """Qwen2.5-VL handler with Pillow support for more image formats."""

    @property
    def chat_format(self) -> str:
        return "qwen2-vl"


class Llava15ChatHandlerWithPIL(_PILImageLoaderMixin, Llava15ChatHandler):
    """LLaVA handler with Pillow support for more image formats."""

    @property
    def chat_format(self) -> str:
        return "llava-1-5"


class LlamaManager:
    """Manages embedded Llama model using llama-cpp-python with Vulkan support."""

    def __init__(self):
        self._llm: Llama | None = None
        self._chat_handler: Llava15ChatHandler | None = None
        self._started = False
        self._current_model_id: str | None = None
        self._on_model_changed: Callable[[str], None] | None = None
        self._inference_lock = threading.Lock()

    @property
    def current_model_id(self) -> str | None:
        return self._current_model_id

    def set_model_changed_callback(self, callback: Callable[[str], None]) -> None:
        self._on_model_changed = callback

    def _get_resource_path(self, filename: str) -> Path:
        """Get path to bundled resource (works with PyInstaller)."""
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).parent.parent
        return base / "resources" / filename

    def _get_model_path(self, model_id: str | None = None) -> Path:
        """Get path to GGUF model file."""
        settings = get_settings()
        return settings.get_model_path(model_id)

    def _get_mmproj_path(self, model_id: str | None = None) -> Path | None:
        """Get path to mmproj file for vision support (optional)."""
        settings = get_settings()
        return settings.get_mmproj_path(model_id)

    def start(
        self,
        model_id: str | None = None,
        n_gpu_layers: int = -1,
        n_ctx: int = 8192,
        n_batch: int = 1024,
        n_threads: int = 0,
        use_mmap: bool = True,
        use_mlock: bool = True,
        verbose: bool = False,
    ) -> bool:
        """Initialize the model while no inference is using its native context."""
        with self._inference_lock:
            return self._start_unlocked(
                model_id=model_id,
                n_gpu_layers=n_gpu_layers,
                n_ctx=n_ctx,
                n_batch=n_batch,
                n_threads=n_threads,
                use_mmap=use_mmap,
                use_mlock=use_mlock,
                verbose=verbose,
            )

    def _start_unlocked(
        self,
        model_id: str | None = None,
        n_gpu_layers: int = -1,
        n_ctx: int = 8192,
        n_batch: int = 1024,
        n_threads: int = 0,
        use_mmap: bool = True,
        use_mlock: bool = True,
        verbose: bool = False,
    ) -> bool:
        """Initialize Llama model with GPU acceleration via Vulkan."""
        # If same model already loaded, skip
        if self._started and self._llm is not None and self._current_model_id == model_id:
            return True

        # If switching model, stop the old one first
        if self._started and self._llm is not None:
            self._stop_unlocked()

        settings = get_settings()
        model_id = model_id or settings.llm_model

        model_path = self._get_model_path(model_id)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model file not found at {model_path}\n"
                f"Baixe o modelo no seletor de LLM ou coloque o arquivo GGUF na pasta resources/"
            )

        from core.model_downloader import verify_registered_model

        logger.info("Verificando integridade do modelo %s", model_id)
        verify_registered_model(model_id, model_path)

        # Auto-detect CPU threads if not specified
        # Use half the cores to avoid contention with GPU inference
        if n_threads <= 0:
            import os

            n_threads = max(1, (os.cpu_count() or 4) // 2)

        # Vision support (mmproj)
        mmproj_path = self._get_mmproj_path(model_id)
        model_obj = get_model_by_id(model_id)
        chat_format = model_obj.chat_format if model_obj else None

        if mmproj_path:
            from core.model_downloader import verify_registered_mmproj

            verify_registered_mmproj(model_id, mmproj_path)
            if model_obj and "qwen" in model_obj.name.lower() and "vl" in model_obj.name.lower():
                self._chat_handler = Qwen25VLChatHandlerWithPIL(
                    clip_model_path=str(mmproj_path),
                    verbose=verbose,
                )
            else:
                self._chat_handler = Llava15ChatHandlerWithPIL(
                    clip_model_path=str(mmproj_path),
                    verbose=verbose,
                )
            chat_handler = self._chat_handler
            logger.info(
                "Vision handler created: %s for %s",
                type(self._chat_handler).__name__,
                model_id,
            )
        else:
            chat_handler = None
            if model_obj and model_obj.has_mmproj:
                logger.warning("mmproj file not found for %s at %s", model_id, mmproj_path)

        # Initialize Llama - try GPU first, fall back to CPU on crash
        gpu_offload_supported = _gpu_offload_supported()
        if n_gpu_layers != 0 and gpu_offload_supported is False:
            logger.warning(
                "A instalacao atual do llama-cpp-python nao possui backend de GPU. "
                "O modelo sera executado em CPU, mesmo com n_gpu_layers=%s.",
                n_gpu_layers,
            )
        try:
            self._llm = Llama(
                model_path=str(model_path),
                n_gpu_layers=n_gpu_layers,
                n_ctx=n_ctx,
                n_batch=n_batch,
                n_threads=n_threads,
                use_mmap=use_mmap,
                use_mlock=use_mlock,
                verbose=verbose,
                chat_handler=chat_handler,
                chat_format=chat_format,
                offload_kqv=True,
                flash_attn=True,
                tensor_split=None,
            )
            backend_label = (
                "GPU disponivel"
                if gpu_offload_supported is True
                else "somente CPU"
                if gpu_offload_supported is False
                else "backend nao identificado"
            )
            logger.info(
                "Modelo carregado com n_gpu_layers=%s (%s)",
                n_gpu_layers,
                backend_label,
            )
        except Exception as gpu_err:
            logger.warning("GPU falhou (%s), tentando CPU", gpu_err)
            self._llm = Llama(
                model_path=str(model_path),
                n_gpu_layers=0,
                n_ctx=n_ctx,
                n_batch=n_batch,
                n_threads=n_threads,
                use_mmap=use_mmap,
                use_mlock=use_mlock,
                verbose=verbose,
                chat_handler=chat_handler,
                chat_format=chat_format,
                offload_kqv=False,
                flash_attn=False,
                tensor_split=None,
            )
            logger.info("Modelo carregado em CPU (sem GPU)")

        self._current_model_id = model_id
        atexit.register(self.stop)
        self._started = True

        # Synthetic text completions can abort multimodal backends before the UI opens.
        if self._on_model_changed:
            self._on_model_changed(model_id)

        return True

    def switch_model(self, model_id: str, **kwargs) -> bool:
        """Hot-swap to a different model."""
        return self.start(model_id=model_id, **kwargs)

    def stop(self) -> None:
        """Free model resources."""
        with self._inference_lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        if self._llm is not None:
            del self._llm
            self._llm = None
        if self._chat_handler is not None:
            del self._chat_handler
            self._chat_handler = None
        gc.collect()
        self._started = False
        self._current_model_id = None

    def is_healthy(self) -> bool:
        """Check readiness without running inference concurrently."""
        metrics = get_metrics()
        if not self._inference_lock.acquire(blocking=False):
            metrics.inc(MetricNames.HEALTH_CHECK_TOTAL, status="busy")
            return True
        try:
            healthy = self._started and self._llm is not None
            status = "ok" if healthy else "not_loaded"
            metrics.inc(MetricNames.HEALTH_CHECK_TOTAL, status=status)
            return healthy
        finally:
            self._inference_lock.release()

    def create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        **kwargs,
    ) -> Any:
        """Create chat completion (OpenAI-compatible API)."""
        metrics = get_metrics()
        call_kwargs = dict(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **kwargs,
        )
        if tools is not None:
            call_kwargs["tools"] = tools
        if tool_choice is not None:
            call_kwargs["tool_choice"] = tool_choice

        metrics.inc(MetricNames.LLM_REQUESTS_TOTAL, model=self._current_model_id or "unknown")

        self._inference_lock.acquire()
        lock_transferred = False
        try:
            if not self._llm:
                raise RuntimeError("Model not initialized. Call start() first.")
            with metrics.timer(
                MetricNames.LLM_INFERENCE_SECONDS,
                model=self._current_model_id or "unknown",
            ):
                result = self._llm.create_chat_completion(**call_kwargs)
            if stream:
                lock_transferred = True
                return LockedIterator(result, self._inference_lock)
        finally:
            if not lock_transferred:
                self._inference_lock.release()

        # Extract token usage if available
        if isinstance(result, dict) and "usage" in result:
            usage = result["usage"]
            if "total_tokens" in usage:
                metrics.inc(
                    MetricNames.LLM_TOKENS_TOTAL,
                    model=self._current_model_id or "unknown",
                )

        return result

    def chat_completion(self, **kwargs) -> Any:
        """Alias for create_chat_completion."""
        return self.create_chat_completion(**kwargs)

    def create_completion(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        **kwargs,
    ) -> Any:
        """Create text completion."""
        self._inference_lock.acquire()
        lock_transferred = False
        try:
            if not self._llm:
                raise RuntimeError("Model not initialized. Call start() first.")
            result = self._llm.create_completion(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                **kwargs,
            )
            if stream:
                lock_transferred = True
                return LockedIterator(result, self._inference_lock)
            return result
        finally:
            if not lock_transferred:
                self._inference_lock.release()

    def get_model_info(self) -> dict[str, Any]:
        """Get model metadata."""
        with self._inference_lock:
            if not self._llm:
                return {}
            model_id = self._current_model_id or ""
            return {
                "model_id": model_id,
                "model_path": str(self._get_model_path(model_id)),
                "n_ctx": self._llm.n_ctx(),
                "n_vocab": self._llm.n_vocab(),
            }


_manager: LlamaManager | None = None


def get_llama_manager() -> LlamaManager:
    """Get singleton Llama manager."""
    global _manager
    if _manager is None:
        _manager = LlamaManager()
    return _manager


def start_llama(
    model_id: str | None = None,
    n_gpu_layers: int = -1,
    n_ctx: int = 8192,
    n_batch: int = 1024,
    n_threads: int = 0,
    **kwargs,
) -> bool:
    """Start embedded Llama model with GPU acceleration."""
    return get_llama_manager().start(
        model_id=model_id,
        n_gpu_layers=n_gpu_layers,
        n_ctx=n_ctx,
        n_batch=n_batch,
        n_threads=n_threads,
        **kwargs,
    )


def stop_llama() -> None:
    """Stop embedded Llama model."""
    get_llama_manager().stop()


def switch_llama_model(model_id: str, **kwargs) -> bool:
    """Hot-swap to a different model."""
    return get_llama_manager().switch_model(model_id=model_id, **kwargs)


def get_llama_client_config() -> dict[str, str]:
    """Get client config (compatibility with old API)."""
    return {"base_url": "local://llama", "api_key": "dummy"}


# Backwards compatibility aliases
start_llama_server = start_llama
stop_llama_server = stop_llama


# ── Multi-Model Router ─────────────────────────────────────────────────


@dataclass
class ModelRouter:
    """Routes queries to appropriate model based on complexity.

    Uses a small/fast model for simple queries and large model for complex tasks.
    """

    # Thresholds for routing
    SIMPLE_MAX_TOKENS: int = 200  # Queries shorter than this → fast model
    COMPLEX_MIN_TOKENS: int = 100  # Queries longer than this → main model

    # Patterns that indicate complex tasks
    COMPLEX_PATTERNS: list[str] = None

    def __post_init__(self):
        if self.COMPLEX_PATTERNS is None:
            self.COMPLEX_PATTERNS = [
                # Reasoning/analysis tasks
                r"\b(analis[ae]|explic[ae]|compar[ae]|resum[ae]|relat[oó]rio)\b",
                # Code tasks
                r"\b(c[oó]digo|programa|script|fun[çc][aã]o|classe|algoritmo|python)\b",
                # Tool-using tasks
                r"\b(pesquisar|buscar|navegar|indexar|extrair|ler|listar)\b",
                # Document/file tasks
                r"\b(documento|pdf|arquivo|imagem|audio|anexo)\b",
                # Complex requests
                r"\b(passo a passo|detalhadamente|completo)\b",
                # Report generation
                r"\b(fazer|criar|gerar)\s+(um\s+)?relat[oó]rio\b",
                # Understanding requests
                r"\b(entender|compreender)\s+(como|o\s+que|por\s+que)\b",
                # Web search intent
                r"\b(preco|noticia|noticias|atual|hoje|agora|ultim[ao])\b",
            ]

    def classify_complexity(self, query: str, has_document: bool = False) -> str:
        """Classify query complexity: 'simple', 'medium', 'complex'."""
        query_lower = query.lower()
        token_estimate = len(query) / 3.5  # Rough token estimate

        # Document context always needs main model
        if has_document:
            return "complex"

        # Check for complex patterns FIRST (before simple check)
        complex_score = sum(
            1 for pattern in self.COMPLEX_PATTERNS if re.search(pattern, query_lower)
        )

        # Very short queries without tool/code patterns → simple
        if token_estimate < self.SIMPLE_MAX_TOKENS / 2 and complex_score == 0:
            return "simple"

        if complex_score >= 2 or token_estimate > self.COMPLEX_MIN_TOKENS:
            return "complex"
        elif complex_score >= 1:
            return "medium"

        return "simple"

    def get_model_for_query(self, query: str, has_document: bool = False) -> str:
        """Return model ID for the given query."""
        complexity = self.classify_complexity(query, has_document)
        settings = get_settings()

        if complexity == "simple":
            # Fast model for simple queries
            return getattr(settings, "fast_llm_model", "llama3.2-3b-q5km")
        else:
            # Main model for complex tasks
            return settings.llm_model


class MultiModelManager:
    """Manages multiple models with lazy loading."""

    def __init__(self):
        # Use the global main manager (already started)
        self.main_manager = get_llama_manager()
        # Create separate fast manager for lazy loading
        self.fast_manager = LlamaManager()
        self.router = ModelRouter()
        self._current_complexity: str | None = None

    def get_manager(self, model_id: str) -> LlamaManager:
        """Get the appropriate manager for a model ID."""
        settings = get_settings()
        if model_id == getattr(settings, "fast_llm_model", None):
            # Check if fast model is loaded, if not fall back to main
            if self.fast_manager._started:
                return self.fast_manager
            return self.main_manager
        return self.main_manager

    def route_and_invoke(
        self, query: str, has_document: bool = False, **kwargs
    ) -> tuple[str, LlamaManager]:
        """Route query to appropriate model and return (model_id, manager)."""
        model_id = self.router.get_model_for_query(query, has_document)
        manager = self.get_manager(model_id)
        self._current_complexity = self.router.classify_complexity(query, has_document)
        return model_id, manager

    def get_current_complexity(self) -> str | None:
        """Get the last classification result."""
        return self._current_complexity


# Global instance
_multi_manager: MultiModelManager | None = None


def get_multi_model_manager() -> MultiModelManager:
    """Get singleton multi-model manager.

    Delegates to core.model_router so production and tests use the same
    routing implementation.
    """
    from core.model_router import get_multi_model_manager as _get_router_manager

    return _get_router_manager()


def get_llama() -> LlamaManager:
    """Get Llama manager instance."""
    return get_llama_manager()
