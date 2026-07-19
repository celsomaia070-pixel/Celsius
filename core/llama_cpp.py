"""Llama.cpp Python bindings for embedded local LLM inference with Vulkan/GPU support."""
import atexit
import gc
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from llama_cpp import Llama
from llama_cpp.llama_chat_format import Llava15ChatHandler

from core.config import get_settings


class LlamaManager:
    """Manages embedded Llama model using llama-cpp-python with Vulkan support."""

    def __init__(self):
        self._llm: Optional[Llama] = None
        self._chat_handler: Optional[Llava15ChatHandler] = None
        self._started = False

    def _get_resource_path(self, filename: str) -> Path:
        """Get path to bundled resource (works with PyInstaller)."""
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).parent.parent
        return base / "resources" / filename

    def _get_model_path(self) -> Path:
        """Get path to GGUF model file."""
        settings = get_settings()
        return settings.get_local_model_path()

    def _get_mmproj_path(self) -> Optional[Path]:
        """Get path to mmproj file for vision support (optional)."""
        mmproj = self._get_resource_path("mmproj.gguf")
        return mmproj if mmproj.exists() else None

    def start(
        self,
        n_gpu_layers: int = -1,
        n_ctx: int = 8192,
        n_batch: int = 512,
        n_threads: int = 0,
        use_mmap: bool = True,
        use_mlock: bool = False,
        verbose: bool = False,
    ) -> bool:
        """Initialize Llama model with GPU acceleration via Vulkan."""
        if self._started and self._llm is not None:
            return True

        model_path = self._get_model_path()
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found at {model_path}")

        settings = get_settings()
        
        # Auto-detect CPU threads if not specified
        if n_threads <= 0:
            import os
            n_threads = max(1, (os.cpu_count() or 4) - 1)

        # Vision support (mmproj)
        mmproj_path = self._get_mmproj_path()
        if mmproj_path:
            self._chat_handler = Llava15ChatHandler(
                clip_model_path=str(mmproj_path),
                verbose=verbose,
            )
            chat_handler = self._chat_handler
        else:
            chat_handler = None

        # Initialize Llama with Vulkan (GPU) support
        # n_gpu_layers=-1 means offload all possible layers to GPU
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
            # Vulkan-specific: offload KV cache to GPU VRAM
            offload_kqv=True,
            # Performance tuning
            flash_attn=True,
            tensor_split=None,
        )

        atexit.register(self.stop)
        self._started = True

        # Warm up
        try:
            self._llm("Warm up", max_tokens=1, temperature=0)
        except Exception:
            pass

        return True

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
        
        return self._llm.create_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )

    # Alias for compatibility with react.py
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
        return {
            "model_path": str(self._get_model_path()),
            "n_ctx": self._llm.n_ctx(),
            "n_vocab": self._llm.n_vocab(),
            "model_size": self._get_model_path().stat().st_size,
        }


_manager: Optional[LlamaManager] = None


def get_llama_manager() -> LlamaManager:
    """Get singleton Llama manager."""
    global _manager
    if _manager is None:
        _manager = LlamaManager()
    return _manager


def start_llama(
    n_gpu_layers: int = -1,
    n_ctx: int = 8192,
    n_batch: int = 512,
    n_threads: int = 0,
    **kwargs,
) -> bool:
    """Start embedded Llama model with GPU acceleration."""
    return get_llama_manager().start(
        n_gpu_layers=n_gpu_layers,
        n_ctx=n_ctx,
        n_batch=n_batch,
        n_threads=n_threads,
        **kwargs,
    )


def stop_llama() -> None:
    """Stop embedded Llama model."""
    get_llama_manager().stop()


def get_llama_client_config() -> Dict[str, str]:
    """Get client config (compatibility with old API)."""
    return {"base_url": "local://llama", "api_key": "dummy"}


# Backwards compatibility aliases
start_llama_server = start_llama
stop_llama_server = stop_llama


def get_llama() -> LlamaManager:
    """Get Llama manager instance (for react.py compatibility)."""
    return get_llama_manager()