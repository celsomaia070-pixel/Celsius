"""Conversation versioning and full-text search system."""

import builtins
import hashlib
import json
import os
import re
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from core.telemetry import (
    MetricNames,
    record_metric,
    trace_function,
    trace_span,
)

_CONVERSATIONS_DIR = Path(__file__).resolve().parent.parent / "conversations"
_MAX_VERSIONS = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_id() -> str:
    return hashlib.md5(uuid.uuid4().bytes).hexdigest()[:12]


def _tokenize(text: str) -> list[str]:
    """Tokenize text for search indexing.

    Supports English, Portuguese, and Chinese.
    - Splits on whitespace and punctuation
    - Lowercases latin characters
    - Keeps CJK characters as individual tokens
    """
    tokens: list[str] = []
    for chunk in re.findall(r"[\w\u4e00-\u9fff\u3400-\u4dbf]+|[^\s]", text.lower()):
        if len(chunk) == 1 and ord(chunk) >= 0x4E00 or chunk.strip():
            tokens.append(chunk)
    return tokens


class ConversationVersion:
    """Tracks conversation version history with backup rotation."""

    def __init__(self, conversation_id: str, base_dir: Path) -> None:
        self.conversation_id = conversation_id
        self.version_dir = base_dir / conversation_id / "versions"
        self.version_dir.mkdir(parents=True, exist_ok=True)

    def save_backup(self, data: dict[str, Any], version: int) -> Path:
        """Save a versioned backup, pruning old versions beyond _MAX_VERSIONS."""
        path = self.version_dir / f"v{version}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._prune(version)
        return path

    def load_version(self, version: int) -> dict[str, Any] | None:
        path = self.version_dir / f"v{version}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def latest_version(self) -> int:
        versions = sorted(self.version_dir.glob("v*.json"))
        if not versions:
            return 0
        return int(versions[-1].stem[1:])

    def _prune(self, current_version: int) -> None:
        versions = sorted(self.version_dir.glob("v*.json"), key=lambda p: int(p.stem[1:]))
        while len(versions) > _MAX_VERSIONS:
            versions.pop(0).unlink(missing_ok=True)


class FullTextSearch:
    """In-memory full-text search index for conversation messages."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._index: dict[str, list[tuple[str, str, int]]] = {}
        # conversation_id -> [(message_id, content, token_count)]

    @trace_function("conversation.search.reindex")
    def reindex(self, conversations: list[dict[str, Any]]) -> None:
        """Rebuild the full index from a list of conversations."""
        with self._lock:
            self._index.clear()
            for conv in conversations:
                cid = conv.get("id", "")
                msgs = conv.get("messages", [])
                entries: list[tuple[str, str, int]] = []
                for msg in msgs:
                    content = msg.get("content", "")
                    mid = msg.get("id", "")
                    tokens = _tokenize(content)
                    entries.append((mid, content, len(tokens)))
                self._index[cid] = entries

    @trace_function("conversation.search.query")
    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search across all indexed messages, returning ranked results."""
        with self._lock:
            query_tokens = _tokenize(query)
            if not query_tokens:
                return []

            results: list[dict[str, Any]] = []
            for cid, entries in self._index.items():
                for mid, content, _token_count in entries:
                    content_lower = content.lower()
                    score = sum(content_lower.count(t) for t in query_tokens)
                    if score > 0:
                        excerpt = self._make_excerpt(content, query_tokens)
                        results.append(
                            {
                                "conversation_id": cid,
                                "message_id": mid,
                                "score": score,
                                "excerpt": excerpt,
                            }
                        )

            results.sort(key=lambda r: r["score"], reverse=True)
            return results[:limit]

    @staticmethod
    def _make_excerpt(content: str, query_tokens: list[str], window: int = 80) -> str:
        content_lower = content.lower()
        best_pos = 0
        best_score = 0
        for token in query_tokens:
            pos = content_lower.find(token)
            if pos != -1:
                surrounding_score = content_lower.count(token)
                if surrounding_score > best_score:
                    best_score = surrounding_score
                    best_pos = pos

        start = max(0, best_pos - window)
        end = min(len(content), best_pos + window)
        excerpt = content[start:end].strip()
        if start > 0:
            excerpt = "..." + excerpt
        if end < len(content):
            excerpt = excerpt + "..."
        return excerpt

    def index_conversation(self, conv: dict[str, Any]) -> None:
        """Index or update a single conversation in the search index."""
        with self._lock:
            cid = conv.get("id", "")
            msgs = conv.get("messages", [])
            entries: list[tuple[str, str, int]] = []
            for msg in msgs:
                content = msg.get("content", "")
                mid = msg.get("id", "")
                tokens = _tokenize(content)
                entries.append((mid, content, len(tokens)))
            self._index[cid] = entries

    def remove_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._index.pop(conversation_id, None)


