"""
ConversationManager - Gerencia conversas, histórico e persistência.
"""
import json
import os
from datetime import datetime
from uuid import uuid4

from PySide6.QtCore import QObject, Signal


class ConversationManager(QObject):
    """Gerencia conversas: criação, seleção, persistência."""

    conversation_changed = Signal(str)  # conv_id
    conversation_list_changed = Signal()
    conversation_deleted = Signal(str)
    conversation_renamed = Signal(str, str)  # conv_id, new_title

    def __init__(self, settings, memory_service, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.memory_service = memory_service
        self._conversations = {}
        self._current_conv_id = None
        self._load_conversations()

    def _get_conversations_dir(self):
        dir_path = os.path.join(self.settings.base_dir, "conversations")
        os.makedirs(dir_path, exist_ok=True)
        return dir_path

    def _load_conversations(self):
        dir_path = self._get_conversations_dir()
        for fname in sorted(os.listdir(dir_path)):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(dir_path, fname), "r", encoding="utf-8") as f:
                        conv = json.load(f)
                    self._conversations[conv["id"]] = conv
                except Exception:
                    pass

    def _save_conversation(self, conv_id):
        conv = self._conversations.get(conv_id)
        if not conv:
            return
        dir_path = self._get_conversations_dir()
        path = os.path.join(dir_path, f"{conv_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conv, f, ensure_ascii=False, indent=2)

    def create_conversation(self, title: str = "Nova conversa") -> str:
        conv_id = str(uuid4())[:8]
        now = datetime.now().isoformat()
        conv = {
            "id": conv_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._conversations[conv_id] = conv
        self._save_conversation(conv_id)
        self.conversation_list_changed.emit()
        return conv_id

    def set_current(self, conv_id: str):
        if conv_id in self._conversations:
            self._current_conv_id = conv_id
            self.conversation_changed.emit(conv_id)

    def get_current(self):
        return self._current_conv_id

    def get_conversation(self, conv_id: str):
        return self._conversations.get(conv_id)

    def get_messages(self, conv_id: str) -> list[dict]:
        conv = self._conversations.get(conv_id)
        if not conv:
            return []
        return conv.get("messages", [])

    def get_all_conversations(self):
        return sorted(
            self._conversations.values(),
            key=lambda c: c["updated_at"],
            reverse=True
        )

    def add_message(self, conv_id: str, role: str, content: str, attachments: list = None):
        conv = self._conversations.get(conv_id)
        if not conv:
            return
        conv["messages"].append({
            "role": role,
            "content": content,
            "attachments": attachments or [],
            "timestamp": datetime.now().isoformat(),
        })
        conv["updated_at"] = datetime.now().isoformat()
        if len(conv["messages"]) == 1:
            # First message, use as title
            conv["title"] = content[:50] + ("..." if len(content) > 50 else "")
        self._save_conversation(conv_id)
        self.conversation_list_changed.emit()

    def get_history_for_ai(self, conv_id: str, max_turns: int = 20) -> list:
        """Retorna histórico formatado para IA."""
        conv = self._conversations.get(conv_id)
        if not conv:
            return []
        history = []
        for msg in conv["messages"][-max_turns:]:
            if msg["role"] in ("user", "assistant"):
                history.append({"role": msg["role"], "content": msg["content"]})
        return history

    def rename_conversation(self, conv_id: str, new_title: str):
        conv = self._conversations.get(conv_id)
        if not conv:
            return
        conv["title"] = new_title
        conv["updated_at"] = datetime.now().isoformat()
        self._save_conversation(conv_id)
        self.conversation_renamed.emit(conv_id, new_title)
        self.conversation_list_changed.emit()

    def delete_conversation(self, conv_id: str):
        if conv_id not in self._conversations:
            return
        del self._conversations[conv_id]
        dir_path = self._get_conversations_dir()
        path = os.path.join(dir_path, f"{conv_id}.json")
        if os.path.exists(path):
            os.remove(path)
        if self._current_conv_id == conv_id:
            self._current_conv_id = None
            self.conversation_changed.emit("")
        self.conversation_deleted.emit(conv_id)
        self.conversation_list_changed.emit()

    def clear_current_conversation(self):
        if self._current_conv_id:
            conv = self._conversations.get(self._current_conv_id)
            if conv:
                conv["messages"] = []
                conv["updated_at"] = datetime.now().isoformat()
                self._save_conversation(self._current_conv_id)
                self.conversation_list_changed.emit()

    def populate_sidebar(self, sidebar):
        """Preenche sidebar com conversas."""
        sidebar.list_widget.clear()
        for conv in self.get_all_conversations():
            sidebar.add_conversation(conv["id"], conv["title"])
        if self._current_conv_id:
            sidebar.set_current_conversation(self._current_conv_id)

    def get_memories_for_ai(self) -> list:
        """Busca memórias relevantes para o contexto atual."""
        if not self._current_conv_id:
            return []
        msgs = self.get_conversation(self._current_conv_id)
        if not msgs:
            return []
        user_msgs = [m["content"] for m in msgs.get("messages", []) if m["role"] == "user"]
        if not user_msgs:
            return []
        return self.memory_service.search(user_msgs[-1])