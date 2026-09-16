"""Advanced conversation history with multi-user support, search, and statistics."""

from __future__ import annotations

import json
import logging
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.conversations import _generate_id, _now_iso, _tokenize
from core.json_persistence import atomic_write_json, read_json

logger = logging.getLogger(__name__)


class ConversationHistoryService:
    """Extended conversation history with user isolation, advanced search, and stats."""

    def __init__(self, base_dir: Path | None = None):
        from core.settings import get_settings

        self._dir = Path(base_dir or get_settings().data_dir / "conversation_history")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._sharing_dir = self._dir / "shares"
        self._sharing_dir.mkdir(parents=True, exist_ok=True)

    def _conv_file(self, conversation_id: str) -> Path:
        return self._dir / f"{conversation_id}.json"

    def _share_file(self, share_id: str) -> Path:
        return self._sharing_dir / f"{share_id}.json"

    def create_conversation(
        self,
        user_id: str,
        title: str = "Nova conversa",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conv_id = _generate_id()
        now = _now_iso()
        conv: dict[str, Any] = {
            "id": conv_id,
            "user_id": user_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "metadata": metadata or {},
            "messages": [],
            "shared": False,
            "tags": [],
        }
        atomic_write_json(self._conv_file(conv_id), conv)
        return deepcopy(conv)

    def get_conversation(
        self, conversation_id: str, user_id: str | None = None
    ) -> dict[str, Any] | None:
        path = self._conv_file(conversation_id)
        data = read_json(path, None)
        if data is None:
            return None
        if user_id and data.get("user_id") != user_id:
            return None
        return deepcopy(data)

    def update_conversation(
        self,
        conversation_id: str,
        user_id: str,
        *,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            conv = self.get_conversation(conversation_id, user_id)
            if conv is None:
                return None
            if title is not None:
                conv["title"] = title
            if tags is not None:
                conv["tags"] = tags
            conv["updated_at"] = _now_iso()
            conv["version"] = conv.get("version", 0) + 1
            atomic_write_json(self._conv_file(conversation_id), conv)
            return deepcopy(conv)

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        with self._lock:
            conv = self.get_conversation(conversation_id, user_id)
            if conv is None:
                return False
            path = self._conv_file(conversation_id)
            if path.exists():
                path.unlink()
            return True

    def add_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            conv = self.get_conversation(conversation_id, user_id)
            if conv is None:
                return None
            msg: dict[str, Any] = {
                "id": _generate_id(),
                "role": role,
                "content": content,
                "timestamp": _now_iso(),
                "metadata": metadata or {},
            }
            conv["messages"].append(msg)
            conv["updated_at"] = _now_iso()
            conv["version"] = conv.get("version", 0) + 1
            if (
                len(conv["messages"]) == 1
                and not conv.get("title")
                or conv.get("title") == "Nova conversa"
            ):
                conv["title"] = content[:50].strip() + ("..." if len(content) > 50 else "")
            atomic_write_json(self._conv_file(conversation_id), conv)
            return deepcopy(msg)

    def list_user_conversations(
        self,
        user_id: str,
        *,
        tag: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for path in self._dir.glob("*.json"):
            try:
                data = read_json(path, None)
                if data is None or data.get("user_id") != user_id:
                    continue
                if tag and tag not in data.get("tags", []):
                    continue
                summary = {
                    "id": data.get("id"),
                    "title": data.get("title"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "message_count": len(data.get("messages", [])),
                    "tags": data.get("tags", []),
                    "shared": data.get("shared", False),
                }
                results.append(summary)
            except Exception:
                continue
        results.sort(key=lambda d: d.get("updated_at", ""), reverse=True)
        return results[offset : offset + limit]

    def search_conversations(
        self,
        user_id: str,
        query: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        tag: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query_tokens = _tokenize(query)
        results: list[dict[str, Any]] = []
        for path in self._dir.glob("*.json"):
            try:
                data = read_json(path, None)
                if data is None or data.get("user_id") != user_id:
                    continue
                updated = data.get("updated_at", "")
                if start_date and updated < start_date:
                    continue
                if end_date and updated > end_date:
                    continue
                if tag and tag not in data.get("tags", []):
                    continue
                score = 0
                excerpts: list[str] = []
                title = data.get("title", "")
                title_lower = title.lower()
                for t in query_tokens:
                    if t in title_lower:
                        score += 3
                for msg in data.get("messages", []):
                    content = msg.get("content", "")
                    content_lower = content.lower()
                    for t in query_tokens:
                        cnt = content_lower.count(t)
                        if cnt > 0:
                            score += cnt
                            excerpt = _make_excerpt(content, query_tokens)
                            if excerpt not in excerpts:
                                excerpts.append(excerpt)
                if score > 0:
                    results.append(
                        {
                            "conversation_id": data.get("id"),
                            "title": title,
                            "score": score,
                            "excerpts": excerpts[:3],
                            "message_count": len(data.get("messages", [])),
                            "updated_at": updated,
                        }
                    )
            except Exception:
                continue
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    def get_statistics(self, user_id: str) -> dict[str, Any]:
        total_conversations = 0
        total_messages = 0
        total_words = 0
        user_messages = 0
        assistant_messages = 0
        earliest: str | None = None
        latest: str | None = None
        for path in self._dir.glob("*.json"):
            try:
                data = read_json(path, None)
                if data is None or data.get("user_id") != user_id:
                    continue
                total_conversations += 1
                msgs = data.get("messages", [])
                total_messages += len(msgs)
                for msg in msgs:
                    content = msg.get("content", "")
                    total_words += len(content.split())
                    if msg.get("role") == "user":
                        user_messages += 1
                    elif msg.get("role") == "assistant":
                        assistant_messages += 1
                created = data.get("created_at", "")
                updated = data.get("updated_at", "")
                if created and (earliest is None or created < earliest):
                    earliest = created
                if updated and (latest is None or updated > latest):
                    latest = updated
            except Exception:
                continue
        return {
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "total_words": total_words,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "earliest_conversation": earliest,
            "latest_conversation": latest,
        }

    def share_conversation(
        self,
        conversation_id: str,
        user_id: str,
        *,
        expires_hours: int = 24,
        max_views: int = 0,
    ) -> dict[str, Any] | None:
        conv = self.get_conversation(conversation_id, user_id)
        if conv is None:
            return None
        share_id = _generate_id()
        now = datetime.now(timezone.utc)
        share_data: dict[str, Any] = {
            "share_id": share_id,
            "conversation_id": conversation_id,
            "owner_id": user_id,
            "title": conv.get("title", ""),
            "messages": conv.get("messages", []),
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=expires_hours)).isoformat(),
            "max_views": max_views,
            "view_count": 0,
            "is_active": True,
        }
        atomic_write_json(self._share_file(share_id), share_data)
        conv["shared"] = True
        atomic_write_json(self._conv_file(conversation_id), conv)
        return deepcopy(share_data)

    def get_shared_conversation(self, share_id: str) -> dict[str, Any] | None:
        path = self._share_file(share_id)
        data = read_json(path, None)
        if data is None:
            return None
        if not data.get("is_active"):
            return None
        expires_at = data.get("expires_at", "")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                if datetime.now(timezone.utc) > exp:
                    data["is_active"] = False
                    atomic_write_json(path, data)
                    return None
            except ValueError:
                pass
        max_views = data.get("max_views", 0)
        if max_views > 0 and data.get("view_count", 0) >= max_views:
            data["is_active"] = False
            atomic_write_json(path, data)
            return None
        data["view_count"] = data.get("view_count", 0) + 1
        atomic_write_json(path, data)
        return deepcopy(data)

    def revoke_share(self, share_id: str) -> bool:
        path = self._share_file(share_id)
        data = read_json(path, None)
        if data is None:
            return False
        data["is_active"] = False
        atomic_write_json(path, data)
        return True

    def export_conversation(
        self, conversation_id: str, user_id: str, format: str = "markdown"
    ) -> str | None:
        conv = self.get_conversation(conversation_id, user_id)
        if conv is None:
            return None
        if format == "json":
            return json.dumps(conv, ensure_ascii=False, indent=2)
        lines: list[str] = []
        title = conv.get("title", "Sem titulo")
        lines.append(f"# {title}\n")
        lines.append(f"*ID:* `{conv.get('id', '')}`  ")
        lines.append(f"*Criado:* {conv.get('created_at', '')}  ")
        lines.append(f"*Atualizado:* {conv.get('updated_at', '')}  ")
        lines.append(f"*Versoes:* {conv.get('version', 1)}  ")
        tags = conv.get("tags", [])
        if tags:
            lines.append(f"*Tags:* {', '.join(tags)}  ")
        lines.append("")
        lines.append("---\n")
        for msg in conv.get("messages", []):
            role = msg.get("role", "unknown")
            timestamp = msg.get("timestamp", "")
            content = msg.get("content", "")
            lines.append(f"### {role.capitalize()} ({timestamp})\n")
            lines.append(f"{content}\n")
        return "\n".join(lines)


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


_history_service: ConversationHistoryService | None = None
_history_lock = threading.Lock()


def get_conversation_history_service() -> ConversationHistoryService:
    global _history_service
    if _history_service is None:
        with _history_lock:
            if _history_service is None:
                _history_service = ConversationHistoryService()
    return _history_service


def reset_conversation_history_service() -> None:
    global _history_service
    with _history_lock:
        _history_service = None
