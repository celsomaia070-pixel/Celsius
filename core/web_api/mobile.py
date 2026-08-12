"""Pairing information for the responsive Celsius web interface."""

from __future__ import annotations

import base64
import io
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from core.mobile_access import get_lan_ip

router = APIRouter(tags=["mobile access"])


def _qr_data_url(value: str) -> str:
    try:
        import qrcode

        image = qrcode.make(value)
        output = io.BytesIO()
        image.save(output, format="PNG")
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except (ImportError, OSError, ValueError):
        return ""


@router.get("/mobile/pairing")
def mobile_pairing(request: Request) -> dict:
    scheme = request.app.state.public_scheme or request.url.scheme
    port = request.app.state.public_port or request.url.port or (443 if scheme == "https" else 80)
    token = request.app.state.access_token
    query = urlencode({"token": token})
    lan_ip = get_lan_ip()
    default_port = 443 if scheme == "https" else 80
    authority = lan_ip if port == default_port else f"{lan_ip}:{port}"
    url = f"{scheme}://{authority}/app?{query}"
    return {
        "ok": True,
        "url": url,
        "qr_code": _qr_data_url(url),
        "lan_ip": lan_ip,
        "lan_access_enabled": bool(request.app.state.lan_access_enabled),
        "same_network_required": True,
        "external_service": False,
        "https": scheme == "https",
        "interface": "desktop-responsive",
        "voice_input": True,
    }
