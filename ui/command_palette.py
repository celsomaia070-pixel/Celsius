import qtawesome as qta
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

        self._actions = []
        self._filtered_actions = []
        self._setup_ui()
        self._register_default_actions()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Container with rounded corners
        container = QWidget()
        container.setObjectName("container")
        container.setStyleSheet("""
            #container {
                background: #161B22;
                border: 1px solid #30363D;
                border-radius: 12px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Digite um comando ou pesquise...  (Esc para fechar)")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #0D1117;
                border: none;
                border-bottom: 1px solid #30363D;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                color: #E6EDF3;
                padding: 16px 20px;
                font-size: 15px;
            }
            QLineEdit:focus {
                outline: none;
            }
        """)
        self.search_input.textChanged.connect(self._filter_actions)
        container_layout.addWidget(self.search_input)

        # Results list
        self.results_list = QListWidget()
        self.results_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                padding: 12px 20px;
                color: #E6EDF3;
                font-size: 13px;
            }
            QListWidget::item:selected {
                background: #1F6FEB30;
                color: #58A6FF;
            }
            QListWidget::item:hover {
                background: #1F6FEB20;
            }
        """)
        self.results_list.itemActivated.connect(self._on_item_activated)
        container_layout.addWidget(self.results_list)

        layout.addWidget(container)

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

            # Create custom widget for item
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)

            icon_label = QLabel()
            icon_label.setPixmap(
                qta.icon(action["icon"], color="#8B949E").pixmap(20, 20)
            )
            layout.addWidget(icon_label)

            name_label = QLabel(action["name"])
            name_label.setStyleSheet("color: #E6EDF3; font-size: 13px;")
            layout.addWidget(name_label)

            layout.addStretch()

            if action.get("shortcut"):
                shortcut_label = QLabel(action["shortcut"])
                shortcut_label.setStyleSheet("""
                    color: #484F58;
                    font-size: 11px;
                    font-family: monospace;
                    background: #161B22;
                    padding: 2px 8px;
                    border-radius: 4px;
                """)
                layout.addWidget(shortcut_label)

            item.setSizeHint(widget.sizeHint())
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, widget)

        if self._filtered_actions:
            self.results_list.setCurrentRow(0)

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
        # Center on parent
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

        # Register shortcut
        from PySide6.QtGui import QKeySequence, QShortcut
        self.shortcut = QShortcut(QKeySequence("Ctrl+K"), window)
        self.shortcut.activated.connect(self._show_palette)

    def _show_palette(self):
        self.palette.show()

    def _execute_action(self, action_id: str):
        handlers = {
            "new_chat": lambda: self.window.limpar_historico(),
            "clear_chat": lambda: self.window.limpar_historico(),
            "toggle_sidebar": lambda: self.window.sidebar.setVisible(not self.window.sidebar.isVisible()),
            "toggle_theme": lambda: self.window._toggle_theme(),
            "settings": lambda: self.window._show_settings(),
            "export_chat": lambda: self.window._export_chat(),
            "change_model": lambda: self.window.combo_modelo.showPopup(),
            "voice_toggle": lambda: self.window.alternar_voz(),
            "generate_report": lambda: self.window.gerar_relatorio(),
        }

        if action_id in handlers:
            handlers[action_id]()
