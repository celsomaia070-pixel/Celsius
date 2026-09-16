"""Pairing information for the responsive Celsius web interface."""

from __future__ import annotations

import base64
import io
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from core.mobile_access import get_lan_ip, mobile_certificate_fingerprint

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
    pairing_code = request.app.state.browser_sessions.issue_pairing_code()
    query = urlencode({"pair": pairing_code})
    lan_ip = get_lan_ip()
    lan_access_enabled = bool(request.app.state.lan_access_enabled)
    if lan_access_enabled:
        default_port = 443 if scheme == "https" else 80
        authority = lan_ip if port == default_port else f"{lan_ip}:{port}"
        url = f"{scheme}://{authority}/app?{query}"
        interface = "desktop-responsive"
    else:
        # The main web server is often intentionally loopback-only. Start the
        # dedicated HTTPS companion after the authenticated user clicks Pair;
        # returning an empty QR here made mobile access look broken.
        server = request.app.state.ensure_mobile_access(allow_lan=True)
        url = server.url
        lan_ip = get_lan_ip()
        scheme = "https" if server.use_https else "http"
        port = server._httpd.server_address[1] if server._httpd else server.port
        interface = "mobile-companion"

    fingerprint = mobile_certificate_fingerprint(
        request.app.state.settings.data_dir / "mobile_access" / "celsius-mobile.crt"
    )
    return {
        "ok": True,
        "url": url,
        "qr_code": _qr_data_url(url),
        "lan_ip": lan_ip,
        "lan_access_enabled": True,
        "same_network_required": True,
        "external_service": False,
        "https": scheme == "https",
        "certificate_fingerprint": fingerprint,
        "interface": interface,
        "voice_input": True,
    }
