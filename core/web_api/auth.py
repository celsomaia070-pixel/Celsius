"""Authentication helpers shared by HTTP and WebSocket endpoints."""

from __future__ import annotations

import contextlib
import secrets

from fastapi import Request, WebSocket

from core.mobile_access import ensure_mobile_token


def resolve_access_token(settings) -> str:
    """Reuse the existing pairing identity during the incremental migration."""

    existing_token = (settings.mobile.pairing_token or "").strip()
    token = ensure_mobile_token(existing_token)
    settings.mobile.pairing_token = token
    if not existing_token:
        with contextlib.suppress(OSError):
            settings.save_local_preferences()
    return token


def request_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return (
        request.query_params.get("token", "").strip()
        or request.cookies.get("celsius_session", "").strip()
    )


def websocket_token(websocket: WebSocket) -> str:
    authorization = websocket.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return (
        websocket.query_params.get("token", "").strip()
        or websocket.cookies.get("celsius_session", "").strip()
    )


def token_matches(candidate: str, expected: str) -> bool:
    return bool(candidate and expected and secrets.compare_digest(candidate, expected))
