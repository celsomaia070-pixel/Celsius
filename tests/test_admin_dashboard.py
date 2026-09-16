"""Tests for admin dashboard endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.users import UserService, UserRole, reset_user_service
from core.conversation_history import ConversationHistoryService, reset_conversation_history_service


@pytest.fixture
def setup_services(tmp_path: Path):
    reset_user_service()
    reset_conversation_history_service()
    user_svc = UserService(data_dir=tmp_path / "users")
    hist_svc = ConversationHistoryService(base_dir=tmp_path / "history")
    yield user_svc, hist_svc
    reset_user_service()
    reset_conversation_history_service()


class TestSystemStats:
    def test_stats_with_no_users(self, setup_services):
        user_svc, hist_svc = setup_services
        users = user_svc.list_users()
        assert len(users) == 0

    def test_stats_with_users_and_conversations(self, setup_services):
        user_svc, hist_svc = setup_services
        admin = user_svc.register("admin@test.com", "password1234", role=UserRole.ADMIN)
        user = user_svc.register("user@test.com", "password1234")
        conv = hist_svc.create_conversation(admin.id, title="Teste")
        hist_svc.add_message(conv["id"], admin.id, "user", "Ola mundo")
        hist_svc.add_message(conv["id"], admin.id, "assistant", "Ola!")
        stats = hist_svc.get_statistics(admin.id)
        assert stats["total_conversations"] == 1
        assert stats["total_messages"] == 2

    def test_user_count(self, setup_services):
        user_svc, _ = setup_services
        user_svc.register("a@test.com", "password1234")
        user_svc.register("b@test.com", "password1234")
        users = user_svc.list_users()
        assert len(users) == 2

    def test_admin_count(self, setup_services):
        user_svc, _ = setup_services
        user_svc.register("admin@test.com", "password1234", role=UserRole.ADMIN)
        user_svc.register("user@test.com", "password1234")
        users = user_svc.list_users()
        admins = [u for u in users if u.role == UserRole.ADMIN]
        assert len(admins) == 1


class TestUserActivity:
    def test_user_activity_sorted_by_messages(self, setup_services):
        user_svc, hist_svc = setup_services
        u1 = user_svc.register("user1@test.com", "password1234")
        u2 = user_svc.register("user2@test.com", "password1234")
        c1 = hist_svc.create_conversation(u1.id, title="Conv 1")
        for i in range(5):
            hist_svc.add_message(c1["id"], u1.id, "user", f"Msg {i}")
        c2 = hist_svc.create_conversation(u2.id, title="Conv 2")
        hist_svc.add_message(c2["id"], u2.id, "user", "Only one")
        s1 = hist_svc.get_statistics(u1.id)
        s2 = hist_svc.get_statistics(u2.id)
        assert s1["total_messages"] > s2["total_messages"]
