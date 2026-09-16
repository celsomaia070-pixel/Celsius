"""Authentication helpers shared by HTTP and WebSocket endpoints."""

from __future__ import annotations

import contextlib
import secrets
import threading
import time

from fastapi import Request, WebSocket

from core.mobile_access import ensure_mobile_token


class BrowserSessionStore:
    """Short-lived browser sessions bootstrapped by one-time pairing codes."""

    def __init__(
        self,
        *,
        pairing_ttl_seconds: int = 120,
        session_ttl_seconds: int = 12 * 60 * 60,
        max_sessions: int = 32,
    ) -> None:
        self.pairing_ttl_seconds = max(30, pairing_ttl_seconds)
        self.session_ttl_seconds = max(300, session_ttl_seconds)
        self.max_sessions = max(1, max_sessions)
        self._pairing_codes: dict[str, float] = {}
        self._sessions: dict[str, float] = {}
        self._lock = threading.RLock()

    def issue_pairing_code(self) -> str:
        with self._lock:
            self._purge()
            code = secrets.token_urlsafe(24)
            self._pairing_codes[code] = time.monotonic() + self.pairing_ttl_seconds
            return code

    def exchange_pairing_code(self, code: str) -> str | None:
        with self._lock:
            self._purge()
            expires_at = self._pairing_codes.pop(code, None)
            if expires_at is None or expires_at <= time.monotonic():
                return None
            return self.issue_session()

    def issue_session(self) -> str:
        with self._lock:
            self._purge()
            while len(self._sessions) >= self.max_sessions:
                oldest = min(self._sessions, key=self._sessions.get)
                self._sessions.pop(oldest, None)
            token = secrets.token_urlsafe(32)
            self._sessions[token] = time.monotonic() + self.session_ttl_seconds
            return token

    def is_valid(self, token: str) -> bool:
        if not token:
            return False
        with self._lock:
            self._purge()
            expires_at = self._sessions.get(token)
            return bool(expires_at and expires_at > time.monotonic())

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)

    def _purge(self) -> None:
        now = time.monotonic()
        self._pairing_codes = {
            code: expires for code, expires in self._pairing_codes.items() if expires > now
        }
        self._sessions = {
            token: expires for token, expires in self._sessions.items() if expires > now
        }


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
    return request.cookies.get("celsius_session", "").strip()


def websocket_token(websocket: WebSocket) -> str:
    authorization = websocket.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return websocket.cookies.get("celsius_session", "").strip()


def token_matches(candidate: str, expected: str) -> bool:
    return bool(candidate and expected and secrets.compare_digest(candidate, expected))


def credential_is_valid(
    candidate: str,
    *,
    access_token: str,
    sessions: BrowserSessionStore,
) -> bool:
    return token_matches(candidate, access_token) or sessions.is_valid(candidate)
