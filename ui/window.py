"""
Main Window - Janela principal refatorada usando controllers e views extraídos.
"""

import contextlib
import tempfile
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.agenda import get_agenda_service
from core.inventory import get_inventory_service
from core.memory import get_memory_service
from core.mobile_access import (
    MobileAccessServer,
    ensure_mobile_certificate,
    ensure_mobile_token,
)
from core.modules import get_module_definition, sidebar_modules
from core.settings import get_settings
from core.tts import (
    TTS_STREAM_FOLLOWUP_MAX_CHARS,
    TTS_STREAM_FOLLOWUP_MIN_CHARS,
    TTS_STREAM_FOLLOWUP_SENTENCE_CHARS,
    naturalize_tts_text,
    pop_ready_tts_chunk,
)
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
        self.agenda_service = get_agenda_service()
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
        self._voice_stream_enabled_for_response = False
        self._voice_stream_force_enabled = False
        self._voice_stream_buffer = ""
        self._voice_stream_active = False
        self._voice_stream_had_content = False
        self._voice_stream_enqueued_text = ""
        self._voice_stream_chunks_enqueued = 0
        self._voice_stream_finish_requested = False
        self._pending_mobile_voice_audio = []
        self._ai_busy = False
        self._next_response_should_speak_on_pc = False
        self._mobile_server = None
        self._agenda_timer = None
        self._agenda_alert_flash_timer = None
        self._agenda_beep_timer = None
        self._agenda_alert_flash_on = False
        self._pending_agenda_reminders = {}
        self._jarvis = None
        if self.settings.ui.jarvis_enabled:
            self._jarvis = JarvisVoiceVisualizer(
                assistant_name=self.settings.assistant.name,
                particle_count=self.settings.ui.jarvis_particle_count,
                fps=self.settings.ui.jarvis_fps,
                use_internal_audio=False,
            )
            self._jarvis.VISUALIZATION_STOPPED.connect(self._on_jarvis_stopped)

        self.setWindowTitle("Celsius Project AI")
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
        self._start_agenda_reminders()

    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("appRoot")
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
        content_widget.setObjectName("contentShell")
        self._content_widget = content_widget
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top bar
        self._top_bar = QWidget()
        self._top_bar.setObjectName("topBar")
        self._top_bar.setFixedHeight(72)
        top_bar_layout = QHBoxLayout(self._top_bar)
        top_bar_layout.setContentsMargins(20, 0, 20, 0)
        top_bar_layout.setSpacing(12)

        # Hamburger toggle
        self.hamburger_btn = QPushButton()
        self.hamburger_btn.setIcon(self._icon("bars"))
        self.hamburger_btn.setToolTip("Mostrar/esconder sidebar")
        self.hamburger_btn.setFixedSize(36, 36)
        self.hamburger_btn.setCursor(Qt.PointingHandCursor)
        self.hamburger_btn.clicked.connect(self._toggle_sidebar)
        top_bar_layout.addWidget(self.hamburger_btn)

        title_block = QWidget()
        title_block.setObjectName("workspaceTitleBlock")
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)
        self.workspace_title = QLabel("Celsius Project AI")
        self.workspace_title.setObjectName("workspaceTitle")
        self.workspace_subtitle = QLabel("IA local • dados no seu computador")
        self.workspace_subtitle.setObjectName("workspaceSubtitle")
        title_layout.addWidget(self.workspace_title)
        title_layout.addWidget(self.workspace_subtitle)
        top_bar_layout.addWidget(title_block)

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

        # Agenda alert stays visible until the user acknowledges the reminder.
        self.agenda_alert = QWidget()
        self.agenda_alert.setObjectName("agendaAlert")
        self.agenda_alert.hide()
        agenda_alert_layout = QHBoxLayout(self.agenda_alert)
        agenda_alert_layout.setContentsMargins(16, 10, 16, 10)
        agenda_alert_layout.setSpacing(12)

        self.agenda_alert_label = QLabel("")
        self.agenda_alert_label.setWordWrap(True)
        agenda_alert_layout.addWidget(self.agenda_alert_label, 1)

        self.agenda_alert_button = QPushButton("Desativar lembrete")
        self.agenda_alert_button.setCursor(Qt.PointingHandCursor)
        self.agenda_alert_button.clicked.connect(self._dismiss_agenda_alert)
        agenda_alert_layout.addWidget(self.agenda_alert_button)
        main_layout.addWidget(self.agenda_alert)

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
        scheme = scheme_from_name(self._theme_mode.value)
        if hasattr(self, "_top_bar"):
            self._top_bar.setStyleSheet(f"""
                #topBar {{
                    background: {scheme.bg_secondary};
                    border-bottom: 1px solid {scheme.border_default};
                }}
                #workspaceTitleBlock {{
                    background: transparent;
                    border: none;
                }}
                #workspaceTitle {{
                    background: transparent;
                    border: none;
                    color: {scheme.text_primary};
                    font-size: 16px;
                    font-weight: 700;
                }}
                #workspaceSubtitle {{
                    background: transparent;
                    border: none;
                    color: {scheme.accent_primary};
                    font-size: 11px;
                    font-weight: 600;
                }}
            """)
            icon_button_style = f"""
                QPushButton {{
                    background: {scheme.bg_secondary};
                    border: 1px solid {scheme.border_default};
                    border-radius: 6px;
                    padding: 8px;
                }}
                QPushButton:hover {{
                    background: {scheme.accent_subtle};
                    border-color: {scheme.accent_primary};
                }}
                QPushButton:pressed {{
                    background: {scheme.bg_active};
                }}
            """
            self.hamburger_btn.setIcon(icon("bars", scheme.text_primary))
            self.settings_btn.setIcon(icon("cog", scheme.text_primary))
            self.hamburger_btn.setStyleSheet(icon_button_style)
            self.theme_btn.setStyleSheet(icon_button_style)
            self.settings_btn.setStyleSheet(icon_button_style)
        if hasattr(self, "module_placeholder"):
            self.module_placeholder.setStyleSheet(
                f"background: {scheme.bg_primary}; color: {scheme.text_secondary}; "
                "font-size: 15px; padding: 28px;"
            )
        if hasattr(self, "agenda_alert"):
            self._apply_agenda_alert_style()

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

    def _start_agenda_reminders(self):
        self._agenda_timer = QTimer(self)
        self._agenda_timer.setInterval(60_000)
        self._agenda_timer.timeout.connect(self._check_agenda_reminders)
        self._agenda_timer.start()
        QTimer.singleShot(2_000, self._check_agenda_reminders)

    def _check_agenda_reminders(self):
        if not hasattr(self, "agenda_service"):
            return
        if not self.settings.modules.is_enabled("agenda"):
            return
        reminders = self.agenda_service.due_reminders(now=datetime.now())
        if not reminders:
            return

        new_reminders = []
        for event in reminders:
            if event.id in self._pending_agenda_reminders:
                continue
            self._pending_agenda_reminders[event.id] = event
            new_reminders.append(event)

        if not new_reminders:
            return

        message = self._format_agenda_reminder_message(new_reminders)
        self.chat_view.add_assistant_message(message)
        self._show_agenda_alert()
        self._beep_agenda_alert()
        if self._mobile_server:
            self._mobile_server.publish_response(message, kind="agenda_reminder")

    def _format_agenda_reminder_message(self, events):
        lines = ["Lembrete da agenda:"]
        for event in events:
            details = [event.starts_at.strftime("%d/%m/%Y %H:%M")]
            if event.customer:
                details.append(event.customer)
            if event.location:
                details.append(event.location)
            lines.append(f"- {event.title} ({' | '.join(details)})")
        return "\n".join(lines)

    def _show_agenda_alert(self):
        if not self._pending_agenda_reminders:
            self._hide_agenda_alert()
            return

        events = list(self._pending_agenda_reminders.values())
        self.agenda_alert_label.setText(self._format_agenda_reminder_message(events))
        self.agenda_alert.show()
        self._start_agenda_alert_timers()

    def _dismiss_agenda_alert(self):
        for event_id in list(self._pending_agenda_reminders):
            with contextlib.suppress(Exception):
                self.agenda_service.mark_reminded(event_id)
        self._pending_agenda_reminders.clear()
        self._hide_agenda_alert()

    def _hide_agenda_alert(self):
        self._stop_agenda_alert_timers()
        self._agenda_alert_flash_on = False
        if hasattr(self, "agenda_alert"):
            self.agenda_alert.hide()
            self._apply_agenda_alert_style()

    def _start_agenda_alert_timers(self):
        if self._agenda_alert_flash_timer is None:
            self._agenda_alert_flash_timer = QTimer(self)
            self._agenda_alert_flash_timer.setInterval(700)
            self._agenda_alert_flash_timer.timeout.connect(self._toggle_agenda_alert_flash)
        if not self._agenda_alert_flash_timer.isActive():
            self._agenda_alert_flash_timer.start()

        if self._agenda_beep_timer is None:
            self._agenda_beep_timer = QTimer(self)
            self._agenda_beep_timer.setInterval(30_000)
            self._agenda_beep_timer.timeout.connect(self._beep_agenda_alert)
        if not self._agenda_beep_timer.isActive():
            self._agenda_beep_timer.start()

    def _stop_agenda_alert_timers(self):
        if self._agenda_alert_flash_timer and self._agenda_alert_flash_timer.isActive():
            self._agenda_alert_flash_timer.stop()
        if self._agenda_beep_timer and self._agenda_beep_timer.isActive():
            self._agenda_beep_timer.stop()

    def _toggle_agenda_alert_flash(self):
        self._agenda_alert_flash_on = not self._agenda_alert_flash_on
        self._apply_agenda_alert_style()

    def _beep_agenda_alert(self):
        if not self._pending_agenda_reminders:
            return
        with contextlib.suppress(Exception):
            QApplication.beep()

    def _apply_agenda_alert_style(self):
        scheme = scheme_from_name(self._theme_mode.value)
        active_bg = scheme.warning
        idle_bg = scheme.warning_bg
        bg = active_bg if self._agenda_alert_flash_on else idle_bg
        text = scheme.text_on_accent if self._agenda_alert_flash_on else scheme.warning_text
        button_bg = scheme.bg_primary
        button_hover = scheme.bg_hover

        self.agenda_alert.setStyleSheet(
            f"""
            QWidget#agendaAlert {{
                background: {bg};
                border-bottom: 1px solid {scheme.warning};
            }}
            """
        )
        self.agenda_alert_label.setStyleSheet(f"color: {text}; font-size: 14px; font-weight: 700;")
        self.agenda_alert_button.setStyleSheet(
            f"""
            QPushButton {{
                background: {button_bg};
                color: {scheme.text_primary};
                border: 1px solid {scheme.border_default};
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {button_hover};
            }}
            """
        )

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
        self._reset_voice_stream()
        should_stream_voice = self._voice_enabled or self._next_response_should_speak_on_pc
        self._voice_stream_enabled_for_response = should_stream_voice
        self._voice_stream_force_enabled = should_stream_voice

    def _on_ai_response_token(self, token: str):
        self.chat_view.append_streaming(token)
        self._stream_voice_token(token)

    def _on_ai_response_finished(self, full_text: str):
        self._ai_busy = False
        self.input_area.set_busy(False)
        self.chat_view.finish_streaming(full_text)
        if self._current_conv_id:
            self.conversation_manager.add_message(self._current_conv_id, "assistant", full_text)
        if self._mobile_server:
            self._mobile_server.publish_response(full_text, kind="assistant")
            self._publish_pending_mobile_voice_audio()
        should_speak_on_pc = self._voice_enabled or self._next_response_should_speak_on_pc
        self._next_response_should_speak_on_pc = False
        if should_speak_on_pc and full_text.strip():
            if self._voice_stream_had_content:
                self._flush_voice_stream(full_text)
            else:
                self._enqueue_voice_stream_chunk(full_text, continuation=False)
        else:
            self._reset_voice_stream()

    def _on_ai_response_error(self, error: str):
        self._ai_busy = False
        self.input_area.set_busy(False)
        self.chat_view.hide_thinking()
        self._reset_voice_stream()
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
        """Fill model combo with GGUF_MODELS and mark missing local files."""
        from core.config import GGUF_MODELS, get_model_by_id

        model_entries = []
        for model in GGUF_MODELS:
            model_path = self.settings.get_model_path(model.id)
            installed = model_path.exists()
            status = "" if installed else " - nao instalado"
            model_entries.append(
                {
                    "id": model.id,
                    "label": f"{model.display_name}{status}",
                    "display_name": model.display_name,
                    "installed": installed,
                    "path": str(model_path),
                    "hf_repo": model.hf_repo,
                    "hf_file": model.hf_file,
                }
            )
        self.input_area.set_models(model_entries)
        current = get_model_by_id(self.settings.llm_model)
        if current:
            self._select_model_in_combo(current.id)

    def _select_model_in_combo(self, model_id: str) -> None:
        combo = self.input_area.model_combo
        previous_state = combo.blockSignals(True)
        try:
            for idx in range(combo.count()):
                data = combo.itemData(idx)
                if isinstance(data, dict) and data.get("id") == model_id:
                    combo.setCurrentIndex(idx)
                    return
        finally:
            combo.blockSignals(previous_state)

    def _on_model_list_loaded(self, models: list):
        self.input_area.set_models(models)

    def _on_model_changed(self, display_name: str):
        """Switch to the selected model by display name."""
        from core.config import GGUF_MODELS

        selected_data = self.input_area.model_combo.currentData()
        selected_id = selected_data.get("id") if isinstance(selected_data, dict) else None
        match = next(
            (m for m in GGUF_MODELS if m.id == selected_id or m.display_name == display_name),
            None,
        )
        if not match:
            return
        old_model = self.settings.llm_model
        if match.id == old_model:
            return
        model_path = self.settings.get_model_path(match.id)
        installed = model_path.exists()
        if isinstance(selected_data, dict):
            installed = bool(selected_data.get("installed", installed))
            if not installed:
                model_path = type(model_path)(selected_data.get("path", model_path))
        if not installed:
            self._select_model_in_combo(old_model)
            QMessageBox.information(
                self,
                "Modelo nao instalado",
                "Este modelo ainda nao esta na pasta resources.\n\n"
                f"Arquivo esperado:\n{model_path}\n\n"
                "Baixe no seletor de LLM ou coloque o GGUF em:\n"
                f"{self.settings.get_resources_dir()}\n\n"
                f"Repositorio: {match.hf_repo}\n"
                f"Arquivo: {match.hf_file}",
            )
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
                self._select_model_in_combo(old_model)
                QMessageBox.warning(self, "Erro", f"Falha ao carregar modelo {match.name}")
        except Exception as e:
            self.settings.llm_model = old_model
            self._select_model_in_combo(old_model)
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
            self._reset_voice_stream()
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
        self._voice_stream_active = False
        QMessageBox.warning(self, "Erro na voz", error)

    def _on_voice_audio_ready(self, audio: bytes, mime_type: str):
        if self._mobile_server:
            if self._ai_busy and self._voice_stream_enabled_for_response:
                self._pending_mobile_voice_audio.append((audio, mime_type))
                return
            self._mobile_server.publish_audio(audio, mime_type=mime_type)

    def _on_voice_finished(self):
        self._voice_stream_active = False
        if self._jarvis:
            self._jarvis.stop_speaking()

    def _on_jarvis_stopped(self):
        pass

    # User message handler
    def _on_user_message(self, text: str):
        self._reset_voice_stream()
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

    def _stream_voice_token(self, token: str):
        if not self._voice_stream_enabled_for_response or not token:
            return

        self._voice_stream_buffer += token
        self._voice_stream_had_content = True
        while True:
            if self._voice_stream_chunks_enqueued:
                chunk, remaining = pop_ready_tts_chunk(
                    self._voice_stream_buffer,
                    min_chars=TTS_STREAM_FOLLOWUP_MIN_CHARS,
                    min_sentence_chars=TTS_STREAM_FOLLOWUP_SENTENCE_CHARS,
                    max_chars=TTS_STREAM_FOLLOWUP_MAX_CHARS,
                )
            else:
                chunk, remaining = pop_ready_tts_chunk(self._voice_stream_buffer)
            self._voice_stream_buffer = remaining
            if not chunk:
                break
            self._enqueue_voice_stream_chunk(chunk)

    def _flush_voice_stream(self, full_text: str = ""):
        missing_tail = self._missing_voice_stream_tail(full_text)
        if missing_tail:
            self._voice_stream_buffer = ""
            self._enqueue_voice_stream_chunk(missing_tail, continuation=False)
        elif self._voice_stream_buffer.strip():
            self._enqueue_voice_stream_chunk(
                self._voice_stream_buffer.strip(),
                continuation=False,
            )
            self._voice_stream_buffer = ""
        self._finish_voice_stream()

    def _enqueue_voice_stream_chunk(self, text: str, *, continuation: bool = True):
        cleaned = naturalize_tts_text(text)
        if not cleaned:
            return
        self._ensure_voice_stream_started()
        self._voice_stream_enqueued_text = f"{self._voice_stream_enqueued_text} {cleaned}".strip()
        self._voice_stream_chunks_enqueued += 1
        self.worker_controller.enqueue_voice_chunk(cleaned, continuation=continuation)

    def _ensure_voice_stream_started(self):
        if self._voice_stream_active:
            return
        self._voice_stream_active = True
        self._voice_stream_finish_requested = False
        if self._jarvis:
            self._jarvis.start_speaking()
        self.worker_controller.start_voice_stream(force_enabled=self._voice_stream_force_enabled)

    def _finish_voice_stream(self):
        if not self._voice_stream_active or self._voice_stream_finish_requested:
            return
        self._voice_stream_finish_requested = True
        self.worker_controller.finish_voice_stream()

    def _reset_voice_stream(self):
        self._voice_stream_enabled_for_response = False
        self._voice_stream_force_enabled = False
        self._voice_stream_buffer = ""
        self._voice_stream_active = False
        self._voice_stream_had_content = False
        self._voice_stream_enqueued_text = ""
        self._voice_stream_chunks_enqueued = 0
        self._voice_stream_finish_requested = False
        self._pending_mobile_voice_audio = []

    def _publish_pending_mobile_voice_audio(self):
        if not self._mobile_server or not self._pending_mobile_voice_audio:
            return
        for audio, mime_type in self._pending_mobile_voice_audio:
            self._mobile_server.publish_audio(audio, mime_type=mime_type)
        self._pending_mobile_voice_audio = []

    def _missing_voice_stream_tail(self, full_text: str) -> str:
        final_text = naturalize_tts_text(full_text)
        spoken_text = naturalize_tts_text(self._voice_stream_enqueued_text)
        if not final_text:
            return ""
        if not spoken_text:
            return final_text
        if final_text.startswith(spoken_text):
            return final_text[len(spoken_text) :].strip()
        buffer_text = naturalize_tts_text(self._voice_stream_buffer)
        if buffer_text and final_text.endswith(buffer_text):
            return buffer_text
        return ""

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
        today = date.today().strftime("%d/%m/%Y")
        assistant = self.settings.assistant
        agenda_context = ""
        if getattr(self.settings.modules, "is_enabled", None) and self.settings.modules.is_enabled(
            "agenda"
        ):
            agenda_service = getattr(self, "agenda_service", None) or get_agenda_service()
            agenda_context = f"\n\n{agenda_service.prompt_context()}"
        return (
            f"Voce e {assistant.name}, {assistant.profile}. "
            f"Sua identidade fixa e Celsius. Hoje e {today}. "
            "Ajude em tarefas gerais do usuario quando solicitado, incluindo redacao, estudos, "
            "tecnologia e explicacoes. O perfil da empresa orienta contexto, mas nao limita "
            "os assuntos que voce pode responder."
            f"{agenda_context}"
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
        if self._agenda_timer and self._agenda_timer.isActive():
            self._agenda_timer.stop()
        self._stop_agenda_alert_timers()
        self._stop_mobile_access()
        self.worker_controller.cleanup()
        super().closeEvent(event)


# Re-export for backwards compatibility with tests
from ui.chat import MessageBubble

__all__ = ["MessageBubble", "ModernChatView", "ModernInputArea", "ModernChatWindow"]
