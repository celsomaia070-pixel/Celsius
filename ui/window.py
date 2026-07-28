"""
Main Window - Janela principal refatorada usando controllers e views extraídos.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.inventory import get_inventory_service
from core.memory import get_memory_service
from core.settings import get_settings
from ui.chat import ModernChatView, ModernInputArea
from ui.command_palette import CommandPaletteManager
from ui.controllers.conversation_manager import ConversationManager
from ui.controllers.theme_controller import ThemeController
from ui.controllers.worker_controller import WorkerController
from ui.icons import icon
from ui.inventory_panel import InventoryPanel
from ui.jarvis_visualizer import JarvisVoiceVisualizer
from ui.kanban_view import KanbanContainer
from ui.sidebar import Sidebar
from ui.state.theme_manager import ThemeManager
from ui.theme import ThemeMode, scheme_from_name
from workers.ai_worker import WorkerManager


class ModernChatWindow(QMainWindow):
    """Main window with sidebar and chat area."""

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.memory_service = get_memory_service()
        self.inventory_service = get_inventory_service()
        self.worker_manager = WorkerManager()
        self.theme_manager = ThemeManager()

        # Controllers
        self.theme_controller = ThemeController(self)
        self.worker_controller = WorkerController(self)
        self.conversation_manager = ConversationManager(
            settings=self.settings, memory_service=self.memory_service, parent=self
        )

        self._theme_mode = ThemeMode.LIGHT
        self._current_conv_id = None
        self._mic_worker = None
        self._voz_worker = None
        self._pending_doc_text = ""
        self._pending_doc_name = ""
        self._pending_image_path = ""
        self._pending_file_path = ""
        self._memories_enabled = True
        self._voice_enabled = False
        self._jarvis = None
        if self.settings.ui.jarvis_enabled:
            self._jarvis = JarvisVoiceVisualizer(
                assistant_name=self.settings.assistant.name,
                particle_count=self.settings.ui.jarvis_particle_count,
                fps=self.settings.ui.jarvis_fps,
                use_internal_audio=False,
            )
            self._jarvis.VISUALIZATION_STOPPED.connect(self._on_jarvis_stopped)

        self.setWindowTitle("Celsius")
        self.resize(1100, 700)
        self._setup_ui()
        self._apply_theme()
        self._load_conversations()

        if self._jarvis:
            self._jarvis.position_at_topbar(self)
            self._jarvis.show()

        # Connect controllers
        self._connect_controllers()

        # Populate model combo with all available models
        self._populate_model_combo()

        # Command palette
        self.palette_manager = CommandPaletteManager(self)
        self.palette_manager.palette.action_triggered.connect(self._handle_palette_action)

        self._register_shortcuts()

        # New conversation
        self._new_conversation()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.new_chat_requested.connect(self._new_conversation)
        self.sidebar.conversation_selected.connect(self._switch_conversation)
        self.sidebar.conversation_delete_requested.connect(self._delete_conversation)
        self.sidebar.conversation_rename_requested.connect(self._rename_conversation)
        self.sidebar.toggle_memories.connect(self._on_toggle_memories)
        self.sidebar.open_memories.connect(self._show_memories_dialog)
        self.sidebar.tab_changed.connect(self._on_tab_changed)
        root_layout.addWidget(self.sidebar)

        # Right content
        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top bar
        self._top_bar = QWidget()
        self._top_bar.setFixedHeight(100)
        top_bar_layout = QHBoxLayout(self._top_bar)
        top_bar_layout.setContentsMargins(16, 0, 20, 0)
        top_bar_layout.setSpacing(12)

        # Hamburger toggle
        self.hamburger_btn = QPushButton()
        self.hamburger_btn.setIcon(self._icon("bars"))
        self.hamburger_btn.setToolTip("Mostrar/esconder sidebar")
        self.hamburger_btn.setFixedSize(36, 36)
        self.hamburger_btn.setCursor(Qt.PointingHandCursor)
        self.hamburger_btn.clicked.connect(self._toggle_sidebar)
        top_bar_layout.addWidget(self.hamburger_btn)

        top_bar_layout.addStretch(1)

        # Theme toggle button
        self.theme_btn = QPushButton()
        self.theme_btn.setToolTip("Alternar tema (Ctrl+Shift+L)")
        self.theme_btn.setFixedSize(36, 36)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        top_bar_layout.addWidget(self.theme_btn)

        # Settings button
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(self._icon("cog"))
        self.settings_btn.setToolTip("Configuracoes (Ctrl+,)")
        self.settings_btn.setFixedSize(36, 36)
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(self._show_settings)
        top_bar_layout.addWidget(self.settings_btn)

        main_layout.addWidget(self._top_bar)

        # Chat view
        self.chat_view = ModernChatView(scheme=scheme_from_name(self._theme_mode.value))
        main_layout.addWidget(self.chat_view, 1)

        # Input area
        self.input_area = ModernInputArea(scheme=scheme_from_name(self._theme_mode.value))
        self.input_area.send_message.connect(self._on_user_message)
        self.input_area.attach_file.connect(self._on_attach_file)
        self.input_area.toggle_mic.connect(self._toggle_mic)
        self.input_area.toggle_voice.connect(self._toggle_voice)
        self.input_area.change_model.connect(self._on_model_changed)
        main_layout.addWidget(self.input_area)

        # Inventory panel
        self.inventory_panel = InventoryPanel(scheme=scheme_from_name(self._theme_mode.value))
        self.inventory_panel.entrada_solicitada.connect(self._on_inventory_entrada)
        self.inventory_panel.saida_solicitada.connect(self._on_inventory_saida)
        self.inventory_panel.item_selecionado.connect(self._on_inventory_item_selected)
        self.inventory_panel.hide()
        main_layout.addWidget(self.inventory_panel)

        # Kanban container
        self.kanban_container = KanbanContainer(scheme=scheme_from_name(self._theme_mode.value))
        self.kanban_container.item_movido.connect(self._on_kanban_move)
        self.kanban_container.hide()
        main_layout.addWidget(self.kanban_container)

        root_layout.addWidget(content_widget, 1)

    def _icon(self, name: str, color=None):
        """Helper para criar ícones usando o theme atual."""
        scheme = scheme_from_name(self._theme_mode.value)
        return icon(name, color or scheme.text_secondary)

    def _connect_controllers(self):
        # Worker controller
        self.worker_controller.ai_response_started.connect(self._on_ai_response_started)
        self.worker_controller.ai_response_token.connect(self._on_ai_response_token)
        self.worker_controller.ai_response_finished.connect(self._on_ai_response_finished)
        self.worker_controller.ai_response_error.connect(self._on_ai_response_error)
        self.worker_controller.ai_status_update.connect(self._on_ai_status_update)
        self.worker_controller.model_loaded.connect(self._on_model_loaded)
        self.worker_controller.model_load_error.connect(self._on_model_load_error)
        self.worker_controller.model_list_loaded.connect(self._on_model_list_loaded)
        self.worker_controller.mic_ready.connect(self._on_mic_ready)
        self.worker_controller.mic_error.connect(self._on_mic_error)
        self.worker_controller.mic_level.connect(self._on_mic_level)
        self.worker_controller.voice_text_ready.connect(self._on_voice_text_ready)
        self.worker_controller.voice_error.connect(self._on_voice_error)
        self.worker_controller.voice_finished.connect(self._on_voice_finished)

        # Conversation manager
        self.conversation_manager.conversation_changed.connect(self._on_conversation_changed)
        self.conversation_manager.conversation_list_changed.connect(
            self._refresh_sidebar_conversations
        )
        self.conversation_manager.conversation_deleted.connect(self._on_conversation_deleted)
        self.conversation_manager.conversation_renamed.connect(self._on_conversation_renamed)

    def _apply_theme(self):
        self.theme_controller.apply_theme(self)

    def _toggle_theme(self):
        self.theme_controller.toggle()
        self._apply_theme()

    def _load_conversations(self):
        self.conversation_manager._load_conversations()
        self._refresh_sidebar_conversations()

    def _refresh_sidebar_conversations(self):
        self.sidebar.clear()
        for conv in self.conversation_manager.get_all_conversations():
            self.sidebar.add_conversation(conv["id"], conv["title"], conv.get("updated_at"))
        if self.conversation_manager.get_current():
            self.sidebar.set_current_conversation(self.conversation_manager.get_current())

    def _new_conversation(self):
        conv_id = self.conversation_manager.create_conversation()
        self.conversation_manager.set_current(conv_id)
        self._current_conv_id = conv_id
        self.chat_view.clear()

    def _switch_conversation(self, conv_id: str):
        self.conversation_manager.set_current(conv_id)
        self._current_conv_id = conv_id
        self.chat_view.clear()

        # Load messages
        for msg in self.conversation_manager.get_messages(conv_id):
            if msg["role"] == "user":
                self.chat_view.add_user_message(msg["content"], msg.get("attachments"))
            else:
                self.chat_view.add_assistant_message(msg["content"])

    def _on_conversation_changed(self, conv_id: str):
        self._current_conv_id = conv_id
        self.sidebar.set_current_conversation(conv_id)

    def _on_conversation_deleted(self, conv_id: str):
        if self._current_conv_id == conv_id:
            self._new_conversation()

    def _on_conversation_renamed(self, conv_id: str, new_title: str):
        self.sidebar.update_conversation_title(conv_id, new_title)

    def _delete_conversation(self, conv_id: str):
        reply = QMessageBox.question(
            self,
            "Excluir conversa",
            "Tem certeza que deseja excluir esta conversa?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.conversation_manager.delete_conversation(conv_id)

    def _rename_conversation(self, conv_id: str, new_title: str):
        self.conversation_manager.rename_conversation(conv_id, new_title)

    def _on_tab_changed(self, tab: str):
        if tab == "estoque":
            self.chat_view.hide()
            self.input_area.hide()
            self.inventory_panel.show()
            self.kanban_container.hide()
        elif tab == "kanban":
            self.chat_view.hide()
            self.input_area.hide()
            self.inventory_panel.hide()
            self.kanban_container.show()
        else:
            self.chat_view.show()
            self.input_area.show()
            self.inventory_panel.hide()
            self.kanban_container.hide()

    # AI Response handlers
    def _on_ai_response_started(self):
        self.chat_view.start_streaming()

    def _on_ai_response_token(self, token: str):
        self.chat_view.append_streaming(token)

    def _on_ai_response_finished(self, full_text: str):
        self.chat_view.finish_streaming(full_text)
        if self._current_conv_id:
            self.conversation_manager.add_message(self._current_conv_id, "assistant", full_text)
        if self._voice_enabled and full_text.strip():
            if self._jarvis:
                self._jarvis.start_speaking()
            self.worker_controller.start_voice(full_text)

    def _on_ai_response_error(self, error: str):
        self.chat_view.hide_thinking()
        self.chat_view.add_assistant_message(f"Erro: {error}")

    def _on_ai_status_update(self, status: str):
        if "Raciocinando" in status or "pensando" in status.lower():
            self.chat_view.show_thinking("Pensando")
        elif "busco" in status.lower():
            self.chat_view.show_thinking("Buscando informacoes")
        elif "Analisando" in status:
            self.chat_view.show_thinking("Analisando")
        elif "Processando" in status:
            self.chat_view.show_thinking("Processando")
        else:
            self.chat_view.hide_thinking()

    # Model handlers
    def _populate_model_combo(self):
        """Fill model combo with all GGUF_MODELS and select current."""
        from core.config import GGUF_MODELS, get_model_by_id

        model_names = [m.display_name for m in GGUF_MODELS]
        self.input_area.set_models(model_names)
        current = get_model_by_id(self.settings.llm_model)
        if current:
            idx = self.input_area.model_combo.findText(current.display_name)
            if idx >= 0:
                self.input_area.model_combo.setCurrentIndex(idx)

    def _on_model_list_loaded(self, models: list):
        self.input_area.set_models(models)

    def _on_model_changed(self, display_name: str):
        """Switch to the selected model by display name."""
        from core.config import GGUF_MODELS

        match = next((m for m in GGUF_MODELS if m.display_name == display_name), None)
        if not match:
            return
        old_model = self.settings.llm_model
        if match.id == old_model:
            return
        self.settings.llm_model = match.id
        # Restart llama.cpp with the new model
        from core.llama_cpp import start_llama_server, stop_llama_server

        try:
            stop_llama_server()
            if not start_llama_server(
                model_id=match.id,
                n_gpu_layers=-1,
                n_ctx=16384,
                n_batch=1024,
                n_threads=0,
            ):
                self.settings.llm_model = old_model
                QMessageBox.warning(self, "Erro", f"Falha ao carregar modelo {match.name}")
        except Exception as e:
            self.settings.llm_model = old_model
            QMessageBox.warning(self, "Erro", f"Falha ao trocar modelo: {e}")

    def _on_model_loaded(self, model_name: str):
        self.input_area.set_models(self.input_area.model_combo.currentText(), model_name)

    def _on_model_load_error(self, error: str):
        QMessageBox.warning(self, "Erro ao carregar modelo", error)

    # Mic handlers
    def _toggle_mic(self):
        if self._mic_worker:
            self.worker_controller.stop_mic()
            self._mic_worker = None
            if self._jarvis:
                self._jarvis.stop_listening()
            self.input_area.set_mic_active(False)
        else:
            self.worker_controller.start_mic()
            if self._jarvis:
                self._jarvis.start_listening()
            self.input_area.set_mic_active(True)

    def _on_mic_ready(self):
        self._mic_worker = self.worker_controller._mic_worker

    def _on_mic_error(self, error: str):
        self._mic_worker = None
        if self._jarvis:
            self._jarvis.stop_listening()
        self.input_area.set_mic_active(False)
        QMessageBox.warning(self, "Erro no microfone", error)

    def _on_mic_level(self, level: float):
        if self._jarvis:
            self._jarvis.set_mic_level(level)

    # Voice handlers
    def _toggle_voice(self):
        self._voice_enabled = self.input_area.btn_voice.isChecked()
        if not self._voice_enabled:
            if self._jarvis:
                self._jarvis.stop_speaking()
            self.worker_controller.stop_voice()

    def _on_voice_text_ready(self, text: str):
        if self._jarvis:
            self._jarvis.stop_listening()
        self._mic_worker = None
        self.input_area.set_mic_active(False)
        self.input_area.input.setText(text)
        self._on_user_message(text)

    def _on_voice_error(self, error: str):
        if self._jarvis:
            self._jarvis.stop_speaking()
        QMessageBox.warning(self, "Erro na voz", error)

    def _on_voice_finished(self):
        if self._jarvis:
            self._jarvis.stop_speaking()

    def _on_jarvis_stopped(self):
        pass

    # User message handler
    def _on_user_message(self, text: str):
        if not self._current_conv_id:
            self._new_conversation()

        attachments = self.input_area.get_attachments()
        self.conversation_manager.add_message(self._current_conv_id, "user", text, attachments)
        self.chat_view.add_user_message(text, attachments)
        self.input_area.clear_attachments()

        # Defer heavy operations (history/memory retrieval) to next event loop iteration
        # so the user message can render first
        QTimer.singleShot(0, lambda: self._start_ai_response(text, attachments))

    def _start_ai_response(self, text: str, attachments: list | None = None):
        history = self.conversation_manager.get_history_for_ai(self._current_conv_id)
        memories = self.conversation_manager.get_memories_for_ai() if self._memories_enabled else []

        system_prompt = self._build_system_prompt()

        self.worker_controller.send_message(
            message=text,
            system_prompt=system_prompt,
            conversation_history=history,
            memories=memories,
            model_name=self.settings.llm_model,
            attachments=attachments or [],
        )

    def _build_system_prompt(self) -> str:
        from datetime import date

        today = date.today().strftime("%d/%m/%Y")
        assistant = self.settings.assistant
        owner_clause = f" Voce ajuda {assistant.owner_name}." if assistant.owner_name else ""
        return f"Voce e {assistant.name}, {assistant.profile}.{owner_clause} Hoje e {today}."

    # File attachment
    def _on_attach_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo")
        if file_path:
            self._process_attachment(file_path)

    def _process_attachment(self, file_path: str):
        from pathlib import Path

        ext = Path(file_path).suffix.lower()

        if ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"] or ext in [
            ".pdf",
            ".txt",
            ".md",
            ".csv",
            ".xlsx",
            ".docx",
        ]:
            self.input_area.add_attachment(file_path)
        else:
            QMessageBox.warning(self, "Tipo nao suportado", f"Extensao {ext} nao suportada.")

    # Inventory handlers
    def _on_inventory_entrada(self, item_id: str):
        item = self.inventory_service.get_item(item_id)
        if not item:
            return
        qtd, ok = self._get_quantity(f"Entrada - {item.nome}", "Quantidade a entrar:")
        if ok and qtd > 0:
            self.inventory_service.entrada(item_id, qtd)
            self.inventory_panel.refresh()
            self.kanban_container.refresh()

    def _on_inventory_saida(self, item_id: str):
        item = self.inventory_service.get_item(item_id)
        if not item:
            return
        qtd, ok = self._get_quantity(f"Saida - {item.nome}", "Quantidade a sair:")
        if ok and 0 < qtd <= item.quantidade:
            self.inventory_service.saida(item_id, qtd)
            self.inventory_panel.refresh()
            self.kanban_container.refresh()
        elif ok and qtd > item.quantidade:
            QMessageBox.warning(self, "Erro", "Quantidade maior que o estoque disponivel.")

    def _on_inventory_item_selected(self, item_id: str):
        self.sidebar.set_active_tab("estoque")

    def _get_quantity(self, title: str, label: str):
        from PySide6.QtWidgets import QInputDialog

        qtd, ok = QInputDialog.getInt(self, title, label, 1, 0, 9999)
        return qtd, ok

    # Kanban handlers
    def _on_kanban_move(self, item_id: str, new_column: str):
        from core.inventory import ColunaKanban

        self.inventory_service.mover_item(item_id, ColunaKanban(new_column))
        self.inventory_panel.refresh()

    # Memory handlers
    def _on_toggle_memories(self, enabled: bool):
        self._memories_enabled = enabled

    def _show_memories_dialog(self):
        from ui.dialogs import CaixaMemoriaDialog

        dialog = CaixaMemoriaDialog(
            memory_service=self.memory_service,
            scheme=scheme_from_name(self._theme_mode.value),
            parent=self,
        )
        dialog.exec()

    # Settings
    def _show_settings(self):
        from ui.dialogs import ConfiguracoesDialog

        dialog = ConfiguracoesDialog(
            self.settings, scheme=scheme_from_name(self._theme_mode.value), parent=self
        )
        if dialog.exec():
            self._apply_theme()

    # Command palette
    def _handle_palette_action(self, action_id: str, data: dict):
        if action_id == "new_chat":
            self._new_conversation()
        elif action_id == "toggle_theme":
            self._toggle_theme()
        elif action_id == "open_settings":
            self._show_settings()
        elif action_id == "clear_chat":
            self.chat_view.clear()
            if self._current_conv_id:
                self.conversation_manager.clear_current_conversation()

    def _toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def _register_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new_conversation)
        QShortcut(QKeySequence("Ctrl+Shift+Delete"), self, activated=self.chat_view.clear)
        QShortcut(QKeySequence("Ctrl+Shift+L"), self, activated=self._toggle_theme)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._show_settings)

    def closeEvent(self, event):
        if self._jarvis:
            self._jarvis.close()
            self._jarvis = None
        self.worker_controller.cleanup()
        super().closeEvent(event)


# Re-export for backwards compatibility with tests
from ui.chat import MessageBubble

__all__ = ["MessageBubble", "ModernChatView", "ModernInputArea", "ModernChatWindow"]
