"""
Main Window - Janela principal refatorada usando controllers e views extraídos.
"""

import contextlib
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.inventory import get_inventory_service
from core.memory import get_memory_service
from core.mobile_access import (
    MobileAccessServer,
    ensure_mobile_certificate,
    ensure_mobile_token,
)
from core.modules import get_module_definition, sidebar_modules
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

    mobile_command_received = Signal(str)

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

        self._theme_mode = self._resolve_theme_mode()
        self.theme_controller.set_mode(self._theme_mode)
        self._current_conv_id = None
        self._mic_worker = None
        self._voz_worker = None
        self._pending_doc_text = ""
        self._pending_doc_name = ""
        self._pending_image_path = ""
        self._pending_file_path = ""
        self._memories_enabled = True
        self._voice_enabled = False
        self._ai_busy = False
        self._next_response_should_speak_on_pc = False
        self._mobile_server = None
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
        self.mobile_command_received.connect(self._on_mobile_command_received)

        # Populate model combo with all available models
        self._populate_model_combo()

        # Command palette
        self.palette_manager = CommandPaletteManager(self)
        self.palette_manager.palette.action_triggered.connect(self._handle_palette_action)
        self._apply_module_configuration()

        self._register_shortcuts()

        # New conversation
        self._new_conversation()
        QTimer.singleShot(500, self._maybe_show_first_setup)
        self._start_mobile_access_if_enabled()

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
        self.sidebar.suppliers_requested.connect(self._show_suppliers_dialog)
        self.sidebar.settings_requested.connect(self._show_settings)
        self.sidebar.mobile_pair_requested.connect(self._show_mobile_pairing_shortcut)
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

        self.module_placeholder = QLabel("")
        self.module_placeholder.setWordWrap(True)
        self.module_placeholder.setAlignment(Qt.AlignCenter)
        self.module_placeholder.hide()
        main_layout.addWidget(self.module_placeholder, 1)

        root_layout.addWidget(content_widget, 1)

    def _resolve_theme_mode(self) -> ThemeMode:
        if self.settings.ui.theme == "dark":
            return ThemeMode.DARK
        return ThemeMode.LIGHT

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
        self.worker_controller.voice_audio_ready.connect(self._on_voice_audio_ready)
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
        if hasattr(self, "module_placeholder"):
            scheme = scheme_from_name(self._theme_mode.value)
            self.module_placeholder.setStyleSheet(
                f"background: {scheme.bg_primary}; color: {scheme.text_secondary}; "
                "font-size: 15px; padding: 28px;"
            )

    def _toggle_theme(self):
        self._theme_mode = self.theme_controller.toggle()
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
        if tab == "chat":
            self.chat_view.show()
            self.input_area.show()
            self.inventory_panel.hide()
            self.kanban_container.hide()
            self.module_placeholder.hide()
        elif tab == "inventory":
            self.chat_view.hide()
            self.input_area.hide()
            self.inventory_panel.show()
            self.kanban_container.hide()
            self.module_placeholder.hide()
        elif tab == "kanban":
            self.chat_view.hide()
            self.input_area.hide()
            self.inventory_panel.hide()
            self.kanban_container.show()
            self.module_placeholder.hide()
        elif tab in {"suppliers", "settings"}:
            self.chat_view.show()
            self.input_area.show()
            self.inventory_panel.hide()
            self.kanban_container.hide()
            self.module_placeholder.hide()
        else:
            module = get_module_definition(tab)
            if module and module.is_ready:
                self.chat_view.show()
                self.input_area.show()
                self.inventory_panel.hide()
                self.kanban_container.hide()
                self.module_placeholder.hide()
                self._show_module_records_dialog(tab)
            else:
                self._show_module_placeholder(tab)

    def _show_module_placeholder(self, module_id: str):
        module = get_module_definition(module_id)
        if module is None:
            title = "Modulo indisponivel"
            description = "Este modulo nao esta configurado para esta empresa."
        else:
            title = module.name
            description = module.description
        self.chat_view.hide()
        self.input_area.hide()
        self.inventory_panel.hide()
        self.kanban_container.hide()
        self.module_placeholder.setText(
            f"{title}\n\n{description}\n\nModulo em preparacao para esta empresa."
        )
        self.module_placeholder.show()

    def _apply_module_configuration(self):
        modules = sidebar_modules(self.settings.modules.enabled)
        self.sidebar.configure_modules(modules)
        if hasattr(self, "palette_manager"):
            self.palette_manager.configure_modules(modules)

    def _maybe_show_first_setup(self):
        if self.settings.modules.first_setup_completed or self.settings.customer.is_configured():
            return
        from ui.dialogs import AssistentePrimeiraConfiguracaoDialog

        dialog = AssistentePrimeiraConfiguracaoDialog(
            self.settings, scheme=scheme_from_name(self._theme_mode.value), parent=self
        )
        if dialog.exec():
            self._apply_module_configuration()
            self._apply_theme()

    def _start_mobile_access_if_enabled(self):
        if not self.settings.mobile.enabled:
            return
        self._restart_mobile_access(show_message=False)

    def _restart_mobile_access(self, show_message: bool = True, show_pairing: bool = True):
        self._stop_mobile_access()
        if not self.settings.mobile.enabled:
            return

        token = ensure_mobile_token(self.settings.mobile.pairing_token)
        self.settings.mobile.pairing_token = token
        self.settings.save_local_preferences()

        host = self.settings.mobile.host if self.settings.mobile.allow_lan else "127.0.0.1"
        cert_file = key_file = None
        use_https = self.settings.mobile.use_https
        https_warning = ""
        if use_https:
            try:
                cert_file, key_file = ensure_mobile_certificate(
                    self.settings.data_dir / "mobile_access"
                )
            except RuntimeError as exc:
                use_https = False
                https_warning = (
                    f"\n\nAviso: HTTPS local indisponivel ({exc}). "
                    "O acesso pelo celular foi iniciado em HTTP; alguns navegadores podem bloquear o microfone."
                )

        server = MobileAccessServer(
            host=host,
            port=self.settings.mobile.port,
            token=token,
            command_callback=self._queue_mobile_command,
            voice_enabled=self.settings.mobile.voice_commands_enabled,
            voice_command_callback=self._queue_mobile_voice_command,
            use_https=use_https,
            cert_file=cert_file,
            key_file=key_file,
        )
        try:
            self._mobile_server = server.start()
        except Exception as exc:
            if not use_https:
                raise
            https_warning = (
                f"\n\nAviso: nao foi possivel iniciar HTTPS local ({exc}). "
                "O acesso pelo celular foi iniciado em HTTP; alguns navegadores podem bloquear o microfone."
            )
            self._mobile_server = MobileAccessServer(
                host=host,
                port=self.settings.mobile.port,
                token=token,
                command_callback=self._queue_mobile_command,
                voice_enabled=self.settings.mobile.voice_commands_enabled,
                voice_command_callback=self._queue_mobile_voice_command,
                use_https=False,
            ).start()
        if show_message:
            self.chat_view.add_assistant_message(
                "Acesso pelo celular ativo nesta rede:\n\n"
                f"{self._mobile_server.url}\n\n"
                "Use esse endereço no navegador do celular. Mantenha o token privado."
                f"{https_warning}"
            )
        if show_pairing:
            self._show_mobile_pairing_dialog()

    def _show_mobile_pairing_dialog(self):
        if not self._mobile_server:
            return
        from ui.dialogs import PareamentoCelularDialog

        dialog = PareamentoCelularDialog(
            self._mobile_server.url,
            https_enabled=self._mobile_server.use_https,
            scheme=scheme_from_name(self._theme_mode.value),
            parent=self,
        )
        dialog.exec()

    def _show_mobile_pairing_shortcut(self):
        if self._mobile_server:
            self._show_mobile_pairing_dialog()
            return

        if not self.settings.mobile.enabled:
            self.settings.mobile.enabled = True
            self.settings.mobile.allow_lan = True
            self.settings.mobile.voice_commands_enabled = True
            self.settings.mobile.use_https = True

        self.settings.mobile.pairing_token = ensure_mobile_token(self.settings.mobile.pairing_token)
        self.settings.save_local_preferences()

        try:
            self._restart_mobile_access(show_message=False, show_pairing=True)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Celular",
                f"Nao foi possivel iniciar o acesso pelo celular:\n{exc}",
            )

    def _stop_mobile_access(self):
        if self._mobile_server:
            self._mobile_server.stop()
            self._mobile_server = None

    def _queue_mobile_command(self, message: str, source: str):
        if self._ai_busy:
            return (
                False,
                "O Celsius ainda esta respondendo. Tente novamente em instantes.",
            )
        prefix = "Comando por voz do celular" if source == "phone_voice" else "Comando do celular"
        self.mobile_command_received.emit(f"{prefix}: {message}")
        return True, "Comando enviado ao Celsius no PC."

    def _queue_mobile_voice_command(self, audio: bytes, mime_type: str):
        if self._ai_busy:
            return (
                False,
                "",
                "O Celsius ainda esta respondendo. Tente novamente em instantes.",
            )

        suffix = self._audio_suffix_from_mime(mime_type)
        temp_path = ""
        try:
            if suffix == ".wav":
                from core.mobile_voice import transcribe_mobile_wav

                transcript = transcribe_mobile_wav(
                    audio, model_name=self.settings.model.whisper_model
                )
                self.mobile_command_received.emit(f"Comando por voz do celular: {transcript}")
                return True, transcript, "Voz transcrita no PC e enviada ao Celsius."

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
                temp.write(audio)
                temp_path = temp.name

            from processors.audio import ProcessadorAudio

            result = ProcessadorAudio.processar(temp_path, base_dir=Path(temp_path).parent)
            if result.lower().startswith("erro"):
                if "converter audio" in result.lower():
                    return (
                        False,
                        "",
                        "Erro ao converter audio. Reabra o QR Code atualizado para gravar em WAV "
                        "ou instale o FFmpeg no Windows.",
                    )
                return False, "", result

            marker = "Transcricao:\n"
            transcript = result.split(marker, 1)[1].strip() if marker in result else result.strip()
            if not transcript:
                return False, "", "Nao consegui entender a gravacao."

            self.mobile_command_received.emit(f"Comando por voz do celular: {transcript}")
            return True, transcript, "Voz transcrita no PC e enviada ao Celsius."
        except Exception as exc:
            return False, "", f"Erro ao transcrever voz do celular: {exc}"
        finally:
            if temp_path:
                with contextlib.suppress(OSError):
                    Path(temp_path).unlink()

    def _audio_suffix_from_mime(self, mime_type: str) -> str:
        mime = (mime_type or "").lower()
        if "wav" in mime:
            return ".wav"
        if "ogg" in mime:
            return ".ogg"
        if "mp4" in mime or "m4a" in mime:
            return ".m4a"
        if "mpeg" in mime or "mp3" in mime:
            return ".mp3"
        return ".webm"

    def _on_mobile_command_received(self, message: str):
        self._next_response_should_speak_on_pc = True
        self._on_user_message(message)

    # AI Response handlers
    def _on_ai_response_started(self):
        self._ai_busy = True
        self.input_area.set_busy(True)
        self.chat_view.start_streaming()

    def _on_ai_response_token(self, token: str):
        self.chat_view.append_streaming(token)

    def _on_ai_response_finished(self, full_text: str):
        self._ai_busy = False
        self.input_area.set_busy(False)
        self.chat_view.finish_streaming(full_text)
        if self._current_conv_id:
            self.conversation_manager.add_message(self._current_conv_id, "assistant", full_text)
        if self._mobile_server:
            self._mobile_server.publish_response(full_text, kind="assistant")
        should_speak_on_pc = self._voice_enabled or self._next_response_should_speak_on_pc
        self._next_response_should_speak_on_pc = False
        if should_speak_on_pc and full_text.strip():
            if self._jarvis:
                self._jarvis.start_speaking()
            self.worker_controller.start_voice(
                full_text,
                force_enabled=should_speak_on_pc,
            )

    def _on_ai_response_error(self, error: str):
        self._ai_busy = False
        self.input_area.set_busy(False)
        self.chat_view.hide_thinking()
        error_text = f"Erro: {error}"
        if getattr(self.chat_view, "_streaming_bubble", None):
            self.chat_view.finish_streaming(error_text)
        else:
            self.chat_view.add_assistant_message(error_text)
        if self._mobile_server:
            self._mobile_server.publish_response(error_text, kind="error")
        self._next_response_should_speak_on_pc = False

    def _on_ai_status_update(self, status: str):
        label = self._friendly_ai_status(status)
        if label:
            self.chat_view.show_thinking(label)

    def _friendly_ai_status(self, status: str) -> str:
        raw = (status or "").strip()
        lowered = raw.lower()

        if any(term in lowered for term in ("extraindo", "arquivo", "anexo")):
            return "Extraindo conteudo do arquivo"
        if "imagem" in lowered or "visual" in lowered:
            return "Analisando imagem"
        if "document" in lowered:
            return "Analisando documentos"
        if "contexto da conversa" in lowered or "historico" in lowered:
            return "Carregando contexto da conversa"
        if "estoque" in lowered:
            return "Consultando dados do estoque"
        if "memoria" in lowered:
            return "Consultando memorias relevantes"
        if "ferramenta" in lowered or "executando" in lowered:
            return "Consultando ferramentas"
        if "modelo" in lowered:
            return "Selecionando melhor modelo local"
        if "estruturando" in lowered:
            return "Estruturando a resposta"
        if "escrevendo" in lowered:
            return "Escrevendo resposta"
        if "elaborando" in lowered:
            return "Elaborando a melhor resposta"
        if "organizando" in lowered:
            return "Organizando os detalhes"
        if "validando" in lowered:
            return "Validando informacoes"
        if "refinando" in lowered:
            return "Refinando a resposta final"
        if "processando" in lowered:
            return "Processando"
        if "analisando" in lowered:
            return "Analisando"
        if "pensando" in lowered or "raciocinando" in lowered:
            return "Pensando"
        return raw or "Pensando"

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
            self.worker_controller.stop_voice()
            if self._jarvis:
                self._jarvis.stop_speaking()
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

    def _on_voice_audio_ready(self, audio: bytes, mime_type: str):
        if self._mobile_server:
            self._mobile_server.publish_audio(audio, mime_type=mime_type)

    def _on_voice_finished(self):
        if self._jarvis:
            self._jarvis.stop_speaking()

    def _on_jarvis_stopped(self):
        pass

    # User message handler
    def _on_user_message(self, text: str):
        self.worker_controller.stop_voice()
        if self._jarvis:
            self._jarvis.stop_speaking()

        if self._ai_busy:
            self.chat_view.add_assistant_message(
                "Ainda estou terminando a resposta anterior. Envie a proxima mensagem quando eu concluir."
            )
            return

        self._ai_busy = True
        self.input_area.set_busy(True)

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

        sent = self.worker_controller.send_message(
            message=text,
            system_prompt=system_prompt,
            conversation_history=history,
            memories=memories,
            model_name=self.settings.llm_model,
            attachments=attachments or [],
        )
        if sent is False:
            self._ai_busy = False
            self.input_area.set_busy(False)

    def _build_system_prompt(self) -> str:
        from datetime import date

        today = date.today().strftime("%d/%m/%Y")
        assistant = self.settings.assistant
        return (
            f"Voce e {assistant.name}, {assistant.profile}. "
            f"Sua identidade fixa e Celsius. Hoje e {today}. "
            "Ajude em tarefas gerais do usuario quando solicitado, incluindo redacao, estudos, "
            "tecnologia e explicacoes. O perfil da empresa orienta contexto, mas nao limita "
            "os assuntos que voce pode responder."
        )

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
        self.sidebar.set_active_tab("inventory")

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

    def _show_suppliers_dialog(self):
        from ui.dialogs import FornecedoresDialog

        dialog = FornecedoresDialog(scheme=scheme_from_name(self._theme_mode.value), parent=self)
        dialog.exec()

    def _show_module_records_dialog(self, module_id: str):
        from ui.dialogs import ModuloRegistrosDialog

        dialog = ModuloRegistrosDialog(
            module_id, scheme=scheme_from_name(self._theme_mode.value), parent=self
        )
        dialog.exec()

    # Settings
    def _show_settings(self):
        from ui.dialogs import ConfiguracoesDialog

        dialog = ConfiguracoesDialog(
            self.settings, scheme=scheme_from_name(self._theme_mode.value), parent=self
        )
        if dialog.exec():
            self._apply_module_configuration()
            if dialog.mobile_action in {"pair", "regenerate"}:
                self._restart_mobile_access(show_message=True, show_pairing=True)
            elif dialog.mobile_action == "restart":
                self._restart_mobile_access(show_message=True, show_pairing=False)
            else:
                self._restart_mobile_access(show_message=False, show_pairing=False)
            self._apply_theme()

    # Command palette
    def _handle_palette_action(self, action_id: str, data: dict):
        if action_id == "new_chat":
            self._new_conversation()
        elif action_id == "toggle_theme":
            self._toggle_theme()
        elif action_id == "open_settings":
            self._show_settings()
        elif action_id.startswith("open_module:"):
            self.sidebar.set_active_tab(action_id.split(":", 1)[1])
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
        self._stop_mobile_access()
        self.worker_controller.cleanup()
        super().closeEvent(event)


# Re-export for backwards compatibility with tests
from ui.chat import MessageBubble

__all__ = ["MessageBubble", "ModernChatView", "ModernInputArea", "ModernChatWindow"]
