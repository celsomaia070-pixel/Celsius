"""Tests for the multi-user authentication system."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.users import (
    User,
    UserService,
    UserRole,
    _hash_password,
    _token_key,
    get_user_service,
    reset_user_service,
)


@pytest.fixture
def tmp_data(tmp_path: Path):
    reset_user_service()
    svc = UserService(data_dir=tmp_path)
    yield svc
    reset_user_service()


class TestPasswordHashing:
    def test_hash_produces_different_salt(self):
        h1, s1 = _hash_password("senha123")
        h2, s2 = _hash_password("senha123")
        assert s1 != s2
        assert h1 != h2

    def test_hash_deterministic_with_same_salt(self):
        h1, salt = _hash_password("senha123")
        h2, _ = _hash_password("senha123", salt)
        assert h1 == h2

    def test_wrong_password_different_hash(self):
        h1, salt = _hash_password("senha123")
        h2, _ = _hash_password("senha456", salt)
        assert h1 != h2


class TestUserRegistration:
    def test_register_success(self, tmp_data: UserService):
        user = tmp_data.register("test@example.com", "password123", "Test User")
        assert user.email == "test@example.com"
        assert user.display_name == "Test User"
        assert user.role == UserRole.ADMIN
        assert user.is_active is True

    def test_first_user_becomes_admin(self, tmp_data: UserService):
        first = tmp_data.register("owner@example.com", "password123")
        second = tmp_data.register("member@example.com", "password123")
        assert first.role == UserRole.ADMIN
        assert second.role == UserRole.USER

    def test_register_duplicate_email_raises(self, tmp_data: UserService):
        tmp_data.register("dup@example.com", "password123")
        with pytest.raises(ValueError, match="Ja existe"):
            tmp_data.register("dup@example.com", "password456")

    def test_register_short_password_raises(self, tmp_data: UserService):
        with pytest.raises(ValueError, match="minimo 8"):
            tmp_data.register("short@example.com", "abc")

    def test_register_empty_email_raises(self, tmp_data: UserService):
        with pytest.raises(ValueError):
            tmp_data.register("", "password123")

    def test_register_admin_role(self, tmp_data: UserService):
        user = tmp_data.register("admin@example.com", "password123", role=UserRole.ADMIN)
        assert user.role == UserRole.ADMIN

    def test_email_normalized_lowercase(self, tmp_data: UserService):
        user = tmp_data.register("UPPER@Example.COM", "password123")
        assert user.email == "upper@example.com"


class TestAuthentication:
    def test_login_success(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        tokens = tmp_data.authenticate("user@example.com", "password123")
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "bearer"

    def test_login_wrong_password(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        with pytest.raises(ValueError, match="Credenciais"):
            tmp_data.authenticate("user@example.com", "wrongpassword")

    def test_login_nonexistent_user(self, tmp_data: UserService):
        with pytest.raises(ValueError, match="Credenciais"):
            tmp_data.authenticate("nobody@example.com", "password123")

    def test_login_is_temporarily_limited_after_repeated_failures(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        for _ in range(5):
            with pytest.raises(ValueError, match="Credenciais"):
                tmp_data.authenticate("user@example.com", "wrongpassword", client_key="127.0.0.1")
        with pytest.raises(ValueError, match="Muitas tentativas"):
            tmp_data.authenticate("user@example.com", "password123", client_key="127.0.0.1")

    def test_validate_token_returns_user(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        tokens = tmp_data.authenticate("user@example.com", "password123")
        user = tmp_data.validate_token(tokens.access_token)
        assert user is not None
        assert user.email == "user@example.com"

    def test_validate_invalid_token(self, tmp_data: UserService):
        assert tmp_data.validate_token("invalid_token") is None

    def test_logout_invalidates_token(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        tokens = tmp_data.authenticate("user@example.com", "password123")
        tmp_data.logout(tokens.access_token)
        assert tmp_data.validate_token(tokens.access_token) is None

    def test_logout_preserves_other_device_session(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        first = tmp_data.authenticate("user@example.com", "password123")
        second = tmp_data.authenticate("user@example.com", "password123")
        tmp_data.logout(first.access_token)
        assert tmp_data.validate_token(first.access_token) is None
        assert tmp_data.validate_token(second.access_token) is not None


class TestRefreshToken:
    def test_refresh_success(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        tokens = tmp_data.authenticate("user@example.com", "password123")
        new_tokens = tmp_data.refresh(tokens.refresh_token)
        assert new_tokens.access_token != tokens.access_token
        assert new_tokens.refresh_token != tokens.refresh_token

    def test_refresh_invalid_token(self, tmp_data: UserService):
        with pytest.raises(ValueError, match="invalido"):
            tmp_data.refresh("invalid_refresh")

    def test_refresh_old_token_invalid(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        tokens = tmp_data.authenticate("user@example.com", "password123")
        new_tokens = tmp_data.refresh(tokens.refresh_token)
        with pytest.raises(ValueError):
            tmp_data.refresh(tokens.refresh_token)

    def test_refresh_revokes_previous_access_in_same_session(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        tokens = tmp_data.authenticate("user@example.com", "password123")
        new_tokens = tmp_data.refresh(tokens.refresh_token)
        assert tmp_data.validate_token(tokens.access_token) is None
        assert tmp_data.validate_token(new_tokens.access_token) is not None


class TestUserManagement:
    def test_list_users(self, tmp_data: UserService):
        tmp_data.register("a@example.com", "password123")
        tmp_data.register("b@example.com", "password456")
        users = tmp_data.list_users()
        assert len(users) == 2

    def test_get_user(self, tmp_data: UserService):
        user = tmp_data.register("user@example.com", "password123")
        found = tmp_data.get_user(user.id)
        assert found is not None
        assert found.email == "user@example.com"

    def test_get_user_by_email(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        found = tmp_data.get_user_by_email("user@example.com")
        assert found is not None

    def test_update_user(self, tmp_data: UserService):
        user = tmp_data.register("user@example.com", "password123")
        updated = tmp_data.update_user(user.id, display_name="New Name", role=UserRole.MANAGER)
        assert updated.display_name == "New Name"
        assert updated.role == UserRole.MANAGER

    def test_delete_user(self, tmp_data: UserService):
        user = tmp_data.register("user@example.com", "password123")
        assert tmp_data.delete_user(user.id) is True
        assert tmp_data.get_user(user.id) is None

    def test_delete_nonexistent_user(self, tmp_data: UserService):
        assert tmp_data.delete_user("nonexistent") is False

    def test_change_password(self, tmp_data: UserService):
        user = tmp_data.register("user@example.com", "password123")
        old_tokens = tmp_data.authenticate("user@example.com", "password123")
        tmp_data.change_password(user.id, "password123", "newpassword456")
        assert tmp_data.validate_token(old_tokens.access_token) is None
        with pytest.raises(ValueError, match="invalido"):
            tmp_data.refresh(old_tokens.refresh_token)
        tokens = tmp_data.authenticate("user@example.com", "newpassword456")
        assert tokens.access_token

    def test_change_password_wrong_old(self, tmp_data: UserService):
        user = tmp_data.register("user@example.com", "password123")
        with pytest.raises(ValueError, match="incorreta"):
            tmp_data.change_password(user.id, "wrongold", "newpassword456")

    def test_public_dict_no_secrets(self, tmp_data: UserService):
        user = tmp_data.register("user@example.com", "password123")
        public = user.to_public_dict()
        assert "password_hash" not in public
        assert "salt" not in public
        assert public["email"] == "user@example.com"


class TestTokenCleanup:
    def test_cleanup_removes_expired(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        tokens = tmp_data.authenticate("user@example.com", "password123")
        with tmp_data._lock:
            from datetime import datetime, timedelta, timezone

            tmp_data._tokens_cache[_token_key(tokens.access_token)]["expires_at"] = (
                datetime.now(timezone.utc) - timedelta(hours=1)
            ).isoformat()
        removed = tmp_data.cleanup_expired_tokens()
        assert removed >= 1

    def test_persisted_tokens_are_hashed(self, tmp_data: UserService):
        tmp_data.register("user@example.com", "password123")
        tokens = tmp_data.authenticate("user@example.com", "password123")
        persisted = (tmp_data._data_dir / "auth_tokens.json").read_text(encoding="utf-8")
        assert tokens.access_token not in persisted
        assert tokens.refresh_token not in persisted
        assert _token_key(tokens.access_token) in persisted
