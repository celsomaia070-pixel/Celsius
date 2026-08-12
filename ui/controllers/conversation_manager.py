"""
ConversationManager - Gerencia conversas, histórico e persistência.
"""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from core.conversations import get_conversation_manager


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
        self._core_manager = get_conversation_manager(
            Path(self.settings.data_dir) / "conversations"
        )
        self._load_conversations()

    def _get_conversations_dir(self):
        dir_path = Path(self.settings.data_dir) / "conversations"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _load_conversations(self):
        self._conversations.clear()
        for summary in self._core_manager.list():
            conv_id = summary.get("id")
            if not conv_id:
                continue
            conv = self._core_manager.load(conv_id)
            if conv:
                self._conversations[conv["id"]] = conv

    def _save_conversation(self, conv_id):
        conv = self._conversations.get(conv_id)
        if not conv:
            return
        saved = self._core_manager.save(conv)
        self._conversations[conv_id] = saved

    def create_conversation(self, title: str = "Nova conversa") -> str:
        conv = self._core_manager.create(title=title)
        conv_id = conv["id"]
        self._conversations[conv_id] = conv
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
        messages = []
        for msg in conv.get("messages", []):
            item = dict(msg)
            metadata = item.get("metadata") or {}
            item["attachments"] = item.get("attachments") or metadata.get("attachments", [])
            messages.append(item)
        return messages

    def get_all_conversations(self):
        return sorted(self._conversations.values(), key=lambda c: c["updated_at"], reverse=True)

    def add_message(self, conv_id: str, role: str, content: str, attachments: list = None):
        conv = self._conversations.get(conv_id)
        if not conv:
            return
        self._core_manager.add_message(
            conv_id,
            role,
            content,
            metadata={"attachments": attachments or []},
        )
        refreshed = self._core_manager.load(conv_id)
        if refreshed:
            self._conversations[conv_id] = refreshed
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
        self._save_conversation(conv_id)
        self.conversation_renamed.emit(conv_id, new_title)
        self.conversation_list_changed.emit()

    def delete_conversation(self, conv_id: str):
        if conv_id not in self._conversations:
            return
        del self._conversations[conv_id]
        self._core_manager.delete(conv_id)
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
