"""Pairing information for the responsive Celsius web interface."""

from __future__ import annotations

import base64
import io

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
    pairing_code = request.app.state.browser_sessions.issue_pairing_code()
    # Mobile pairing always targets the focused voice companion. The full
    # responsive web interface remains available separately at /app.
    server = request.app.state.ensure_mobile_access(allow_lan=True)
    url = server.url
    lan_ip = get_lan_ip()
    scheme = "https" if server.use_https else "http"
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
        # Mobile companion specific fields
        "mobile_companion_url": server.url if interface == "mobile-companion" else "",
        # The companion owns its own one-time token. Keep compatibility with
        # lightweight/older companion implementations that expose the token only
        # in the URL; the browser still receives a usable pairing link.
        "mobile_pairing_code": (
            getattr(server, "pairing_code", "") or pairing_code
            if interface == "mobile-companion"
            else pairing_code
        ),
    }