class ConversationManager:
    """Manages versioned conversations with full-text search."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._dir = base_dir or _CONVERSATIONS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._search = FullTextSearch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @trace_function("conversation.create")
    def create(
        self, title: str | None = None, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a new conversation with version 1."""
        conv_id = _generate_id()
        now = _now_iso()
        conv: dict[str, Any] = {
            "id": conv_id,
            "title": title or "Nova conversa",
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "metadata": metadata or {},
            "messages": [],
        }
        self._write(conv)
        ver_tracker = ConversationVersion(conv_id, self._dir)
        ver_tracker.save_backup(conv, 1)
        record_metric(MetricNames.TOOL_CALLS_TOTAL, 1, {"operation": "conversation.create"})
        return deepcopy(conv)

    @trace_function("conversation.list")
    def list(self) -> list[dict[str, Any]]:
        """List all conversations (metadata only, no messages)."""
        with self._lock:
            result: list[dict[str, Any]] = []
            for path in sorted(self._dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    summary = {
                        "id": data.get("id"),
                        "title": data.get("title"),
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "version": data.get("version", 1),
                        "message_count": len(data.get("messages", [])),
                    }
                    result.append(summary)
                except (json.JSONDecodeError, KeyError):
                    continue
            return result

    @trace_function("conversation.load")
    def load(self, conversation_id: str) -> dict[str, Any] | None:
        """Load a full conversation including messages."""
        path = self._dir / f"{conversation_id}.json"
        if not path.exists():
            return None
        with self._lock:
            data = json.loads(path.read_text(encoding="utf-8"))
            return deepcopy(data)

    @trace_function("conversation.save")
    def save(self, conversation: dict[str, Any]) -> dict[str, Any]:
        """Save a conversation, incrementing its version and creating a backup."""
        with self._lock:
            conv_id = conversation["id"]
            existing = self._load_raw(conv_id)
            version = (existing.get("version", 0) if existing else 0) + 1
            conversation["version"] = version
            conversation["updated_at"] = _now_iso()

            if not conversation.get("created_at"):
                conversation["created_at"] = conversation["updated_at"]
            if not conversation.get("title") or self._is_default_title(
                conversation.get("title", "")
            ):
                auto = self._auto_title(conversation)
                if not self._is_default_title(auto):
                    conversation["title"] = auto

            ver_tracker = ConversationVersion(conv_id, self._dir)
            ver_tracker.save_backup(conversation, version)

            self._write(conversation)
            self._search.index_conversation(conversation)

            record_metric(MetricNames.TOOL_CALLS_TOTAL, 1, {"operation": "conversation.save"})
            record_metric(
                "celsius.conversation.versions.total",
                version,
                {"conversation_id": conv_id},
            )
            return deepcopy(conversation)

    def load_version(self, conversation_id: str, version: int) -> dict[str, Any] | None:
        """Load a specific backup version of a conversation."""
        vt = ConversationVersion(conversation_id, self._dir)
        data = vt.load_version(version)
        return deepcopy(data) if data else None

    def get_version_history(self, conversation_id: str) -> builtins.list[int]:
        """Return sorted list of available version numbers."""
        vt = ConversationVersion(conversation_id, self._dir)
        files = sorted(vt.version_dir.glob("v*.json"))
        return [int(f.stem[1:]) for f in files]

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    @trace_function("conversation.add_message")
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a message to a conversation and save it."""
        with self._lock:
            conv = self._load_raw(conversation_id)
            if conv is None:
                raise ValueError(f"Conversation {conversation_id} not found")

            msg: dict[str, Any] = {
                "id": _generate_id(),
                "role": role,
                "content": content,
                "timestamp": _now_iso(),
                "metadata": metadata or {},
            }
            conv["messages"].append(msg)
            if len(conv.get("messages", [])) == 1 and self._is_default_title(conv.get("title", "")):
                conv["title"] = self._auto_title(conv)

            self.save(conv)
            record_metric(
                "celsius.conversation.messages.total",
                len(conv["messages"]),
                {"conversation_id": conversation_id},
            )
            return deepcopy(msg)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def rebuild_search_index(self) -> None:
        """Rebuild the full-text search index from disk."""
        with self._lock:
            conversations = []
            for path in self._dir.glob("*.json"):
                try:
                    conversations.append(json.loads(path.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, KeyError):
                    continue
            self._search.reindex(conversations)

    def search(self, query: str, limit: int = 20) -> builtins.list[dict[str, Any]]:
        """Full-text search across all conversations."""
        with trace_span("conversation.search", {"query": query}):
            results = self._search.search(query, limit=limit)
            record_metric(MetricNames.MEMORY_SEARCHES_TOTAL, 1, {"source": "conversation"})
            return results

    def search_by_date(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
    ) -> builtins.list[dict[str, Any]]:
        """Search conversations by updated_at date range (ISO format strings)."""
        with self._lock:
            results: list[dict[str, Any]] = []
            for path in self._dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    updated = data.get("updated_at", "")
                    if start_date and updated < start_date:
                        continue
                    if end_date and updated > end_date:
                        continue
                    results.append(data)
                except (json.JSONDecodeError, KeyError):
                    continue

            results.sort(key=lambda d: d.get("updated_at", ""), reverse=True)
            return [deepcopy(r) for r in results[:limit]]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @trace_function("conversation.export_markdown")
    def export_markdown(self, conversation_id: str) -> str | None:
        """Export a conversation as a Markdown string."""
        conv = self.load(conversation_id)
        if conv is None:
            return None

        lines: list[str] = []
        title = conv.get("title", "Sem titulo")
        lines.append(f"# {title}\n")
        lines.append(f"*ID:* `{conv.get('id', '')}`  ")
        lines.append(f"*Criado:* {conv.get('created_at', '')}  ")
        lines.append(f"*Atualizado:* {conv.get('updated_at', '')}  ")
        lines.append(f"*Versao:* {conv.get('version', 1)}  ")
        lines.append("")
        lines.append("---\n")

        for msg in conv.get("messages", []):
            role = msg.get("role", "unknown")
            timestamp = msg.get("timestamp", "")
            content = msg.get("content", "")
            lines.append(f"### {role.capitalize()} ({timestamp})\n")
            lines.append(f"{content}\n")

        record_metric(
            MetricNames.TOOL_CALLS_TOTAL, 1, {"operation": "conversation.export_markdown"}
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation and its version backups."""
        with self._lock:
            path = self._dir / f"{conversation_id}.json"
            if path.exists():
                path.unlink()
            version_dir = self._dir / conversation_id / "versions"
            if version_dir.exists():
                for f in version_dir.glob("v*.json"):
                    f.unlink()
                version_dir.rmdir()
            parent = self._dir / conversation_id
            if parent.exists():
                parent.rmdir()
            self._search.remove_conversation(conversation_id)
            record_metric(MetricNames.TOOL_CALLS_TOTAL, 1, {"operation": "conversation.delete"})
            return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_raw(self, conversation_id: str) -> dict[str, Any] | None:
        path = self._dir / f"{conversation_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, conversation: dict[str, Any]) -> None:
        path = self._dir / f"{conversation['id']}.json"
        self._dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=self._dir,
            text=True,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(conversation, f, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)

    @staticmethod
    def _auto_title(conv: dict[str, Any]) -> str:
        messages = conv.get("messages", [])
        if not messages:
            return "Nova conversa"
        first_content = messages[0].get("content", "")
        title = first_content[:50].strip()
        if len(first_content) > 50:
            title += "..."
        return title or "Nova conversa"

    @staticmethod
    def _is_default_title(title: str) -> bool:
        return not title or title == "Nova conversa"

    @property
    def search_index(self) -> FullTextSearch:
        return self._search


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: ConversationManager | None = None


def get_conversation_manager(base_dir: Path | None = None) -> ConversationManager:
    """Return a singleton ConversationManager."""
    global _manager
    if _manager is None:
        _manager = ConversationManager(base_dir)
    return _manager


def reset_conversation_manager() -> None:
    """Reset the singleton (useful for tests)."""
    global _manager
    _manager = None
