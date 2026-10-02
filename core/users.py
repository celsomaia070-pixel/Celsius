"""Multi-user authentication and authorization for Celsius."""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from core.json_persistence import atomic_write_json, read_json

logger = logging.getLogger(__name__)

_HASH_ITERATIONS = 260_000
_SALT_BYTES = 16
_TOKEN_EXPIRY_HOURS = 24
_REFRESH_EXPIRY_DAYS = 30
_TOKEN_KEY_PREFIX = "sha256:"
_LOGIN_WINDOW_SECONDS = 5 * 60
_LOGIN_MAX_FAILURES = 5


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    VIEWER = "viewer"


@dataclass
class User:
    id: str
    email: str
    display_name: str
    password_hash: str
    salt: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_login: str = ""
    avatar_url: str = ""
    sidebar_preferences: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("password_hash", None)
        d.pop("salt", None)
        return d


@dataclass(frozen=True)
class AuthToken:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = _TOKEN_EXPIRY_HOURS * 3600


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(_SALT_BYTES)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        _HASH_ITERATIONS,
    )
    return key.hex(), salt


def _generate_id() -> str:
    return secrets.token_hex(12)


def _generate_token() -> str:
    return secrets.token_urlsafe(48)


def _token_key(token: str) -> str:
    """Return the non-reversible key persisted for a bearer token."""
    digest = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
    return f"{_TOKEN_KEY_PREFIX}{digest}"


