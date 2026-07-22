"""Llama.cpp Python bindings for embedded local LLM inference with Vulkan/GPU support."""
import atexit
import base64
import gc
import io
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from llama_cpp import Llama
from llama_cpp.llama_chat_format import Llava15ChatHandler, Qwen25VLChatHandler

from core.config import get_settings, get_model_by_id, GGUFModel

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class Qwen25VLChatHandlerWithPIL(Qwen25VLChatHandler):
    """Qwen2.5-VL handler with Pillow support for more image formats."""

    def _load_image(self, image_url: str) -> bytes:
        if image_url.startswith("data:"):
            import base64
            header, data = image_url.split(",", 1)
            image_bytes = base64.b64decode(data)
            if PIL_AVAILABLE:
                try:
                    img = Image.open(io.BytesIO(image_bytes))
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")
                    out = io.BytesIO()
                    img.save(out, format="JPEG", quality=90)
                    return out.getvalue()
                except Exception:
                    pass
            return image_bytes
        else:
            import urllib.request
            with urllib.request.urlopen(image_url) as f:
                return f.read()

    @property
    def chat_format(self) -> str:
        """Use Qwen2-VL chat format for proper conversation template."""
        return "qwen2-vl"


class Llava15ChatHandlerWithPIL(Llava15ChatHandler):
    """LLaVA handler with Pillow support for more image formats."""

    def _load_image(self, image_url: str) -> bytes:
        if image_url.startswith("data:"):
            import base64
            header, data = image_url.split(",", 1)
            image_bytes = base64.b64decode(data)
            if PIL_AVAILABLE:
                try:
                    img = Image.open(io.BytesIO(image_bytes))
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")
                    out = io.BytesIO()
                    img.save(out, format="JPEG", quality=90)
                    return out.getvalue()
                except Exception:
                    pass
            return image_bytes
        else:
            import urllib.request
            with urllib.request.urlopen(image_url) as f:
                return f.read()

    @property
    def chat_format(self) -> str:
        """Use LLaVA chat format for proper conversation template."""
        return "llava-1-5"


class LlamaManager:
    """Manages embedded Llama model using llama-cpp-python with Vulkan support."""

    def __init__(self):
        self._llm: Optional[Llama] = None
        self._chat_handler: Optional[Llava15ChatHandler] = None
        self._started = False
        self._current_model_id: Optional[str] = None
        self._on_model_changed: Optional[Callable[[str], None]] = None

    @property
    def current_model_id(self) -> Optional[str]:
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

    def _get_mmproj_path(self, model_id: str | None = None) -> Optional[Path]:
        """Get path to mmproj file for vision support (optional)."""
        settings = get_settings()
        return settings.get_mmproj_path(model_id)

    def start(
        self,
        model_id: Optional[str] = None,
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
            self.stop()

        settings = get_settings()
        model_id = model_id or settings.llm_model

        model_path = self._get_model_path(model_id)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model file not found at {model_path}\n"
                f"Baixe o modelo no seletor de LLM ou coloque o arquivo GGUF na pasta resources/"
            )

        # Auto-detect CPU threads if not specified
        # Use half the cores to avoid contention with GPU inference
        if n_threads <= 0:
            import os
            n_threads = max(1, (os.cpu_count() or 4) // 2)

        # Vision support (mmproj)
        mmproj_path = self._get_mmproj_path(model_id)
        model_obj = get_model_by_id(model_id)
        chat_format = None

        if mmproj_path:
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
            print(f"[LLAMA] Vision handler created: {type(self._chat_handler).__name__} for {model_id}")
        else:
            chat_handler = None
            # Set chat_format for non-vision Qwen models
            if model_obj and "qwen" in model_obj.name.lower():
                if "vl" in model_obj.name.lower():
                    chat_format = "qwen2-vl"
                else:
                    chat_format = "qwen2"
            if model_obj and model_obj.has_mmproj:
                print(f"[LLAMA] WARNING: mmproj file not found for {model_id} at {mmproj_path}")

        # Initialize Llama with Vulkan (GPU) support
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

        self._current_model_id = model_id
        atexit.register(self.stop)
        self._started = True

        # Warm up
        try:
            self._llm("Warm up", max_tokens=1, temperature=0)
        except Exception:
            pass

        if self._on_model_changed:
            self._on_model_changed(model_id)

        return True

    def switch_model(self, model_id: str, **kwargs) -> bool:
        """Hot-swap to a different model."""
        return self.start(model_id=model_id, **kwargs)

    def stop(self) -> None:
        """Free model resources."""
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
        """Check if model is loaded."""
        return self._llm is not None

    def create_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Create chat completion (OpenAI-compatible API)."""
        if not self._llm:
            raise RuntimeError("Model not initialized. Call start() first.")

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

        return self._llm.create_chat_completion(**call_kwargs)

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
        if not self._llm:
            raise RuntimeError("Model not initialized. Call start() first.")

        return self._llm.create_completion(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **kwargs,
        )

    def get_model_info(self) -> Dict[str, Any]:
        """Get model metadata."""
        if not self._llm:
            return {}
        model_id = self._current_model_id or ""
        return {
            "model_id": model_id,
            "model_path": str(self._get_model_path(model_id)),
            "n_ctx": self._llm.n_ctx(),
            "n_vocab": self._llm.n_vocab(),
        }


_manager: Optional[LlamaManager] = None


def get_llama_manager() -> LlamaManager:
    """Get singleton Llama manager."""
    global _manager
    if _manager is None:
        _manager = LlamaManager()
    return _manager


def start_llama(
    model_id: Optional[str] = None,
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


def get_llama_client_config() -> Dict[str, str]:
    """Get client config (compatibility with old API)."""
    return {"base_url": "local://llama", "api_key": "dummy"}


# Backwards compatibility aliases
start_llama_server = start_llama
stop_llama_server = stop_llama


def get_llama() -> LlamaManager:
    """Get Llama manager instance."""
    return get_llama_manager()
