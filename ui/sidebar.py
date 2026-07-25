from datetime import datetime
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QPixmap
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

from core.config import get_settings
from ui.components.base import Divider, IconButton, SearchInput
from ui.icons import icon
from ui.theme.schemes import get_scheme
from ui.theme.tokens import SPACING, RADIUS, TYPOGRAPHY


class ConversationItem(QListWidgetItem):
    def __init__(self, conv_id: str, title: str, timestamp=None, parent=None):
        super().__init__(parent)
        self.conv_id = conv_id
        self.title = title
        self.timestamp = timestamp
        if isinstance(self.timestamp, str):
            try:
                self.timestamp = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
            except:
                self.timestamp = datetime.now()
        elif self.timestamp is None:
            self.timestamp = datetime.now()
        self.setData(Qt.UserRole, conv_id)
        self._update_display()

    def _update_display(self):
        if self.timestamp:
            time_str = self.timestamp.strftime("%d/%m %H:%M")
            self.setText(f"{self.title}\n{time_str}")
            self.setToolTip(f"{self.title}\n{self.timestamp.strftime('%d/%m/%Y %H:%M')}")
        else:
            self.setText(self.title)


class Sidebar(QWidget):
    """Light sidebar with conversation history, memory toggle, and settings."""

    new_chat_requested = Signal()
    conversation_selected = Signal(str)
    conversation_delete_requested = Signal(str)
    conversation_rename_requested = Signal(str, str)
    toggle_memories = Signal(bool)
    open_memories = Signal()
    settings_requested = Signal()
    tab_changed = Signal(str)  # "conversas" | "estoque"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self._conversations: dict[str, ConversationItem] = {}
        self._memories_enabled = True
        self._scheme = None
        self._active_tab = "conversas"
        self._setup_ui()

    def set_scheme(self, scheme):
        """Update color scheme and reapply styles."""
        self._scheme = scheme
        self._apply_scheme()
        self._update_tab_styles()
        if hasattr(self, 'search_input') and hasattr(self.search_input, 'set_scheme'):
            self.search_input.set_scheme(scheme)

    def _apply_scheme(self):
        if not self._scheme:
            return
        s = self._scheme
        self.setStyleSheet(f"""
            QWidget {{
                background: {s.bg_primary};
                border-right: 1px solid {s.border_default};
            }}
        """)

    def _setup_ui(self):
        s = self._scheme or get_scheme()
        self.setStyleSheet(f"""
            QWidget {{
                background: {s.bg_primary};
                border-right: 1px solid {s.border_default};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(SPACING.space_4, 0, SPACING.space_4, 0)

        title = QLabel()
        title.setStyleSheet("background: transparent; border: none;")
        settings = get_settings()
        logo_path = os.path.join(settings.base_dir, "logo", "logo.png")
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            title.setPixmap(pixmap.scaledToHeight(32, Qt.SmoothTransformation))
        else:
            title.setText("Celsius")
            title.setStyleSheet(
                f"color: {s.text_primary}; font-size: {TYPOGRAPHY.text_xl}px; font-weight: {TYPOGRAPHY.weight_bold};"
                " background: transparent; border: none;"
            )
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.new_chat_btn = QPushButton()
        self.new_chat_btn.setIcon(icon("plus", s.accent_primary))
        self.new_chat_btn.setToolTip("Nova conversa (Ctrl+N)")
        self.new_chat_btn.setFixedSize(32, 32)
        self.new_chat_btn.setCursor(Qt.PointingHandCursor)
        self.new_chat_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: {RADIUS.radius_md}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
        """)
        self.new_chat_btn.clicked.connect(self.new_chat_requested.emit)
        header_layout.addWidget(self.new_chat_btn)

        layout.addWidget(header)

        # Tab bar
        tab_bar = QWidget()
        tab_bar.setFixedHeight(40)
        tab_bar.setStyleSheet(f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};")
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(SPACING.space_3, 0, SPACING.space_3, 0)
        tab_layout.setSpacing(0)

        self._tab_conversas = QPushButton("Conversas")
        self._tab_conversas.setCheckable(True)
        self._tab_conversas.setChecked(True)
        self._tab_conversas.setCursor(Qt.PointingHandCursor)
        self._tab_estoque = QPushButton("Estoque")
        self._tab_estoque.setCheckable(True)
        self._tab_estoque.setCursor(Qt.PointingHandCursor)

        tab_buttons = [self._tab_conversas, self._tab_estoque]

        for btn in tab_buttons:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {s.text_muted}; font-size: {TYPOGRAPHY.text_sm}px; font-weight: {TYPOGRAPHY.weight_semibold};
                    padding: {SPACING.space_2}px {SPACING.space_3}px; border-bottom: 2px solid transparent;
                }}
                QPushButton:hover {{
                    color: {s.text_primary};
                }}
                QPushButton:checked {{
                    color: {s.text_primary};
                    border-bottom: 2px solid {s.accent_primary};
                }}
            """)
            tab_layout.addWidget(btn)

        self._tab_conversas.clicked.connect(lambda: self._switch_tab("conversas"))
        self._tab_estoque.clicked.connect(lambda: self._switch_tab("estoque"))
        layout.addWidget(tab_bar)

        # Search
        self.search_input = SearchInput(placeholder="Buscar conversas...", icon_name="search")
        self.search_input.setContentsMargins(SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2)
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
                padding: {SPACING.space_1}px {SPACING.space_2}px;
            }}
            QListWidget::item {{
                background: transparent;
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_3}px {SPACING.space_3}px;
                margin: {SPACING.space_1}px {SPACING.space_1}px;
                color: {s.text_primary};
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
            QListWidget::item:hover {{
                background: {s.bg_hover};
            }}
            QListWidget::item:selected {{
                background: {s.bg_active};
            }}
        """)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget, 1)

        # Inventory panel placeholder (will be replaced by window.py)
        self.inventory_container = QWidget()
        self.inventory_container.setLayout(QVBoxLayout())
        self.inventory_container.layout().setContentsMargins(0, 0, 0, 0)
        self.inventory_container.hide()
        layout.addWidget(self.inventory_container, 1)

        # Bottom section
        bottom = QWidget()
        bottom.setStyleSheet(f"border-top: 1px solid {s.border_default}; background: {s.bg_primary};")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(SPACING.space_3, SPACING.space_3, SPACING.space_3, SPACING.space_3)
        bottom_layout.setSpacing(SPACING.space_1)

        # Memory button
        self.memory_btn = QPushButton()
        self.memory_btn.setIcon(icon("brain", s.text_muted))
        self.memory_btn.setText("Memorias")
        self.memory_btn.setToolTip("Gerenciar memorias do usuario")
        self.memory_btn.setCursor(Qt.PointingHandCursor)
        self.memory_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_md}px;
                color: {s.text_secondary};
                padding: {SPACING.space_2}px {SPACING.space_3}px;
                text-align: left;
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
                border-color: {s.accent_primary};
                color: {s.text_primary};
            }}
        """)
        self.memory_btn.clicked.connect(self.open_memories.emit)
        bottom_layout.addWidget(self.memory_btn)

        # Settings button
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(icon("cog", s.text_muted))
        self.settings_btn.setText("Configuracoes")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_md}px;
                color: {s.text_secondary};
                padding: {SPACING.space_2}px {SPACING.space_3}px;
                text-align: left;
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
                border-color: {s.accent_primary};
                color: {s.text_primary};
            }}
        """)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        bottom_layout.addWidget(self.settings_btn)

        layout.addWidget(bottom)

    def _switch_tab(self, tab: str):
        if tab == self._active_tab:
            return
        self._active_tab = tab

        self._tab_conversas.setChecked(tab == "conversas")
        self._tab_estoque.setChecked(tab == "estoque")

        is_conversas = tab == "conversas"
        self.search_input.setPlaceholderText(
            "Buscar conversas..." if is_conversas else "Buscar itens..."
        )
        self.search_input.setVisible(is_conversas)
        self.list_widget.setVisible(is_conversas)
        self.new_chat_btn.setVisible(is_conversas)
        self.inventory_container.setVisible(tab == "estoque")

        self.tab_changed.emit(tab)

    def _update_tab_styles(self):
        tab_buttons = [self._tab_conversas, self._tab_estoque]
        for btn in tab_buttons:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {self._scheme.text_muted}; font-size: {TYPOGRAPHY.text_sm}px; font-weight: {TYPOGRAPHY.weight_semibold};
                    padding: {SPACING.space_2}px {SPACING.space_3}px; border-bottom: 2px solid transparent;
                }}
                QPushButton:hover {{
                    color: {self._scheme.text_primary};
                }}
                QPushButton:checked {{
                    color: {self._scheme.text_primary};
                    border-bottom: 2px solid {self._scheme.accent_primary};
                }}
            """)

    def install_inventory_panel(self, panel: QWidget):
        """Replace inventory container with actual panel widget."""
        layout = self.inventory_container.layout()
        layout.addWidget(panel)

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
                background: {self._scheme.bg_primary};
                border: 1px solid {self._scheme.border_default};
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_1}px;
            }}
            QMenu::item {{
                padding: {SPACING.space_2}px {SPACING.space_6}px;
                border-radius: {RADIUS.radius_sm}px;
                color: {self._scheme.text_primary};
            }}
            QMenu::item:selected {{
                background: {self._scheme.bg_hover};
            }}
        """)

        rename_action = menu.addAction(icon("edit", "#8E8E93"), "Renomear")
        rename_action.triggered.connect(lambda: self._rename_conversation(item))

        delete_action = menu.addAction(icon("trash", self._scheme.error), "Excluir")
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
