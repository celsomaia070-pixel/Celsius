"""Lifecycle wrapper for running the local ASGI server beside the desktop UI."""

from __future__ import annotations

import logging
import threading
import time

import uvicorn

from core.web_api.app import create_app

logger = logging.getLogger(__name__)


class LocalWebApiServer:
    def __init__(self, *, host: str = "127.0.0.1", port: int = 8790, settings=None):
        self.host = host
        self.port = port
        self.app = create_app(settings=settings)
        self._server = uvicorn.Server(
            uvicorn.Config(
                self.app,
                host=host,
                port=port,
                log_level="warning",
                access_log=False,
            )
        )
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, *, timeout: float = 5.0) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        self._thread = threading.Thread(
            target=self._server.run,
            name="CelsiusWebApi",
            daemon=True,
        )
        self._thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started:
                logger.info("API local disponivel em %s", self.url)
                return True
            if not self._thread.is_alive():
                break
            time.sleep(0.05)
        logger.warning("A API local nao iniciou em %s", self.url)
        return False

    def stop(self, *, timeout: float = 5.0) -> None:
        self._server.should_exit = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
