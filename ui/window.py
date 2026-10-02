"""
Main Window - Janela principal refatorada usando controllers e views extraídos.
"""

import contextlib
import logging
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.agenda import get_agenda_service
from core.extras import feature_notice_lines
from core.inventory import get_inventory_service
from core.memory import get_memory_service
from core.mobile_access import (
    ensure_mobile_token,
    get_mobile_runtime,
    start_for_settings,
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
from ui.task_panel import TaskPanel
from ui.theme import ThemeMode, scheme_from_name
from workers.ai_worker import WorkerManager

logger = logging.getLogger(__name__)



class ModernChatWindow(QMainWindow):
    """Main window with sidebar and chat area."""

    mobile_command_received = Signal(str)

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        for notice in feature_notice_lines():
            logger.warning("Recurso opcional indisponivel; habilite com: %s", notice)
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
        self._is_processing_message = False
        self._work_mode_enabled = False
        self._slow_model_suggestions_shown = set()
        self._next_response_should_speak_on_pc = False
        self._response_from_mobile = False
        self._mobile_partial_buffer = ""
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
        self._refresh_workspace_branding()
        self._apply_theme()
        self._load_conversations()

        if self._jarvis:
            self._jarvis.position_at_topbar(self)
            self._jarvis.show()

        # Connect controllers
        self._connect_controllers()
        self.mobile_command_received.connect(self._on_mobile_command_received)

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

        # WORK button
        self.work_btn = QPushButton("WORK")
        self.work_btn.setToolTip("Modo Work: múltiplos agentes colaborando (Ctrl+W)")
        self.work_btn.setCursor(Qt.PointingHandCursor)
        self.work_btn.setCheckable(True)
        self.work_btn.setFixedHeight(36)
        s = scheme_from_name(self._theme_mode.value)
        self.work_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {s.accent_primary};
                border-radius: 6px;
                padding: 4px 16px;
                color: {s.accent_primary};
                font-weight: 700;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {s.accent_primary};
                color: {s.text_on_accent};
            }}
            QPushButton:checked {{
                background: {s.accent_primary};
                color: {s.text_on_accent};
            }}
        """)
        self.work_btn.clicked.connect(self._toggle_work_mode)
        top_bar_layout.addWidget(self.work_btn)

        # WORK status label (shows what agents are doing)
        self.work_status_label = QLabel("")
        self.work_status_label.setObjectName("workStatusLabel")
        self.work_status_label.setWordWrap(True)
        self.work_status_label.setMaximumWidth(280)
        self.work_status_label.setStyleSheet(f"""
            QLabel#workStatusLabel {{
                color: {s.text_secondary};
                font-size: 10px;
                font-style: italic;
                padding: 2px 8px;
                background: transparent;
            }}
        """)
        self.work_status_label.hide()
        top_bar_layout.addWidget(self.work_status_label)

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

        # Task panel (for agentic modes)
        self.task_panel = TaskPanel(scheme=scheme_from_name(self._theme_mode.value))
        self.task_panel.confirm_requested.connect(self._on_task_confirm)
        self.task_panel.cancel_requested.connect(self._on_task_cancel)
        self.task_panel.pause_requested.connect(self._on_task_pause)
        self.task_panel.continue_requested.connect(self._on_task_continue)
        self.task_panel.mode_changed.connect(self._on_task_mode_changed)
        self.task_panel.hide()
        main_layout.addWidget(self.task_panel, 1)

        # Input area
        self.input_area = ModernInputArea(scheme=scheme_from_name(self._theme_mode.value))
        self.input_area.send_message.connect(self._on_user_message)
        self.input_area.attach_file.connect(self._on_attach_file)
        self.input_area.toggle_mic.connect(self._toggle_mic)
        self.input_area.toggle_voice.connect(self._toggle_voice)
        self.input_area.stop_response.connect(self._on_stop_response)
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
        self.worker_controller.ai_response_cancelled.connect(self._on_ai_response_cancelled)
        self.worker_controller.ai_response_error.connect(self._on_ai_response_error)
        self.worker_controller.ai_status_update.connect(self._on_ai_status_update)
        self.worker_controller.ai_suggestion.connect(self._on_ai_suggestion)
        self.worker_controller.ai_notice.connect(self._on_ai_notice)
        self.worker_controller.model_load_error.connect(self._on_model_load_error)
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
        if hasattr(self, "task_panel"):
            self.task_panel.set_scheme(scheme)
        # Update WORK button style
        if hasattr(self, "work_btn"):
            self.work_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid {scheme.accent_primary};
                    border-radius: 6px;
                    padding: 4px 16px;
                    color: {scheme.accent_primary};
                    font-weight: 700;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {scheme.accent_primary};
                    color: {scheme.text_on_accent};
                }}
                QPushButton:checked {{
                    background: {scheme.accent_primary};
                    color: {scheme.text_on_accent};
                }}
            """)
        # Update WORK status label style
        if hasattr(self, "work_status_label"):
            self.work_status_label.setStyleSheet(f"""
                QLabel#workStatusLabel {{
                    color: {scheme.text_secondary};
                    font-size: 10px;
                    font-style: italic;
                    padding: 2px 8px;
                    background: transparent;
                }}
            """)

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
        # Initialize task panel for this conversation
        if hasattr(self, "task_panel"):
            from core.agent_tasks import AgentTaskStore

            if not hasattr(self, "_task_store"):
                self._task_store = AgentTaskStore(self.settings.data_dir / "agent_tasks.db")
                self.task_panel.set_store(self._task_store)
            self.task_panel.set_scope(conv_id)
            self.task_panel.refresh_current_task()

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

        # Update task panel scope
        if hasattr(self, "task_panel") and hasattr(self, "_task_store"):
            self.task_panel.set_scope(conv_id)
            self.task_panel.refresh_current_task()

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
            # Show task panel for non-assistente modes
            mode = self.input_area.get_mode()
            if mode != "assistente" and hasattr(self, "task_panel"):
                self.task_panel.show()
            elif hasattr(self, "task_panel"):
                self.task_panel.hide()
        elif tab == "inventory":
            self.chat_view.hide()
            self.input_area.hide()
            self.inventory_panel.show()
            self.kanban_container.hide()
            self.module_placeholder.hide()
            if hasattr(self, "task_panel"):
                self.task_panel.hide()
        elif tab == "kanban":
            self.chat_view.hide()
            self.input_area.hide()
            self.inventory_panel.hide()
            self.kanban_container.show()
            self.module_placeholder.hide()
            if hasattr(self, "task_panel"):
                self.task_panel.hide()
        elif tab in {"suppliers", "settings"}:
            self.chat_view.show()
            self.input_area.show()
            self.inventory_panel.hide()
            self.kanban_container.hide()
            self.module_placeholder.hide()
            if hasattr(self, "task_panel"):
                self.task_panel.hide()
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
            if hasattr(self, "task_panel"):
                self.task_panel.hide()

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
            self._refresh_workspace_branding()
            self._apply_module_configuration()
            self._apply_theme()

    def _start_mobile_access_if_enabled(self):
        if not self.settings.mobile.enabled:
            return
        self._restart_mobile_access(show_message=False)

    def _restart_mobile_access(self, show_message: bool = True, show_pairing: bool = True):
        runtime = get_mobile_runtime()
        existing = runtime.server
        https_warning = ""
        reuse = (
            existing is not None and existing.is_running and self._mobile_server_matches(existing)
        )
        if reuse:
            self._mobile_server = existing
        else:
            self._stop_mobile_access()
            if not self.settings.mobile.enabled:
                return

            token = ensure_mobile_token(self.settings.mobile.pairing_token)
            self.settings.mobile.pairing_token = token
            self.settings.save_local_preferences()

            server, https_warning = start_for_settings(
                self.settings,
                command_callback=runtime.command,
                voice_command_callback=runtime.voice,
            )
            runtime.attach(server)
            self._mobile_server = server
        runtime.set_sink(self)
        if show_message:
            self.chat_view.add_assistant_message(
                "Acesso pelo celular ativo nesta rede:\n\n"
                f"{self._mobile_server.url}\n\n"
                "Use esse endereço no navegador do celular. Mantenha o token privado."
                f"{https_warning}"
            )
        if show_pairing:
            self._show_mobile_pairing_dialog()

    def _mobile_server_matches(self, server) -> bool:
        expected_host = self.settings.mobile.host if self.settings.mobile.allow_lan else "127.0.0.1"
        expected_port = int(self.settings.mobile.port)
        expected_https = bool(self.settings.mobile.use_https)
        expected_token = ensure_mobile_token(self.settings.mobile.pairing_token)
        return (
            server.port == expected_port
            and server.use_https == expected_https
            and server.host == expected_host
            and server.token == expected_token
            and self.settings.mobile.voice_commands_enabled == server.voice_enabled
        )

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
        runtime = get_mobile_runtime()
        if runtime.server is not None:
            runtime.close()
        elif self._mobile_server:
            self._mobile_server.stop()
        self._mobile_server = None

    def _queue_mobile_command(self, message: str, source: str):
        if self._ai_busy:
            return (
                False,
                "O Celsius ainda esta respondendo. Tente novamente em instantes.",
            )
        mode_switch = self._apply_mode_command(message)
        if mode_switch is not None:
            return True, mode_switch
        prefix = "Comando por voz do celular" if source == "phone_voice" else "Comando do celular"
        self.mobile_command_received.emit(f"{prefix}: {message}")
        return True, "Comando enviado ao Celsius no PC."

    def _apply_mode_command(self, message: str) -> str | None:
        """Honour "modo X" on the phone/voice, returning the notice or None."""
        from core.agent_modes import get_mode, parse_mode_command

        mode_id = parse_mode_command(message)
        if mode_id is None:
            return None
        self.input_area.set_mode(mode_id)
        mode = get_mode(mode_id)
        return f"Modo alterado para {mode.label}. {mode.summary}"

    def _apply_task_voice_command(self, message: str) -> str | None:
        """Handle task-related voice commands."""
        from core.agent_modes import get_mode
        from core.agent_tasks import normalize_state

        if not hasattr(self, "_task_store") or not self._current_conv_id:
            return None

        cleaned = message.strip().lower()

        # Task progress query
        if any(
            cmd in cleaned
            for cmd in [
                "consulte o andamento",
                "andamento da tarefa",
                "status da tarefa",
                "como está a tarefa",
            ]
        ):
            tasks = self._task_store.list(self._current_conv_id, limit=1)
            if not tasks:
                return "Nenhuma tarefa ativa no momento."
            task = tasks[0]
            status = normalize_state(task.get("status", "unknown"))
            mode = get_mode(task.get("mode", ""))
            steps = task.get("steps", [])
            completed = sum(1 for s in steps if normalize_state(s.get("status", "")) == "succeeded")
            total = len(steps)
            return f"Tarefa {task['id']} ({mode.label}): {status}. Objetivo: {task.get('objective', '')[:100]}. Progresso: {completed}/{total} passos."

        # Cancel task
        if any(cmd in cleaned for cmd in ["cancele a tarefa", "cancelar tarefa", "pare a tarefa"]):
            tasks = self._task_store.list(self._current_conv_id, limit=1)
            if not tasks:
                return "Nenhuma tarefa ativa para cancelar."
            task = tasks[0]
            task["status"] = "cancelled"
            task["error"] = "Tarefa cancelada por comando de voz."
            self._task_store.save(task)
            if hasattr(self, "task_panel"):
                self.task_panel.refresh_current_task()
            return f"Tarefa {task['id']} cancelada."

        # Confirm (approve)
        if any(cmd in cleaned for cmd in ["confirma", "confirmar", "autorizar", "sim, confirmo"]):
            tasks = self._task_store.list(self._current_conv_id, limit=1)
            if not tasks:
                return "Nenhuma tarefa aguardando confirmação."
            task = tasks[0]
            for step in task.get("steps", []):
                if step.get("status") in ("waiting_confirmation", "awaiting_approval"):
                    code = step.get("approval_code")
                    if code and step.get("expires", 0) > time.time():
                        step["status"] = "authorized"
                        self._task_store.save(task)
                        if hasattr(self, "task_panel"):
                            self.task_panel.refresh_current_task()
                        return f"Ação confirmada. A tarefa {task['id']} vai continuar."
                    elif code:
                        return "A autorização expirou. Use 'retomar' para revisar."
            return "Nenhuma ação pendente de confirmação."

        # Reject (não confirme)
        if any(
            cmd in cleaned
            for cmd in [
                "não confirme",
                "nao confirme",
                "rejeitar",
                "cancelar ação",
                "não autorizo",
                "nao autorizo",
            ]
        ):
            tasks = self._task_store.list(self._current_conv_id, limit=1)
            if not tasks:
                return "Nenhuma tarefa aguardando confirmação."
            task = tasks[0]
            for step in task.get("steps", []):
                if step.get("status") in ("waiting_confirmation", "awaiting_approval"):
                    code = step.get("approval_code")
                    if code:
                        step["status"] = "cancelled"
                        step.pop("approval_code", None)
                        task["status"] = "cancelled"
                        task["rejected_action"] = True
                        self._task_store.save(task)
                        if hasattr(self, "task_panel"):
                            self.task_panel.refresh_current_task()
                        return f"Ação rejeitada. Tarefa {task['id']} cancelada."
            return "Nenhuma ação pendente de confirmação."

        # Pause task
        if any(cmd in cleaned for cmd in ["pause a tarefa", "pausar tarefa", "pause"]):
            tasks = self._task_store.list(self._current_conv_id, limit=1)
            if not tasks:
                return "Nenhuma tarefa ativa para pausar."
            task = tasks[0]
            if task["status"] in ("running", "waiting_confirmation", "awaiting_approval"):
                task["status"] = "paused"
                task["error"] = "Tarefa pausada por comando de voz."
                self._task_store.save(task)
                if hasattr(self, "task_panel"):
                    self.task_panel.refresh_current_task()
                return f"Tarefa {task['id']} pausada."
            return f"Tarefa {task['id']} não pode ser pausada no estado atual."

        # Continue task
        if any(
            cmd in cleaned
            for cmd in [
                "continue a tarefa",
                "continuar tarefa",
                "retome a tarefa",
                "retomar tarefa",
            ]
        ):
            tasks = self._task_store.list(self._current_conv_id, limit=1)
            if not tasks:
                return "Nenhuma tarefa para continuar."
            task = tasks[0]
            if task["status"] in ("paused", "waiting_confirmation", "awaiting_approval"):
                task["status"] = "running"
                task["error"] = ""
                self._task_store.save(task)
                if hasattr(self, "task_panel"):
                    self.task_panel.refresh_current_task()
                return f"Tarefa {task['id']} continuada."
            return f"Tarefa {task['id']} não está pausada."

        return None

    @staticmethod
    def _strip_transport_prefix(text: str) -> str:
        """Drop the "Comando do celular:" label before the model reads the text.

        The label is useful for the user on screen, but it is transport noise
        for the model, so a voice/phone order like "modo estoque" still
        reaches the mode parser as a plain request.
        """
        cleaned = str(text or "").strip()
        for prefix in (
            "Comando por voz do celular:",
            "Comando do celular:",
            "Comando por voz:",
        ):
            if cleaned.lower().startswith(prefix.lower()):
                return cleaned[len(prefix) :].strip()
        return cleaned

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
                mode_switch = self._apply_mode_command(transcript)
                if mode_switch is not None:
                    return True, transcript, mode_switch
                task_switch = self._apply_task_voice_command(transcript)
                if task_switch is not None:
                    return True, transcript, task_switch
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

            mode_switch = self._apply_mode_command(transcript)
            if mode_switch is not None:
                return True, transcript, mode_switch
            task_switch = self._apply_task_voice_command(transcript)
            if task_switch is not None:
                return True, transcript, task_switch
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
        self._response_from_mobile = True
        self._on_user_message(message)

    # AI Response handlers
    def _on_ai_response_started(self):
        self._ai_busy = True
        self.input_area.set_busy(True)
        self.chat_view.start_streaming()
        self._reset_voice_stream()
        self._mobile_partial_buffer = ""
        should_stream_voice = self._voice_enabled or self._next_response_should_speak_on_pc
        self._voice_stream_enabled_for_response = should_stream_voice
        self._voice_stream_force_enabled = should_stream_voice
        # Show work status when WORK mode is active
        if getattr(self, "_work_mode_enabled", False) and hasattr(self, "work_status_label"):
            self.work_status_label.setText("Iniciando análise...")
            self.work_status_label.show()

    def _on_ai_response_token(self, token: str):
        self.chat_view.append_streaming(token)
        self._stream_voice_token(token)
        if self._mobile_server is not None and self._response_from_mobile:
            self._mobile_partial_buffer += token
            self._mobile_server.publish_partial(self._mobile_partial_buffer)

    def _on_ai_response_finished(self, full_text: str):
        self._ai_busy = False
        self.input_area.set_busy(False)
        keep_stream = self.worker_controller.last_turn_was_task
        full_text = self.chat_view.finish_streaming(full_text, keep_stream=keep_stream)
        if self._current_conv_id:
            self.conversation_manager.add_message(self._current_conv_id, "assistant", full_text)
        self._kick_memory_extraction()
        if self._mobile_server:
            self._mobile_server.publish_response(
                full_text or "(sem resposta visivel)", kind="assistant"
            )
            self._publish_pending_mobile_voice_audio()
        should_speak_on_pc = self._voice_enabled or self._next_response_should_speak_on_pc
        self._next_response_should_speak_on_pc = False
        self._response_from_mobile = False
        if should_speak_on_pc and full_text.strip():
            if self._voice_stream_had_content:
                self._flush_voice_stream(full_text)
            else:
                self._enqueue_voice_stream_chunk(full_text, continuation=False)
        else:
            self._reset_voice_stream()
        # Clear work status when WORK mode response finishes
        if getattr(self, "_work_mode_enabled", False) and hasattr(self, "work_status_label"):
            self.work_status_label.setText("Concluído")
            # Hide after a short delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self.work_status_label.setText("Aguardando tarefa...") if getattr(self, "_work_mode_enabled", False) else None)

    def _on_stop_response(self) -> bool:
        stopped = self.worker_controller.stop_response()
        if not stopped and self._ai_busy:
            self.chat_view.show_thinking("Interrompendo...")
        return stopped

    def _on_ai_response_cancelled(self, partial_text: str):
        self._ai_busy = False
        self.input_area.set_busy(False)
        partial_text = self.chat_view.finish_streaming(
            partial_text, keep_stream=self.worker_controller.last_turn_was_task
        )
        if self._current_conv_id and partial_text.strip():
            self.conversation_manager.add_message(self._current_conv_id, "assistant", partial_text)
        if self._mobile_server:
            self._mobile_server.publish_response(
                partial_text or "(resposta interrompida)", kind="assistant"
            )
        self._reset_voice_stream()
        self._next_response_should_speak_on_pc = False
        self._response_from_mobile = False

    def _kick_memory_extraction(self) -> None:
        """Learn durable user facts from the finished turn, in background."""
        if not self._memories_enabled:
            return
        features = getattr(self.settings, "features", None)
        if features is not None and not getattr(features, "memory", True):
            return
        memory_settings = getattr(self.settings, "memory", None)
        if memory_settings is not None and not getattr(
            memory_settings, "auto_extract_facts", False
        ):
            return
        if not self._current_conv_id:
            return
        conversation = self.conversation_manager.get_conversation(self._current_conv_id)
        if not conversation:
            return
        recent = (
            getattr(memory_settings, "extraction_recent_messages", 10)
            if memory_settings is not None
            else 10
        )
        messages = [
            {"role": item.get("role"), "content": item.get("content")}
            for item in conversation.get("messages", [])
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ][-recent:]
        if not messages:
            return
        try:
            from core.memory import extract_and_store_async

            extract_and_store_async(messages, conversation_id=self._current_conv_id)
        except Exception as exc:
            logger.warning("Nao foi possivel agendar extracao de memorias: %s", exc)

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
        self._response_from_mobile = False

    def _on_ai_suggestion(self, suggestion: str):
        """Show a lighter-model suggestion in the chat as a non-persistent bubble."""
        if not suggestion:
            return
        if suggestion in self._slow_model_suggestions_shown:
            return
        self._slow_model_suggestions_shown.add(suggestion)
        self.chat_view.add_assistant_message(f"[Dica] {suggestion}")

    def _on_ai_notice(self, notice: str):
        """Show a model-switch/context notice as a non-persistent assistant bubble."""
        if not notice or not notice.strip():
            return
        if notice in self._slow_model_suggestions_shown:
            return
        self._slow_model_suggestions_shown.add(notice)
        self.chat_view.add_assistant_message(notice)

    def _on_ai_status_update(self, status: str):
        label = self._friendly_ai_status(status)
        if label:
            self.chat_view.show_thinking(label)
            # Also show in work status label when WORK mode is active
            if getattr(self, "_work_mode_enabled", False) and hasattr(self, "work_status_label"):
                self.work_status_label.setText(label)

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

    # Task panel handlers
    def _on_task_confirm(self, approval_code: str, step: dict):
        """Handle task confirmation."""
        if self._task_store and self._current_conv_id:
            task = self._task_store.find_approval(approval_code, self._current_conv_id)
            if task:
                for s in task["steps"]:
                    if s.get("approval_code") == approval_code:
                        s["status"] = "authorized"
                        break
                self._task_store.save(task)
                self.task_panel.refresh_current_task()

    def _on_task_cancel(self, task_id: str):
        """Handle task cancellation."""
        if self._task_store and self._current_conv_id:
            task = self._task_store.get(task_id, self._current_conv_id)
            if task:
                task["status"] = "cancelled"
                task["error"] = "Tarefa cancelada pelo usuário."
                self._task_store.save(task)
                self.task_panel.refresh_current_task()

    def _on_task_pause(self, task_id: str):
        """Handle task pause."""
        if self._task_store and self._current_conv_id:
            task = self._task_store.get(task_id, self._current_conv_id)
            if task:
                task["status"] = "paused"
                task["error"] = "Tarefa pausada pelo usuário."
                self._task_store.save(task)
                self.task_panel.refresh_current_task()

    def _on_task_continue(self, task_id: str):
        """Handle task continuation."""
        if self._task_store and self._current_conv_id:
            task = self._task_store.get(task_id, self._current_conv_id)
            if task and task["status"] in ("paused", "waiting_confirmation"):
                task["status"] = "running"
                task["error"] = ""
                self._task_store.save(task)
                self.task_panel.refresh_current_task()
                # The task runtime will pick it up on next RETOMAR or auto-continue

    def _on_task_mode_changed(self, mode_id: str):
        """Handle agent mode change from task panel."""
        self.input_area.set_mode(mode_id)


    # User message handler
    def _on_user_message(self, text: str):
        if self._ai_busy:
            self.chat_view.add_assistant_message(
                "Ainda estou terminando a resposta anterior. "
                "Use o botao Parar (ou Esc) para interromper e enviar a nova pergunta."
            )
            return

        if self._is_processing_message:
            return

        text = self._strip_transport_prefix(text)
        if not text:
            return

        self._is_processing_message = True
        try:
            self._ai_busy = True
            self.input_area.set_busy(True)

            self._reset_voice_stream()
            self.worker_controller.stop_voice()
            if self._jarvis:
                self._jarvis.stop_speaking()

            if not self._current_conv_id:
                self._new_conversation()

            attachments = self.input_area.get_attachments()
            self.conversation_manager.add_message(self._current_conv_id, "user", text, attachments)
            self.chat_view.add_user_message(text, attachments)
            self.input_area.clear_attachments()

            QTimer.singleShot(0, lambda: self._start_ai_response(text, attachments))
        finally:
            self._is_processing_message = False

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

        # Auto-select agents when WORK mode is enabled
        work_agents = []
        if getattr(self, "_work_mode_enabled", False):
            from ai.agents import classificar_tarefa
            agente = classificar_tarefa(text)
            if agente and agente.id != "assistente":
                work_agents = [agente.id]

        sent = self.worker_controller.send_message(
            message=text,
            system_prompt=system_prompt,
            conversation_history=history,
            memories=memories,
            model_name=self.settings.llm_model,
            attachments=attachments or [],
            conversation_id=self._current_conv_id or "",
            agent_mode=self._selected_agent_mode(),
            work_agents=work_agents,
        )
        if sent is False:
            self._ai_busy = False
            self.input_area.set_busy(False)

    def _selected_agent_mode(self) -> str:
        """Mode chosen in the input area, or the configured default."""
        from core.agent_modes import get_mode, is_valid_mode

        if not self.settings.agent.enabled:
            return get_mode(None).id
        # Use the default mode since input_area no longer has mode selector
        mode_id = self.settings.agent.default_mode
        if not is_valid_mode(mode_id):
            return get_mode(None).id
        return mode_id

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
    def _refresh_workspace_branding(self):
        """Exibe o nome da empresa (Config > Perfil do cliente/empresa > Empresa)
        no titulo da janela e no topo da tela; 'Celsius Project AI' se vazio."""
        company = self.settings.customer.company_name.strip()
        title = company if company else "Celsius Project AI"
        self.setWindowTitle(title)
        if self.workspace_title is not None:
            self.workspace_title.setText(title)

    def _show_settings(self):
        from ui.dialogs import ConfiguracoesDialog

        dialog = ConfiguracoesDialog(
            self.settings, scheme=scheme_from_name(self._theme_mode.value), parent=self
        )
        if dialog.exec():
            self._refresh_workspace_branding()
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
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self._toggle_work_mode)

    def _toggle_work_mode(self):
        """Toggle WORK mode on/off."""
        if self.work_btn.isChecked():
            self._enable_work_mode()
        else:
            self._disable_work_mode()

    def _enable_work_mode(self):
        """Enable WORK mode - system will auto-select agents based on task."""
        self._work_mode_enabled = True
        # Show task panel for work mode
        if hasattr(self, "task_panel"):
            self.task_panel.show()
        # Show work status label
        if hasattr(self, "work_status_label"):
            self.work_status_label.setText("Aguardando tarefa...")
            self.work_status_label.show()

    def _disable_work_mode(self):
        """Disable WORK mode."""
        self._work_mode_enabled = False
        if hasattr(self, "task_panel"):
            self.task_panel.hide()
        # Hide work status label
        if hasattr(self, "work_status_label"):
            self.work_status_label.hide()
            self.work_status_label.setText("")



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
