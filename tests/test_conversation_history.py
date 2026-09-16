"""Tests for conversation history with multi-user support."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.conversation_history import (
    ConversationHistoryService,
    get_conversation_history_service,
    reset_conversation_history_service,
)


@pytest.fixture
def tmp_data(tmp_path: Path):
    reset_conversation_history_service()
    svc = ConversationHistoryService(base_dir=tmp_path)
    yield svc
    reset_conversation_history_service()


class TestConversationCreation:
    def test_create_conversation(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        assert conv["user_id"] == "user1"
        assert conv["title"] == "Teste"
        assert conv["messages"] == []
        assert conv["shared"] is False

    def test_create_with_tags(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste", metadata={"tags": ["ai"]})
        assert conv["metadata"]["tags"] == ["ai"]


class TestConversationAccess:
    def test_get_own_conversation(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        found = tmp_data.get_conversation(conv["id"], "user1")
        assert found is not None
        assert found["title"] == "Teste"

    def test_cannot_get_other_user_conversation(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        found = tmp_data.get_conversation(conv["id"], "user2")
        assert found is None

    def test_list_user_conversations(self, tmp_data: ConversationHistoryService):
        tmp_data.create_conversation("user1", title="Conv 1")
        tmp_data.create_conversation("user1", title="Conv 2")
        tmp_data.create_conversation("user2", title="Conv 3")
        convs = tmp_data.list_user_conversations("user1")
        assert len(convs) == 2

    def test_list_with_tag_filter(self, tmp_data: ConversationHistoryService):
        c1 = tmp_data.create_conversation("user1", title="Conv 1")
        tmp_data.update_conversation(c1["id"], "user1", tags=["trabalho"])
        c2 = tmp_data.create_conversation("user1", title="Conv 2")
        tmp_data.update_conversation(c2["id"], "user1", tags=["pessoal"])
        convs = tmp_data.list_user_conversations("user1", tag="trabalho")
        assert len(convs) == 1
        assert convs[0]["id"] == c1["id"]


class TestMessages:
    def test_add_message(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        msg = tmp_data.add_message(conv["id"], "user1", "user", "Ola!")
        assert msg["role"] == "user"
        assert msg["content"] == "Ola!"
        assert msg["id"]

    def test_auto_title_from_first_message(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1")
        tmp_data.add_message(conv["id"], "user1", "user", "Qual e a capital do Brasil?")
        updated = tmp_data.get_conversation(conv["id"], "user1")
        assert updated["title"] == "Qual e a capital do Brasil?"

    def test_cannot_add_message_to_other_user_conv(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        msg = tmp_data.add_message(conv["id"], "user2", "user", "Ola!")
        assert msg is None


class TestSearch:
    def test_search_by_content(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        tmp_data.add_message(conv["id"], "user1", "user", "Python e uma linguagem de programacao")
        results = tmp_data.search_conversations("user1", "python")
        assert len(results) == 1
        assert results[0]["conversation_id"] == conv["id"]

    def test_search_by_date(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        tmp_data.add_message(conv["id"], "user1", "user", "Mensagem")
        results = tmp_data.search_conversations(
            "user1",
            "mensagem",
            start_date="2020-01-01",
            end_date="2030-12-31",
        )
        assert len(results) == 1

    def test_search_no_results(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        tmp_data.add_message(conv["id"], "user1", "user", "Ola")
        results = tmp_data.search_conversations("user1", "xyz123")
        assert len(results) == 0

    def test_search_isolation(self, tmp_data: ConversationHistoryService):
        c1 = tmp_data.create_conversation("user1", title="Teste")
        tmp_data.add_message(c1["id"], "user1", "user", "Python e legal")
        c2 = tmp_data.create_conversation("user2", title="Teste")
        tmp_data.add_message(c2["id"], "user2", "user", "Python e incrivel")
        results = tmp_data.search_conversations("user1", "python")
        assert len(results) == 1
        assert results[0]["conversation_id"] == c1["id"]


class TestStatistics:
    def test_statistics(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        tmp_data.add_message(conv["id"], "user1", "user", "Ola mundo")
        tmp_data.add_message(conv["id"], "user1", "assistant", "Ola! Como posso ajudar?")
        stats = tmp_data.get_statistics("user1")
        assert stats["total_conversations"] == 1
        assert stats["total_messages"] == 2
        assert stats["user_messages"] == 1
        assert stats["assistant_messages"] == 1
        assert stats["total_words"] > 0


class TestSharing:
    def test_share_conversation(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        tmp_data.add_message(conv["id"], "user1", "user", "Ola")
        share = tmp_data.share_conversation(conv["id"], "user1", expires_hours=24)
        assert share is not None
        assert share["is_active"] is True
        assert share["share_id"]

    def test_get_shared_conversation(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        tmp_data.add_message(conv["id"], "user1", "user", "Ola")
        share = tmp_data.share_conversation(conv["id"], "user1")
        data = tmp_data.get_shared_conversation(share["share_id"])
        assert data is not None
        assert data["title"] == "Teste"

    def test_revoke_share(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        share = tmp_data.share_conversation(conv["id"], "user1")
        ok = tmp_data.revoke_share(share["share_id"])
        assert ok is True
        data = tmp_data.get_shared_conversation(share["share_id"])
        assert data is None

    def test_max_views_limit(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        share = tmp_data.share_conversation(conv["id"], "user1", max_views=2)
        tmp_data.get_shared_conversation(share["share_id"])
        tmp_data.get_shared_conversation(share["share_id"])
        data = tmp_data.get_shared_conversation(share["share_id"])
        assert data is None


class TestExport:
    def test_export_markdown(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        tmp_data.add_message(conv["id"], "user1", "user", "Ola")
        content = tmp_data.export_conversation(conv["id"], "user1", format="markdown")
        assert content is not None
        assert "# Teste" in content
        assert "Ola" in content

    def test_export_json(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        tmp_data.add_message(conv["id"], "user1", "user", "Ola")
        content = tmp_data.export_conversation(conv["id"], "user1", format="json")
        assert content is not None
        import json

        data = json.loads(content)
        assert data["title"] == "Teste"


class TestDelete:
    def test_delete_conversation(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        ok = tmp_data.delete_conversation(conv["id"], "user1")
        assert ok is True
        found = tmp_data.get_conversation(conv["id"], "user1")
        assert found is None

    def test_cannot_delete_other_user_conv(self, tmp_data: ConversationHistoryService):
        conv = tmp_data.create_conversation("user1", title="Teste")
        ok = tmp_data.delete_conversation(conv["id"], "user2")
        assert ok is False
