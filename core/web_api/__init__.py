"""Local web API foundation for the Celsius interface migration."""

from __future__ import annotations

import ssl
from typing import Any

from core.mobile_access import _create_server_ssl_context

# ``python -m core.web_api`` imports this package before its __main__. Restore
# stdlib SSL here so runpy/asyncio cannot cache pip's client-only wrapper.
_native_ssl_context = _create_server_ssl_context()
ssl.SSLContext = type(_native_ssl_context)
del _native_ssl_context

__all__ = ["EventHub", "create_app", "get_event_hub"]


def __getattr__(name: str) -> Any:
    """Keep package exports lazy so server bootstrap can configure SSL first."""

    if name == "create_app":
        from core.web_api.app import create_app

        return create_app
    if name in {"EventHub", "get_event_hub"}:
        from core.web_api.events import EventHub, get_event_hub

        return {"EventHub": EventHub, "get_event_hub": get_event_hub}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
