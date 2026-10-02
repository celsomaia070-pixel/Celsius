"""Lifecycle wrapper for running the local ASGI server beside the desktop UI."""

from __future__ import annotations

import ipaddress
import logging
import threading
import time
from typing import Any

import uvicorn

from core.mobile_access import _create_server_ssl_context, ensure_mobile_certificate, get_lan_ip
from core.settings import get_settings
from core.web_api.app import create_app

logger = logging.getLogger(__name__)


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LocalWebApiServer:
    def __init__(
        self,
        *,
        host: str | None = None,
        port: int = 8790,
        settings: Any = None,
        allow_lan: bool = False,
    ):
        settings = settings or get_settings()
        self.host = (
            host
            if host is not None
            else ("0.0.0.0" if allow_lan else settings.web.host)  # nosec B104
        )
        self.port = port
        self.lan_access_enabled = not _is_loopback(self.host)
        if self.lan_access_enabled and not allow_lan:
            raise ValueError("A exposicao da API na rede local exige allow_lan=True.")

        self.use_https = self.lan_access_enabled
        cert_file = key_file = None
        ssl_context = None
        if self.use_https:
            cert_file, key_file = ensure_mobile_certificate(
                settings.data_dir / "mobile_access",
                lan_ip=get_lan_ip(),
            )
            # ``core.web_api`` already restores the native stdlib SSL class at
            # package import, so a server context built here is not a client-only
            # truststore wrapper even on Windows.
            ssl_context = _create_server_ssl_context()

        scheme = "https" if self.use_https else "http"
        self.app = create_app(
            settings=settings,
            lan_access_enabled=self.lan_access_enabled,
            public_scheme=scheme,
            public_port=port,
        )
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=port,
            log_level="warning",
            access_log=False,
        )
        if ssl_context is not None:
            config.load()
            ssl_context.load_cert_chain(str(cert_file), str(key_file))
            config.ssl = ssl_context
        self._server = uvicorn.Server(config)
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        scheme = "https" if self.use_https else "http"
        display_host = get_lan_ip() if self.host in {"0.0.0.0", "::"} else self.host  # nosec B104
        return f"{scheme}://{display_host}:{self.port}"

    def start(self, *, timeout: float = 5.0) -> bool:
        if self._thread and self._thread.is_alive():
            return self._server.started and not self._server.should_exit
        # Uvicorn retains started/should_exit after shutdown; a new run needs fresh state.
        self._server = uvicorn.Server(self._server.config)
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
