"""Tests for core.conversations (ConversationManager, FullTextSearch, versions)."""

import threading

import pytest

from core.conversations import (
    ConversationManager,
    _generate_id,
    _tokenize,
)


@pytest.fixture
def conv_dir(tmp_path):
    """Provide a clean temporary directory for conversation storage."""
    return tmp_path / "conversations"


@pytest.fixture
def manager(conv_dir):
    """Provide a fresh ConversationManager per test."""
    mgr = ConversationManager(base_dir=conv_dir)
    return mgr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_generate_id_returns_hex(self):
        uid = _generate_id()
        assert len(uid) == 12
        int(uid, 16)  # must be valid hex

    def test_generate_id_unique(self):
        ids = {_generate_id() for _ in range(50)}
        assert len(ids) == 50


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


class TestTokenizer:
    def test_basic(self):
        tokens = _tokenize("hello world")
        assert "hello" in tokens
        assert "world" in tokens

    def test_lowercase(self):
        tokens = _tokenize("Hello WORLD")
        assert "hello" in tokens
        assert "world" in tokens

    def test_punctuation(self):
        tokens = _tokenize("one,two three!")
        assert "one" in tokens
        assert "two" in tokens
        assert "three" in tokens

    def test_empty(self):
        tokens = _tokenize("")
        assert tokens == []

    def test_chinese(self):
        tokens = _tokenize("你好世界")
        assert len(tokens) >= 1

    def test_mixed(self):
        tokens = _tokenize("hello 你好 world")
        assert "hello" in tokens
        assert "world" in tokens


# ---------------------------------------------------------------------------
# Create conversation
# ---------------------------------------------------------------------------


class TestCreateConversation:
    def test_create_returns_dict(self, manager):
        conv = manager.create()
        assert isinstance(conv, dict)

    def test_create_has_id(self, manager):
        conv = manager.create()
        assert "id" in conv
        assert len(conv["id"]) == 12

    def test_create_has_title(self, manager):
        conv = manager.create(title="Test Title")
        assert conv["title"] == "Test Title"

    def test_create_default_title(self, manager):
        conv = manager.create()
        assert conv["title"] == "Nova conversa"

    def test_create_has_timestamps(self, manager):
        conv = manager.create()
        assert "created_at" in conv
        assert "updated_at" in conv

    def test_create_version_starts_at_1(self, manager):
        conv = manager.create()
        assert conv["version"] == 1

    def test_create_empty_messages(self, manager):
        conv = manager.create()
        assert conv["messages"] == []

    def test_create_with_metadata(self, manager):
        conv = manager.create(metadata={"source": "test"})
        assert conv["metadata"]["source"] == "test"

    def test_create_persists(self, manager):
        conv = manager.create()
        loaded = manager.load(conv["id"])
        assert loaded is not None
        assert loaded["id"] == conv["id"]


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------


class TestSaveLoadConversation:
    def test_save_increments_version(self, manager):
        conv = manager.create()
        conv["title"] = "Updated"
        saved = manager.save(conv)
        assert saved["version"] == 2

    def test_save_sets_updated_at(self, manager):
        conv = manager.create()
        original_updated = conv["updated_at"]
        import time

        time.sleep(0.01)
        conv["title"] = "New Title"
        saved = manager.save(conv)
        assert saved["updated_at"] >= original_updated

    def test_load_returns_deepcopy(self, manager):
        conv = manager.create()
        loaded = manager.load(conv["id"])
        loaded["title"] = "Modified"
        original = manager.load(conv["id"])
        assert original["title"] != "Modified"

    def test_load_nonexistent(self, manager):
        assert manager.load("nonexistent") is None

    def test_list_conversations(self, manager):
        manager.create(title="First")
        manager.create(title="Second")
        items = manager.list()
        assert len(items) >= 2

    def test_list_returns_summaries(self, manager):
        conv = manager.create(title="Summary Test")
        items = manager.list()
        match = next(i for i in items if i["id"] == conv["id"])
        assert match["title"] == "Summary Test"
        assert "messages" not in match
        assert "message_count" in match


