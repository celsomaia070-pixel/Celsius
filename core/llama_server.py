"""Llama.cpp server manager for embedded local LLM inference."""
import atexit
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

from core.config import get_settings


class LlamaServerManager:
    """Manages embedded llama-server process."""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.base_url = "http://127.0.0.1:8080/v1"
        self._started = False

    def _get_resource_path(self, filename: str) -> Path:
        """Get path to bundled resource (works with PyInstaller)."""
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).parent.parent
        return base / "resources" / filename

    def _get_server_binary(self) -> Path:
        """Get platform-specific llama-server binary name."""
        import platform
        system = platform.system().lower()
        if system == "windows":
            return self._get_resource_path("llama-server.exe")
        elif system == "darwin":
            return self._get_resource_path("llama-server-macos")
        else:
            return self._get_resource_path("llama-server-linux")

    def _get_model_path(self) -> Path:
        """Get path to GGUF model file."""
        settings = get_settings()
        return settings.get_local_model_path()

    def start(self, wait_ready: bool = True, timeout: float = 60.0) -> bool:
        """Start llama-server process."""
        if self._started and self.is_healthy():
            return True

        binary = self._get_server_binary()
        model = self._get_model_path()

        if not binary.exists():
            raise FileNotFoundError(f"llama-server binary not found at {binary}")
        if not model.exists():
            raise FileNotFoundError(f"Model file not found at {model}")

        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
        else:
            creationflags = 0

        cmd = [
            str(binary),
            "-m", str(model),
            "-c", "8192",
            "--port", "8080",
            "--host", "127.0.0.1",
            "--no-warmup",
            "--parallel", "1",
        ]

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

        atexit.register(self.stop)
        self._started = True

        if wait_ready:
            return self._wait_ready(timeout)
        return True

    def _wait_ready(self, timeout: float) -> bool:
        """Wait for server to be ready."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_healthy():
                return True
            time.sleep(0.5)
        return False

    def is_healthy(self) -> bool:
        """Check if server is responding."""
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self.base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False

    def stop(self) -> None:
        """Stop llama-server process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
        self._started = False

    def get_client_config(self) -> dict:
        """Get OpenAI client configuration."""
        return {
            "base_url": self.base_url,
            "api_key": "dummy",
        }


_server_manager: Optional[LlamaServerManager] = None


def get_server_manager() -> LlamaServerManager:
    """Get singleton server manager."""
    global _server_manager
    if _server_manager is None:
        _server_manager = LlamaServerManager()
    return _server_manager


def start_llama_server(wait_ready: bool = True) -> bool:
    """Start embedded llama-server."""
    return get_server_manager().start(wait_ready=wait_ready)


def stop_llama_server() -> None:
    """Stop embedded llama-server."""
    get_server_manager().stop()


def get_llama_client_config() -> dict:
    """Get OpenAI client config for llama-server."""
    return get_server_manager().get_client_config()