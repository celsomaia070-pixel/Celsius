from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCursor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.modules import module_catalog, sidebar_modules
from core.settings import get_settings
from ui.components.base import SearchInput
from ui.icons import icon
from ui.theme.schemes import get_scheme
from ui.theme.tokens import RADIUS, SPACING, TYPOGRAPHY


class ConversationItem(QListWidgetItem):
    def __init__(self, conv_id: str, title: str, timestamp=None, parent=None):
        super().__init__(parent)
        self.conv_id = conv_id
        self.title = title
        self.timestamp = timestamp
        if isinstance(self.timestamp, str):
            try:
                self.timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            except Exception:
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
    """Light sidebar with conversation history, memory access, and suppliers."""

    new_chat_requested = Signal()
    conversation_selected = Signal(str)
    conversation_delete_requested = Signal(str)
    conversation_rename_requested = Signal(str, str)
    toggle_memories = Signal(bool)
    open_memories = Signal()
    settings_requested = Signal()
    suppliers_requested = Signal()
    mobile_pair_requested = Signal()
    module_selected = Signal(str)
    tab_changed = Signal(str)  # "conversas" | "estoque"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self._conversations: dict[str, ConversationItem] = {}
        self._memories_enabled = True
        self._scheme = None
        self._active_tab = "chat"
        self._module_buttons: dict[str, QPushButton] = {}
        self._setup_ui()

    def set_scheme(self, scheme):
        """Update color scheme and reapply styles."""
        self._scheme = scheme
        self._apply_scheme()
        self._update_tab_styles()
        if hasattr(self, "search_input") and hasattr(self.search_input, "set_scheme"):
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
        self._header.setStyleSheet(
            f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};"
        )
        self._title_label.setStyleSheet(
            f"color: {s.text_primary}; font-size: {TYPOGRAPHY.text_xl}px; "
            f"font-weight: {TYPOGRAPHY.weight_bold}; background: transparent; border: none;"
        )
        self._set_brand_logo()
        self.new_chat_btn.setIcon(icon("plus", s.accent_primary))
        self.new_chat_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: {RADIUS.radius_md}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
        """)
        self._tab_bar.setStyleSheet(
            f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};"
        )
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
        self._bottom.setStyleSheet(
            f"border-top: 1px solid {s.border_default}; background: {s.bg_primary};"
        )
        for button in self._module_buttons.values():
            module_id = button.property("module_id")
            module = next((m for m in module_catalog() if m.id == module_id), None)
            if module:
                button.setIcon(icon(module.icon, s.text_muted))
            button.setStyleSheet(self._module_button_style(s))

        for button, icon_name in (
            (self.memory_btn, "brain"),
            (self.mobile_btn, "smartphone"),
        ):
            button.setIcon(icon(icon_name, s.text_muted))
            button.setStyleSheet(f"""
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
        self._header = QWidget()
        self._header.setFixedHeight(56)
        self._header.setStyleSheet(
            f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};"
        )
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(SPACING.space_4, 0, SPACING.space_4, 0)

        self._title_label = QLabel()
        self._title_label.setStyleSheet("background: transparent; border: none;")
        self._set_brand_logo()
        header_layout.addWidget(self._title_label)
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

        layout.addWidget(self._header)

        # Tab bar
        self._tab_bar = QWidget()
        self._tab_bar.setStyleSheet(
            f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};"
        )
        self._module_bar_layout = QVBoxLayout(self._tab_bar)
        self._module_bar_layout.setContentsMargins(
            SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2
        )
        self._module_bar_layout.setSpacing(SPACING.space_1)
        self.configure_modules(sidebar_modules(get_settings().modules.enabled))
        layout.addWidget(self._tab_bar)

        # Search
        self.search_input = SearchInput(placeholder="Buscar conversas...", icon_name="search")
        self.search_input.setContentsMargins(
            SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2
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
        self._bottom = QWidget()
        self._bottom.setStyleSheet(
            f"border-top: 1px solid {s.border_default}; background: {s.bg_primary};"
        )
        bottom_layout = QVBoxLayout(self._bottom)
        bottom_layout.setContentsMargins(
            SPACING.space_3, SPACING.space_3, SPACING.space_3, SPACING.space_3
        )
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

        self.mobile_btn = QPushButton()
        self.mobile_btn.setIcon(icon("smartphone", s.text_muted))
        self.mobile_btn.setText("Celular / QR Code")
        self.mobile_btn.setToolTip("Abrir QR Code para conectar ou reconectar o celular")
        self.mobile_btn.setCursor(Qt.PointingHandCursor)
        self.mobile_btn.setStyleSheet(f"""
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
        self.mobile_btn.clicked.connect(self.mobile_pair_requested.emit)
        bottom_layout.addWidget(self.mobile_btn)

        self.suppliers_btn = self._module_buttons.get("suppliers", QPushButton())
        self.settings_btn = self._module_buttons.get("settings", QPushButton())

        layout.addWidget(self._bottom)

    def _set_brand_logo(self):
        s = self._scheme or get_scheme()
        pixmap = self._render_brand_svg(s)
        if pixmap.isNull():
            settings = get_settings()
            png_path = Path(settings.base_dir) / "logo" / "logo.png"
            pixmap = QPixmap(str(png_path))
            if not pixmap.isNull():
                pixmap = pixmap.scaledToHeight(32, Qt.SmoothTransformation)

        if not pixmap.isNull():
            self._title_label.setText("")
            self._title_label.setPixmap(pixmap)
            self._title_label.setFixedSize(pixmap.size())
            self._title_label.setStyleSheet("background: transparent; border: none;")
            return

        self._title_label.setPixmap(QPixmap())
        self._title_label.setMinimumSize(0, 0)
        self._title_label.setMaximumSize(16777215, 16777215)
        self._title_label.setText("Celsius")
        self._title_label.setStyleSheet(
            f"color: {s.text_primary}; font-size: {TYPOGRAPHY.text_xl}px; "
            f"font-weight: {TYPOGRAPHY.weight_bold}; background: transparent; border: none;"
        )

    def _render_brand_svg(self, scheme) -> QPixmap:
        settings = get_settings()
        svg_path = Path(settings.base_dir) / "logo" / "celsius-logo.svg"
        if not svg_path.exists():
            return QPixmap()
        try:
            svg = svg_path.read_text(encoding="utf-8")
        except OSError:
            return QPixmap()

        accent_2 = getattr(scheme, "accent_hover", scheme.accent_primary)
        svg = (
            svg.replace("__TEXT__", scheme.text_primary)
            .replace("__MUTED__", scheme.text_secondary)
            .replace("__ACCENT_2__", accent_2)
            .replace("__ACCENT__", scheme.accent_primary)
        )
        renderer = QSvgRenderer(bytearray(svg.encode("utf-8")))
        if not renderer.isValid():
            return QPixmap()

        pixmap = QPixmap(QSize(176, 32))
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()
        return pixmap

    def _switch_tab(self, tab: str):
        if tab == self._active_tab:
            if tab == "suppliers":
                self.suppliers_requested.emit()
            elif tab == "settings":
                self.settings_requested.emit()
            elif tab not in {"chat", "inventory"}:
                self.module_selected.emit(tab)
                self.tab_changed.emit(tab)
            return
        self._active_tab = tab

        for module_id, button in self._module_buttons.items():
            button.setChecked(module_id == tab)

        if hasattr(self, "search_input"):
            is_conversas = tab == "chat"
            self.search_input.setPlaceholderText(
                "Buscar conversas..." if is_conversas else "Buscar itens..."
            )
            self.search_input.setVisible(is_conversas)
            self.list_widget.setVisible(is_conversas)
            self.new_chat_btn.setVisible(is_conversas)
            self.inventory_container.setVisible(tab == "inventory")

        self.module_selected.emit(tab)
        if tab == "suppliers":
            self.suppliers_requested.emit()
        elif tab == "settings":
            self.settings_requested.emit()
        self.tab_changed.emit(tab)

    def _update_tab_styles(self):
        if not self._scheme:
            return
        for btn in self._module_buttons.values():
            btn.setStyleSheet(self._module_button_style(self._scheme))

    def _module_button_style(self, scheme):
        return f"""
            QPushButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: {RADIUS.radius_md}px;
                color: {scheme.text_muted};
                font-size: {TYPOGRAPHY.text_sm}px;
                font-weight: {TYPOGRAPHY.weight_semibold};
                padding: {SPACING.space_2}px {SPACING.space_3}px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {scheme.bg_hover};
                color: {scheme.text_primary};
            }}
            QPushButton:checked {{
                background: {scheme.bg_active};
                border-color: {scheme.accent_primary};
                color: {scheme.text_primary};
            }}
        """

    def configure_modules(self, modules):
        while self._module_bar_layout.count():
            item = self._module_bar_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        s = self._scheme or get_scheme()
        self._module_buttons = {}
        for module in modules:
            button = QPushButton(module.name)
            button.setProperty("module_id", module.id)
            button.setIcon(icon(module.icon, s.text_muted))
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(module.description)
            button.setStyleSheet(self._module_button_style(s))
            button.clicked.connect(lambda checked=False, mid=module.id: self._switch_tab(mid))
            self._module_buttons[module.id] = button
            self._module_bar_layout.addWidget(button)

        self.suppliers_btn = self._module_buttons.get("suppliers", QPushButton())
        self.settings_btn = self._module_buttons.get("settings", QPushButton())
        self._module_bar_layout.addStretch()
        if self._active_tab not in self._module_buttons:
            self._active_tab = "chat"
        for module_id, button in self._module_buttons.items():
            button.setChecked(module_id == self._active_tab)

    def set_active_tab(self, tab: str):
        self._active_tab = ""
        self._switch_tab(tab)

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
