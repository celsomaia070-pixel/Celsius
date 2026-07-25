from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.icons import icon
from ui.theme.schemes import ColorScheme, get_scheme


class CommandPalette(QDialog):
    """Command palette (Cmd+K) for quick actions."""

    action_triggered = Signal(str)  # action_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Dialog | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.resize(600, 400)

        self._scheme = get_scheme()
        self._actions = []
        self._filtered_actions = []
        self._setup_ui()
        self._register_default_actions()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        s = self._scheme
        self.container.setStyleSheet(f"""
            #container {{
                background: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: 12px;
            }}
        """)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {s.bg_primary};
                border: none;
                border-bottom: 1px solid {s.border_default};
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                color: {s.text_primary};
                padding: 16px 20px;
                font-size: 15px;
            }}
            QLineEdit:focus {{
                outline: none;
            }}
        """)
        self.results_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                border: none;
                padding: 12px 20px;
                color: {s.text_primary};
                font-size: 13px;
            }}
            QListWidget::item:selected {{
                background: {s.accent_subtle};
                color: {s.accent_primary};
            }}
            QListWidget::item:hover {{
                background: {s.bg_hover};
            }}
        """)
        self._refresh_items()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        s = self._scheme

        self.container = QWidget()
        self.container.setObjectName("container")
        self.container.setStyleSheet(f"""
            #container {{
                background: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: 12px;
            }}
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Digite um comando ou pesquise...  (Esc para fechar)")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {s.bg_primary};
                border: none;
                border-bottom: 1px solid {s.border_default};
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                color: {s.text_primary};
                padding: 16px 20px;
                font-size: 15px;
            }}
            QLineEdit:focus {{
                outline: none;
            }}
        """)
        self.search_input.textChanged.connect(self._filter_actions)
        container_layout.addWidget(self.search_input)

        self.results_list = QListWidget()
        self.results_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                border: none;
                padding: 12px 20px;
                color: {s.text_primary};
                font-size: 13px;
            }}
            QListWidget::item:selected {{
                background: {s.accent_subtle};
                color: {s.accent_primary};
            }}
            QListWidget::item:hover {{
                background: {s.bg_hover};
            }}
        """)
        self.results_list.itemActivated.connect(self._on_item_activated)
        container_layout.addWidget(self.results_list)

        layout.addWidget(self.container)

    def _register_default_actions(self):
        actions = [
            ("new_chat", "Nova conversa", "fa5s.plus", "Ctrl+N"),
            ("clear_chat", "Limpar conversa", "fa5s.trash", "Ctrl+Shift+Del"),
            ("toggle_sidebar", "Alternar barra lateral", "fa5s.sidebar", "Ctrl+B"),
            ("toggle_theme", "Alternar tema claro/escuro", "fa5s.moon", "Ctrl+Shift+L"),
            ("settings", "Configurações", "fa5s.cog", "Ctrl+,"),
            ("export_chat", "Exportar conversa", "fa5s.file-export", ""),
            ("import_chat", "Importar conversa", "fa5s.file-import", ""),
            ("change_model", "Trocar modelo", "fa5s.cube", ""),
            ("voice_toggle", "Ativar/Desativar voz", "fa5s.microphone", ""),
            ("generate_report", "Gerar relatório", "fa5s.file-alt", ""),
            ("web_search", "Pesquisar na web", "fa5s.search", ""),
            ("run_code", "Executar código", "fa5s.code", ""),
            ("index_document", "Indexar documento (RAG)", "fa5s.database", ""),
            ("list_documents", "Listar documentos indexados", "fa5s.list", ""),
            ("memory_view", "Ver memórias", "fa5s.brain", ""),
            ("add_memory", "Adicionar memória", "fa5s.plus-circle", ""),
        ]

        for action_id, name, icon_name, shortcut in actions:
            self.add_action(action_id, name, icon_name, shortcut)

    def add_action(self, action_id: str, name: str, icon_name: str, shortcut: str = ""):
        self._actions.append({
            "id": action_id,
            "name": name,
            "icon": icon_name,
            "shortcut": shortcut,
        })

    def _filter_actions(self, text: str):
        self._filtered_actions = []
        self.results_list.clear()

        if not text.strip():
            self._filtered_actions = self._actions[:]
        else:
            text_lower = text.lower()
            for action in self._actions:
                if (text_lower in action["name"].lower() or
                    text_lower in action["id"].lower() or
                    text_lower in action.get("shortcut", "").lower()):
                    self._filtered_actions.append(action)

        for action in self._filtered_actions:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, action["id"])

            widget = QWidget()
            w_layout = QHBoxLayout(widget)
            w_layout.setContentsMargins(0, 0, 0, 0)
            w_layout.setSpacing(12)

            icon_label = QLabel()
            icon_label.setPixmap(
                icon(action["icon"], self._scheme.text_secondary).pixmap(20, 20)
            )
            w_layout.addWidget(icon_label)

            name_label = QLabel(action["name"])
            name_label.setStyleSheet(f"color: {self._scheme.text_primary}; font-size: 13px;")
            w_layout.addWidget(name_label)

            w_layout.addStretch()

            if action.get("shortcut"):
                shortcut_label = QLabel(action["shortcut"])
                shortcut_label.setStyleSheet(f"""
                    color: {self._scheme.text_muted};
                    font-size: 11px;
                    font-family: monospace;
                    background: {self._scheme.bg_tertiary};
                    padding: 2px 8px;
                    border-radius: 4px;
                """)
                w_layout.addWidget(shortcut_label)

            item.setSizeHint(widget.sizeHint())
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, widget)

        if self._filtered_actions:
            self.results_list.setCurrentRow(0)

    def _refresh_items(self):
        """Re-render current filtered items with updated theme."""
        current_text = self.search_input.text()
        self._filter_actions(current_text)

    def _on_item_activated(self, item: QListWidgetItem):
        action_id = item.data(Qt.UserRole)
        self.action_triggered.emit(action_id)
        self.hide()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.hide()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            current = self.results_list.currentItem()
            if current:
                self._on_item_activated(current)
        elif event.key() == Qt.Key_Up:
            row = self.results_list.currentRow()
            if row > 0:
                self.results_list.setCurrentRow(row - 1)
        elif event.key() == Qt.Key_Down:
            row = self.results_list.currentRow()
            if row < self.results_list.count() - 1:
                self.results_list.setCurrentRow(row + 1)
        else:
            super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            parent_rect = self.parent().geometry()
            self.move(
                parent_rect.center().x() - self.width() // 2,
                parent_rect.top() + 80
            )
        self.search_input.clear()
        self.search_input.setFocus()
        QTimer.singleShot(0, lambda: self.search_input.setFocus())

    def hideEvent(self, event):
        super().hideEvent(event)
        self.search_input.clear()


class CommandPaletteManager:
    """Manages command palette registration and shortcuts."""

    def __init__(self, window):
        self.window = window
        self.palette = CommandPalette(window)
        self.palette.action_triggered.connect(self._execute_action)

        from PySide6.QtGui import QKeySequence, QShortcut
        self.shortcut = QShortcut(QKeySequence("Ctrl+K"), window)
        self.shortcut.activated.connect(self._show_palette)

    def set_scheme(self, scheme: ColorScheme):
        self.palette.set_scheme(scheme)

    def _show_palette(self):
        self.palette.show()

    def _execute_action(self, action_id: str):
        def _noop():
            self.window.chat_view.add_assistant_message("Funcionalidade em desenvolvimento.")

        handlers = {
            "new_chat": self.window._new_conversation,
            "clear_chat": self.window.chat_view.clear,
            "toggle_sidebar": lambda: self.window.sidebar.setVisible(not self.window.sidebar.isVisible()),
            "toggle_theme": self.window._toggle_theme,
            "settings": self.window._show_settings,
            "change_model": lambda: self.window.input_area.model_combo.showPopup(),
            "voice_toggle": self.window._toggle_voice,
            "generate_report": self.window._generate_report,
            "export_chat": _noop,
            "import_chat": _noop,
            "web_search": _noop,
            "run_code": _noop,
            "index_document": _noop,
            "list_documents": _noop,
            "memory_view": self.window._show_memories_dialog,
            "add_memory": _noop,
        }

        if action_id in handlers:
            handlers[action_id]()
