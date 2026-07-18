from datetime import datetime

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ConversationItem(QListWidgetItem):
    def __init__(self, conv_id: str, title: str, timestamp: datetime, parent=None):
        super().__init__(parent)
        self.conv_id = conv_id
        self.title = title
        self.timestamp = timestamp
        self.setData(Qt.UserRole, conv_id)
        self._update_display()

    def _update_display(self):
        time_str = self.timestamp.strftime("%d/%m %H:%M")
        self.setText(f"{self.title}\n{time_str}")
        self.setToolTip(f"{self.title}\n{self.timestamp.strftime('%d/%m/%Y %H:%M')}")


class Sidebar(QWidget):
    """Light sidebar with conversation history, memory toggle, and settings."""

    new_chat_requested = Signal()
    conversation_selected = Signal(str)
    conversation_delete_requested = Signal(str)
    conversation_rename_requested = Signal(str, str)
    toggle_memories = Signal(bool)
    open_memories = Signal()
    settings_requested = Signal()

    BG = "#FFFFFF"
    BG_SECONDARY = "#F5F5F7"
    BG_HOVER = "#F0F0F2"
    BG_SELECTED = "#E8E8ED"
    BORDER = "#E5E5EA"
    TEXT_PRIMARY = "#1A1A1B"
    TEXT_SECONDARY = "#8E8E93"
    TEXT_MUTED = "#AEAEB2"
    ACCENT = "#000000"
    RED = "#FF3B30"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self._conversations: dict[str, ConversationItem] = {}
        self._memories_enabled = True
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QWidget {{
                background: {self.BG};
                border-right: 1px solid {self.BORDER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(f"background: {self.BG}; border-bottom: 1px solid {self.BORDER};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("Celsius")
        title.setStyleSheet(
            f"color: {self.TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.new_chat_btn = QPushButton()
        self.new_chat_btn.setIcon(qta.icon("fa5s.plus", color=self.ACCENT))
        self.new_chat_btn.setToolTip("Nova conversa (Ctrl+N)")
        self.new_chat_btn.setFixedSize(32, 32)
        self.new_chat_btn.setCursor(Qt.PointingHandCursor)
        self.new_chat_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 8px;
            }}
            QPushButton:hover {{
                background: {self.BG_HOVER};
            }}
        """)
        self.new_chat_btn.clicked.connect(self.new_chat_requested.emit)
        header_layout.addWidget(self.new_chat_btn)

        layout.addWidget(header)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar conversas...")
        self.search_input.setFixedHeight(36)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {self.BG_SECONDARY};
                border: 1px solid {self.BORDER};
                border-radius: 8px;
                padding: 0 12px;
                padding-left: 36px;
                color: {self.TEXT_PRIMARY};
                font-size: 13px;
                margin: 8px 12px;
            }}
            QLineEdit:focus {{
                border-color: {self.ACCENT};
            }}
        """)
        self.search_input.addAction(
            qta.icon("fa5s.search", color=self.TEXT_MUTED),
            QLineEdit.LeadingPosition,
        )
        self.search_input.textChanged.connect(self._filter_conversations)
        layout.addWidget(self.search_input)

        # Conversation list
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
                padding: 4px 8px;
            }}
            QListWidget::item {{
                background: transparent;
                border-radius: 8px;
                padding: 10px 12px;
                margin: 2px 4px;
                color: {self.TEXT_PRIMARY};
                font-size: 13px;
            }}
            QListWidget::item:hover {{
                background: {self.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background: {self.BG_SELECTED};
            }}
        """)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget, 1)

        # Bottom section
        bottom = QWidget()
        bottom.setStyleSheet(f"border-top: 1px solid {self.BORDER}; background: {self.BG};")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(12, 12, 12, 12)
        bottom_layout.setSpacing(6)

        # Memory button
        self.memory_btn = QPushButton()
        self.memory_btn.setIcon(qta.icon("fa5s.brain", color="#8E8E93"))
        self.memory_btn.setText("Memorias")
        self.memory_btn.setToolTip("Gerenciar memorias do usuario")
        self.memory_btn.setCursor(Qt.PointingHandCursor)
        self.memory_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {self.BORDER};
                border-radius: 8px;
                color: {self.TEXT_SECONDARY};
                padding: 8px 12px;
                text-align: left;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {self.BG_HOVER};
                border-color: {self.ACCENT};
                color: {self.TEXT_PRIMARY};
            }}
        """)
        self.memory_btn.clicked.connect(self.open_memories.emit)
        bottom_layout.addWidget(self.memory_btn)

        # Settings button
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(qta.icon("fa5s.cog", color="#8E8E93"))
        self.settings_btn.setText("Configuracoes")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {self.BORDER};
                border-radius: 8px;
                color: {self.TEXT_SECONDARY};
                padding: 8px 12px;
                text-align: left;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {self.BG_HOVER};
                border-color: {self.ACCENT};
                color: {self.TEXT_PRIMARY};
            }}
        """)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        bottom_layout.addWidget(self.settings_btn)

        layout.addWidget(bottom)

    def add_conversation(self, conv_id: str, title: str, timestamp: datetime = None):
        if timestamp is None:
            timestamp = datetime.now()
        item = ConversationItem(conv_id, title, timestamp)
        self._conversations[conv_id] = item
        self.list_widget.insertItem(0, item)
        return item

    def update_conversation(self, conv_id: str, title: str):
        if conv_id in self._conversations:
            item = self._conversations[conv_id]
            item.title = title
            item._update_display()

    def remove_conversation(self, conv_id: str):
        if conv_id in self._conversations:
            item = self._conversations.pop(conv_id)
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)

    def set_current_conversation(self, conv_id: str):
        if conv_id in self._conversations:
            self.list_widget.setCurrentItem(self._conversations[conv_id])

    def clear(self):
        self._conversations.clear()
        self.list_widget.clear()

    def _filter_conversations(self, text: str):
        text_lower = text.lower().strip()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if text_lower in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

    def _on_item_clicked(self, item: ConversationItem):
        self.conversation_selected.emit(item.conv_id)

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {self.BG};
                border: 1px solid {self.BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 6px;
                color: {self.TEXT_PRIMARY};
            }}
            QMenu::item:selected {{
                background: {self.BG_HOVER};
            }}
        """)

        rename_action = menu.addAction(qta.icon("fa5s.edit", color="#8E8E93"), "Renomear")
        rename_action.triggered.connect(lambda: self._rename_conversation(item))

        delete_action = menu.addAction(qta.icon("fa5s.trash", color=self.RED), "Excluir")
        delete_action.triggered.connect(
            lambda: self.conversation_delete_requested.emit(item.conv_id)
        )

        menu.exec(QCursor.pos())

    def _rename_conversation(self, item: ConversationItem):
        from PySide6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(
            self, "Renomear conversa", "Novo titulo:", text=item.title
        )
        if ok and new_name.strip():
            item.title = new_name.strip()
            item._update_display()
            self.conversation_rename_requested.emit(item.conv_id, item.title)