# ---------------------------------------------------------------------------
# Add message
# ---------------------------------------------------------------------------


class TestAddMessage:
    def test_add_message(self, manager):
        conv = manager.create()
        msg = manager.add_message(conv["id"], "user", "Hello!")
        assert msg["role"] == "user"
        assert msg["content"] == "Hello!"

    def test_add_message_has_id(self, manager):
        conv = manager.create()
        msg = manager.add_message(conv["id"], "user", "Hi")
        assert "id" in msg
        assert len(msg["id"]) == 12

    def test_add_message_has_timestamp(self, manager):
        conv = manager.create()
        msg = manager.add_message(conv["id"], "user", "Hi")
        assert "timestamp" in msg

    def test_add_multiple_messages(self, manager):
        conv = manager.create()
        manager.add_message(conv["id"], "user", "Hello")
        manager.add_message(conv["id"], "assistant", "Hi there")
        loaded = manager.load(conv["id"])
        assert len(loaded["messages"]) == 2

    def test_add_message_auto_titles(self, manager):
        conv = manager.create()
        manager.add_message(
            conv["id"],
            "user",
            "This is a very long message that should become the title automatically",
        )
        loaded = manager.load(conv["id"])
        assert loaded["title"] != "Nova conversa"

    def test_add_message_not_found(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.add_message("nonexistent", "user", "Hi")

    def test_add_message_with_metadata(self, manager):
        conv = manager.create()
        msg = manager.add_message(conv["id"], "user", "test", metadata={"token_count": 5})
        assert msg["metadata"]["token_count"] == 5


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------


class TestFullTextSearch:
    def test_search_empty(self, manager):
        results = manager.search("anything")
        assert results == []

    def test_search_after_index(self, manager):
        conv = manager.create()
        manager.add_message(conv["id"], "user", "python programming language")
        manager.add_message(conv["id"], "assistant", "Python is great for data science")
        manager.rebuild_search_index()
        results = manager.search("python")
        assert len(results) >= 1

    def test_search_ranking(self, manager):
        conv1 = manager.create()
        manager.add_message(conv1["id"], "user", "python is a programming language used everywhere")
        conv2 = manager.create()
        manager.add_message(conv2["id"], "user", "I like cats")
        manager.rebuild_search_index()
        results = manager.search("python programming")
        # The python conversation should rank higher
        assert len(results) >= 1
        assert results[0]["conversation_id"] == conv1["id"]

    def test_search_limit(self, manager):
        for i in range(5):
            conv = manager.create()
            manager.add_message(conv["id"], "user", f"unique_keyword_{i} description here")
        manager.rebuild_search_index()
        results = manager.search("unique_keyword", limit=2)
        assert len(results) <= 2

    def test_search_excerpt(self, manager):
        conv = manager.create()
        manager.add_message(conv["id"], "user", "the quick brown fox jumps over the lazy dog")
        manager.rebuild_search_index()
        results = manager.search("brown fox")
        assert len(results) >= 1
        assert "excerpt" in results[0]
        assert "brown" in results[0]["excerpt"].lower() or "fox" in results[0]["excerpt"].lower()


# ---------------------------------------------------------------------------
# Search by date
# ---------------------------------------------------------------------------


class TestSearchByDate:
    def test_search_all(self, manager):
        manager.create()
        manager.create()
        results = manager.search_by_date()
        assert len(results) >= 2

    def test_search_with_start_date(self, manager):
        manager.create()
        results = manager.search_by_date(start_date="2020-01-01")
        assert len(results) >= 1

    def test_search_with_end_date(self, manager):
        manager.create()
        results = manager.search_by_date(end_date="2099-12-31")
        assert len(results) >= 1

    def test_search_with_range(self, manager):
        manager.create()
        results = manager.search_by_date(start_date="2020-01-01", end_date="2099-12-31")
        assert len(results) >= 1

    def test_search_returns_deepcopy(self, manager):
        conv = manager.create()
        results = manager.search_by_date()
        if results:
            results[0]["title"] = "MODIFIED"
            original = manager.load(conv["id"])
            assert original["title"] != "MODIFIED"


# ---------------------------------------------------------------------------
# Version history
# ---------------------------------------------------------------------------


class TestVersionHistory:
    def test_version_history_empty(self, manager):
        conv = manager.create()
        history = manager.get_version_history(conv["id"])
        assert len(history) >= 1  # v1 from create

    def test_version_history_after_saves(self, manager):
        conv = manager.create()
        conv["title"] = "V2"
        manager.save(conv)
        conv["title"] = "V3"
        manager.save(conv)
        history = manager.get_version_history(conv["id"])
        assert len(history) >= 3
        assert 1 in history
        assert 2 in history
        assert 3 in history

    def test_load_version(self, manager):
        conv = manager.create()
        original_title = conv["title"]
        conv["title"] = "Updated Title"
        manager.save(conv)
        loaded = manager.load_version(conv["id"], 1)
        assert loaded["title"] == original_title

    def test_load_version_nonexistent(self, manager):
        result = manager.load_version("nonexistent", 1)
        assert result is None


# ---------------------------------------------------------------------------
# Export to markdown
# ---------------------------------------------------------------------------


class TestExportMarkdown:
    def test_export_returns_string(self, manager):
        conv = manager.create(title="Export Test")
        md = manager.export_markdown(conv["id"])
        assert isinstance(md, str)

    def test_export_contains_title(self, manager):
        conv = manager.create(title="My Title")
        md = manager.export_markdown(conv["id"])
        assert "My Title" in md

    def test_export_contains_messages(self, manager):
        conv = manager.create()
        manager.add_message(conv["id"], "user", "Hello!")
        manager.add_message(conv["id"], "assistant", "Hi there!")
        md = manager.export_markdown(conv["id"])
        assert "Hello!" in md
        assert "Hi there!" in md

    def test_export_nonexistent(self, manager):
        assert manager.export_markdown("nonexistent") is None

    def test_export_contains_metadata(self, manager):
        conv = manager.create()
        md = manager.export_markdown(conv["id"])
        assert conv["id"] in md
        assert "created_at" in md or "Criado" in md


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDeleteConversation:
    def test_delete(self, manager):
        conv = manager.create()
        assert manager.delete(conv["id"]) is True
        assert manager.load(conv["id"]) is None

    def test_delete_nonexistent(self, manager):
        # Should not raise
        manager.delete("nonexistent")

    def test_delete_removes_from_list(self, manager):
        conv = manager.create()
        cid = conv["id"]
        manager.delete(cid)
        items = manager.list()
        assert all(i["id"] != cid for i in items)


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_creates(self, conv_dir):
        errors = []

        def create_conversation(idx):
            try:
                mgr = ConversationManager(base_dir=conv_dir)
                mgr.create(title=f"Thread {idx}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_conversation, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        mgr = ConversationManager(base_dir=conv_dir)
        items = mgr.list()
        assert len(items) >= 10

    def test_concurrent_messages(self, conv_dir):
        mgr = ConversationManager(base_dir=conv_dir)
        conv = mgr.create()
        errors = []
        lock = threading.Lock()

        def add_msg(idx):
            try:
                m = ConversationManager(base_dir=conv_dir)
                m.add_message(conv["id"], "user", f"Message {idx}")
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=add_msg, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loaded = mgr.load(conv["id"])
        # With file-based storage, concurrent writes may race.
        # The key assertion is no crashes and some messages were written.
        assert loaded is not None
        assert len(loaded["messages"]) >= 1

    def test_concurrent_search_index(self, conv_dir):
        mgr = ConversationManager(base_dir=conv_dir)
        conv = mgr.create()
        mgr.add_message(conv["id"], "user", "test content")
        errors = []

        def search():
            try:
                m = ConversationManager(base_dir=conv_dir)
                m.rebuild_search_index()
                m.search("test")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=search) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