class UserService:
    """Manages user registration, authentication, and session tokens."""

    def __init__(self, data_dir: Path | None = None):
        from core.settings import get_settings

        self._data_dir = Path(data_dir or get_settings().data_dir)
        self._users_dir = self._data_dir / "users"
        self._users_dir.mkdir(parents=True, exist_ok=True)
        self._tokens_file = self._data_dir / "auth_tokens.json"
        self._lock = threading.Lock()
        self._users_cache: dict[str, User] = {}
        self._tokens_cache: dict[str, dict[str, Any]] = {}
        self._login_failures: dict[str, list[float]] = {}
        self._load_all()

    def _users_file(self, user_id: str) -> Path:
        return self._users_dir / f"{user_id}.json"

    def _load_all(self) -> None:
        with self._lock:
            self._users_cache.clear()
            for f in self._users_dir.glob("*.json"):
                try:
                    data = read_json(f, None)
                    if data:
                        data["role"] = UserRole(data.get("role", "user"))
                        self._users_cache[data["id"]] = User(**data)
                except Exception as exc:
                    logger.warning("Falha ao carregar usuario %s: %s", f.name, exc)
            raw_tokens = read_json(self._tokens_file, {})
            if isinstance(raw_tokens, dict):
                migrated = False
                protected: dict[str, dict[str, Any]] = {}
                for token, metadata in raw_tokens.items():
                    key = token if token.startswith(_TOKEN_KEY_PREFIX) else _token_key(token)
                    migrated = migrated or key != token
                    if isinstance(metadata, dict):
                        protected[key] = metadata
                self._tokens_cache = protected
                if migrated:
                    self._save_tokens()

    def _save_user(self, user: User) -> None:
        path = self._users_file(user.id)
        atomic_write_json(path, asdict(user))

    def _save_tokens(self) -> None:
        atomic_write_json(self._tokens_file, self._tokens_cache)

    def register(
        self,
        email: str,
        password: str,
        display_name: str = "",
        role: UserRole = UserRole.USER,
    ) -> User:
        email = email.strip().lower()
        if not email or not password:
            raise ValueError("Email e senha sao obrigatorios.")
        if len(password) < 8:
            raise ValueError("A senha deve ter no minimo 8 caracteres.")
        with self._lock:
            for u in self._users_cache.values():
                if u.email == email:
                    raise ValueError("Ja existe um usuario com este email.")
            is_first_user = not self._users_cache
            effective_role = UserRole.ADMIN if is_first_user else role
            password_hash, salt = _hash_password(password)
            user = User(
                id=_generate_id(),
                email=email,
                display_name=display_name or email.split("@")[0],
                password_hash=password_hash,
                salt=salt,
                role=effective_role,
            )
            self._users_cache[user.id] = user
            self._save_user(user)
        logger.info("Usuario registrado: %s (%s)", user.email, user.id)
        return user

    def authenticate(self, email: str, password: str, *, client_key: str = "") -> AuthToken:
        email = email.strip().lower()
        attempt_key = f"{client_key.strip()}:{email}"
        with self._lock:
            now_monotonic = time.monotonic()
            failures = [
                value
                for value in self._login_failures.get(attempt_key, ())
                if now_monotonic - value < _LOGIN_WINDOW_SECONDS
            ]
            self._login_failures[attempt_key] = failures
            if len(failures) >= _LOGIN_MAX_FAILURES:
                raise ValueError("Muitas tentativas. Aguarde alguns minutos e tente novamente.")
            user = None
            for u in self._users_cache.values():
                if u.email == email:
                    user = u
                    break
            if user is None or not user.is_active:
                failures.append(now_monotonic)
                raise ValueError("Credenciais invalidas.")
            computed_hash, _ = _hash_password(password, user.salt)
            if not secrets.compare_digest(computed_hash, user.password_hash):
                failures.append(now_monotonic)
                raise ValueError("Credenciais invalidas.")
            self._login_failures.pop(attempt_key, None)
            user.last_login = datetime.now(timezone.utc).isoformat()
            user.updated_at = user.last_login
            self._save_user(user)
            access = _generate_token()
            refresh = _generate_token()
            session_id = secrets.token_hex(12)
            now = datetime.now(timezone.utc)
            self._tokens_cache[_token_key(access)] = {
                "user_id": user.id,
                "type": "access",
                "session_id": session_id,
                "expires_at": (now + timedelta(hours=_TOKEN_EXPIRY_HOURS)).isoformat(),
            }
            self._tokens_cache[_token_key(refresh)] = {
                "user_id": user.id,
                "type": "refresh",
                "session_id": session_id,
                "expires_at": (now + timedelta(days=_REFRESH_EXPIRY_DAYS)).isoformat(),
            }
            self._save_tokens()
        return AuthToken(access_token=access, refresh_token=refresh)

    def refresh(self, refresh_token: str) -> AuthToken:
        with self._lock:
            refresh_key = _token_key(refresh_token)
            token_data = self._tokens_cache.get(refresh_key)
            if not token_data or token_data.get("type") != "refresh":
                raise ValueError("Refresh token invalido.")
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                self._tokens_cache.pop(refresh_key, None)
                self._save_tokens()
                raise ValueError("Refresh token expirado.")
            user = self._users_cache.get(token_data["user_id"])
            if not user or not user.is_active:
                raise ValueError("Usuario invalido ou inativo.")
            session_id = str(token_data.get("session_id") or "")
            for key, item in list(self._tokens_cache.items()):
                same_user = item.get("user_id") == user.id
                same_session = session_id and item.get("session_id") == session_id
                legacy_session = not session_id and same_user and not item.get("session_id")
                if same_session or legacy_session:
                    self._tokens_cache.pop(key, None)
            if not session_id:
                session_id = secrets.token_hex(12)
            access = _generate_token()
            new_refresh = _generate_token()
            now = datetime.now(timezone.utc)
            self._tokens_cache[_token_key(access)] = {
                "user_id": user.id,
                "type": "access",
                "session_id": session_id,
                "expires_at": (now + timedelta(hours=_TOKEN_EXPIRY_HOURS)).isoformat(),
            }
            self._tokens_cache[_token_key(new_refresh)] = {
                "user_id": user.id,
                "type": "refresh",
                "session_id": session_id,
                "expires_at": (now + timedelta(days=_REFRESH_EXPIRY_DAYS)).isoformat(),
            }
            self._save_tokens()
        return AuthToken(access_token=access, refresh_token=new_refresh)

    def validate_token(self, token: str) -> User | None:
        with self._lock:
            token_key = _token_key(token)
            token_data = self._tokens_cache.get(token_key)
            if not token_data or token_data.get("type") != "access":
                return None
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                self._tokens_cache.pop(token_key, None)
                return None
            user = self._users_cache.get(token_data["user_id"])
            if user and user.is_active:
                return user
        return None

    def logout(self, token: str) -> None:
        with self._lock:
            token_data = self._tokens_cache.get(_token_key(token))
            if token_data is None:
                return
            user_id = token_data.get("user_id")
            session_id = token_data.get("session_id")
            for key, item in list(self._tokens_cache.items()):
                same_session = session_id and item.get("session_id") == session_id
                legacy_session = not session_id and item.get("user_id") == user_id
                if same_session or legacy_session:
                    self._tokens_cache.pop(key, None)
            self._save_tokens()

    def get_user(self, user_id: str) -> User | None:
        return self._users_cache.get(user_id)

    def get_user_by_email(self, email: str) -> User | None:
        email = email.strip().lower()
        for u in self._users_cache.values():
            if u.email == email:
                return u
        return None

    def list_users(self) -> list[User]:
        return list(self._users_cache.values())

    def update_user(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        avatar_url: str | None = None,
    ) -> User:
        with self._lock:
            user = self._users_cache.get(user_id)
            if user is None:
                raise ValueError("Usuario nao encontrado.")
            if display_name is not None:
                user.display_name = display_name
            if role is not None:
                user.role = role
            if is_active is not None:
                user.is_active = is_active
            if avatar_url is not None:
                user.avatar_url = avatar_url
            user.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_user(user)
        return user

    def update_sidebar_preferences(self, user_id: str, changes: dict[str, Any]) -> User:
        """Merge personal workspace preferences without changing other users."""
        with self._lock:
            user = self._users_cache.get(user_id)
            if user is None:
                raise ValueError("Usuario nao encontrado.")
            preferences = dict(user.sidebar_preferences)
            visibility = changes.get("sidebar_visible")
            preferences.update(changes)
            if visibility is not None:
                preferences["sidebar_visible"] = {
                    **user.sidebar_preferences.get("sidebar_visible", {}),
                    **visibility,
                }
            previous = user.sidebar_preferences
            user.sidebar_preferences = preferences
            try:
                self._save_user(user)
            except OSError:
                user.sidebar_preferences = previous
                raise
        return user

    def change_password(self, user_id: str, old_password: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise ValueError("A nova senha deve ter no minimo 8 caracteres.")
        with self._lock:
            user = self._users_cache.get(user_id)
            if user is None:
                raise ValueError("Usuario nao encontrado.")
            computed_hash, _ = _hash_password(old_password, user.salt)
            if not secrets.compare_digest(computed_hash, user.password_hash):
                raise ValueError("Senha atual incorreta.")
            new_hash, new_salt = _hash_password(new_password)
            user.password_hash = new_hash
            user.salt = new_salt
            user.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_user(user)
            # Password rotation is a security boundary: every browser and
            # companion must authenticate again with the new password.
            revoked = [
                token
                for token, data in self._tokens_cache.items()
                if data.get("user_id") == user_id
            ]
            for token in revoked:
                self._tokens_cache.pop(token, None)
            if revoked:
                self._save_tokens()

    def delete_user(self, user_id: str) -> bool:
        with self._lock:
            user = self._users_cache.pop(user_id, None)
            if user is None:
                return False
            path = self._users_file(user_id)
            if path.exists():
                path.unlink()
            tokens_to_remove = [
                t for t, d in self._tokens_cache.items() if d.get("user_id") == user_id
            ]
            for t in tokens_to_remove:
                self._tokens_cache.pop(t, None)
            self._save_tokens()
        logger.info("Usuario removido: %s (%s)", user.email, user_id)
        return True

    def cleanup_expired_tokens(self) -> int:
        now = datetime.now(timezone.utc)
        with self._lock:
            expired = [
                t
                for t, d in self._tokens_cache.items()
                if datetime.fromisoformat(d["expires_at"]) < now
            ]
            for t in expired:
                self._tokens_cache.pop(t, None)
            if expired:
                self._save_tokens()
        return len(expired)


_user_service: UserService | None = None
_user_service_lock = threading.Lock()


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        with _user_service_lock:
            if _user_service is None:
                _user_service = UserService()
    return _user_service


def reset_user_service() -> None:
    global _user_service
    with _user_service_lock:
        _user_service = None
