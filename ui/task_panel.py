"""
Task Panel - Painel de tarefas agênticas para desktop.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.agent_modes import get_mode, list_modes
from core.agent_tasks import AgentTaskStore, normalize_state
from core.decisions import get_decision_client
from core.settings import get_settings
from ui.theme import LIGHT_SCHEME
from ui.theme.tokens import RADIUS, SPACING, TYPOGRAPHY


class StepWidget(QWidget):
    """Widget para exibir um passo da tarefa."""

    def __init__(self, step: dict, index: int, scheme=None, parent=None):
        super().__init__(parent)
        self.step = step
        self.index = index
        self._scheme = scheme or LIGHT_SCHEME
        self._setup_ui()

    def _setup_ui(self):
        s = self._scheme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING.space_2, SPACING.space_2, SPACING.space_2, SPACING.space_2
        )
        layout.setSpacing(SPACING.space_1)

        # Header
        header = QHBoxLayout()
        header.setSpacing(SPACING.space_2)

        # Step number
        num_label = QLabel(f"Passo {self.index + 1}")
        num_label.setStyleSheet(f"""
            font-weight: 700;
            font-size: {TYPOGRAPHY.text_sm}px;
            color: {s.text_secondary};
        """)
        header.addWidget(num_label)

        # Tool name
        tool = self.step.get("tool", "")
        tool_label = QLabel(f"🔧 {tool}")
        tool_label.setStyleSheet(f"""
            font-family: monospace;
            font-size: {TYPOGRAPHY.text_sm}px;
            color: {s.text_primary};
        """)
        header.addWidget(tool_label)

        # Status badge
        status = normalize_state(self.step.get("status", "planned"))
        self.status_label = QLabel(status.replace("_", " ").title())
        self.status_label.setStyleSheet(self._status_style(status))
        header.addWidget(self.status_label)

        header.addStretch()
        layout.addLayout(header)

        # Arguments
        args = self.step.get("arguments", {})
        if args:
            args_text = json.dumps(args, ensure_ascii=False, indent=2)
            if len(args_text) > 300:
                args_text = args_text[:300] + "..."
            args_label = QLabel(f"Argumentos: {args_text}")
            args_label.setWordWrap(True)
            args_label.setStyleSheet(f"""
                font-family: monospace;
                font-size: {TYPOGRAPHY.text_xs}px;
                color: {s.text_muted};
                background: {s.bg_tertiary};
                border-radius: {RADIUS.radius_sm}px;
                padding: {SPACING.space_1}px;
            """)
            layout.addWidget(args_label)

        # Result/Error
        result = self.step.get("result", "")
        if result:
            is_error = result.startswith(("Erro", "Servico'"))
            result_label = QLabel(
                f"Resultado: {result[:500]}" + ("..." if len(result) > 500 else "")
            )
            result_label.setWordWrap(True)
            result_label.setStyleSheet(f"""
                font-family: monospace;
                font-size: {TYPOGRAPHY.text_xs}px;
                color: {s.error if is_error else s.success};
                background: {s.error_bg if is_error else s.success_bg};
                border-radius: {RADIUS.radius_sm}px;
                padding: {SPACING.space_1}px;
            """)
            layout.addWidget(result_label)

    def _status_style(self, status: str) -> str:
        s = self._scheme
        colors = {
            "planned": (s.text_muted, s.bg_tertiary),
            "awaiting_approval": (s.warning, s.warning_bg),
            "authorized": (s.accent_primary, s.accent_subtle),
            "running": (s.accent_primary, s.accent_subtle),
            "succeeded": (s.success, s.success_bg),
            "failed": (s.error, s.error_bg),
            "cancelled": (s.text_muted, s.bg_tertiary),
            "waiting_confirmation": (s.warning, s.warning_bg),
            "paused": (s.text_muted, s.bg_tertiary),
        }
        fg, bg = colors.get(status, (s.text_primary, s.bg_secondary))
        return f"""
            QLabel {{
                background: {bg};
                color: {fg};
                border-radius: {RADIUS.radius_sm}px;
                padding: 2px 8px;
                font-size: {TYPOGRAPHY.text_xs}px;
                font-weight: 600;
            }}
        """

    def update_step(self, step: dict):
        self.step = step
        status = normalize_state(step.get("status", "planned"))
        self.status_label.setText(status.replace("_", " ").title())
        self.status_label.setStyleSheet(self._status_style(status))
        # Rebuild would be better but for simplicity just update status


class TaskPlanWidget(QWidget):
    """Widget para exibir o plano da tarefa."""

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self.plan = []
        self._scheme = scheme or LIGHT_SCHEME
        self._setup_ui()

    def _setup_ui(self):
        s = self._scheme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING.space_2, SPACING.space_2, SPACING.space_2, SPACING.space_2
        )
        layout.setSpacing(SPACING.space_2)

        title = QLabel("Plano da Tarefa")
        title.setStyleSheet(
            f"font-weight: 700; font-size: {TYPOGRAPHY.text_lg}px; color: {s.text_primary};"
        )
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_md}px;
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
            QListWidget::item {{
                padding: {SPACING.space_2}px;
                border-bottom: 1px solid {s.border_default};
            }}
            QListWidget::item:last {{
                border-bottom: none;
            }}
        """)
        layout.addWidget(self.list_widget, 1)

        self.empty_label = QLabel("Nenhum plano gerado ainda")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {s.text_muted}; font-size: {TYPOGRAPHY.text_sm}px;")
        layout.addWidget(self.empty_label)
        self.empty_label.hide()

    def set_plan(self, plan: list):
        self.plan = plan
        self.list_widget.clear()
        if not plan:
            self.empty_label.show()
            self.list_widget.hide()
        else:
            self.empty_label.hide()
            self.list_widget.show()
            for i, step in enumerate(plan):
                item = QListWidgetItem(f"{i + 1}. {step.get('description', 'Sem descrição')}")
                item.setData(Qt.UserRole, step)
                tool = step.get("tool", "")
                if tool:
                    item.setToolTip(f"Ferramenta: {tool}")
                self.list_widget.addItem(item)


class TaskHistoryWidget(QWidget):
    """Widget para exibir histórico de tarefas."""

    task_selected = Signal(str)  # task_id

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or LIGHT_SCHEME
        self.store: AgentTaskStore | None = None
        self.scope = ""
        self._setup_ui()

    def _setup_ui(self):
        s = self._scheme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING.space_2, SPACING.space_2, SPACING.space_2, SPACING.space_2
        )
        layout.setSpacing(SPACING.space_2)

        title = QLabel("Histórico de Tarefas")
        title.setStyleSheet(
            f"font-weight: 700; font-size: {TYPOGRAPHY.text_lg}px; color: {s.text_primary};"
        )
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_md}px;
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
        """)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget, 1)

        self.empty_label = QLabel("Nenhuma tarefa neste contexto")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {s.text_muted}; font-size: {TYPOGRAPHY.text_sm}px;")
        layout.addWidget(self.empty_label)
        self.empty_label.hide()

    def set_store(self, store: AgentTaskStore, scope: str):
        self.store = store
        self.scope = scope
        self.refresh()

    def refresh(self):
        if not self.store or not self.scope:
            return
        tasks = self.store.list(self.scope, limit=50)
        self.list_widget.clear()
        if not tasks:
            self.empty_label.show()
            self.list_widget.hide()
        else:
            self.empty_label.hide()
            self.list_widget.show()
            for task in tasks:
                status = normalize_state(task.get("status", "unknown"))
                mode = task.get("mode", "")
                objective = task.get("objective", "")[:80]
                item = QListWidgetItem(f"[{status}] {mode}: {objective}")
                item.setData(Qt.UserRole, task["id"])
                self.list_widget.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem):
        task_id = item.data(Qt.UserRole)
        if task_id:
            self.task_selected.emit(task_id)


class TaskPanel(QWidget):
    """Painel principal de tarefas agênticas."""

    confirm_requested = Signal(str, dict)  # approval_code, step
    cancel_requested = Signal(str)  # task_id
    pause_requested = Signal(str)  # task_id
    continue_requested = Signal(str)  # task_id
    mode_changed = Signal(str)  # mode_id

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or LIGHT_SCHEME
        self.settings = get_settings()
        self.store: AgentTaskStore | None = None
        self.current_task: dict | None = None
        self.current_scope = ""
        self._setup_ui()
        self._refresh_jev_status()
        self._jev_timer = QTimer(self)
        self._jev_timer.setInterval(15000)
        self._jev_timer.timeout.connect(self._refresh_jev_status)
        self._jev_timer.start()

    def _setup_ui(self):
        s = self._scheme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with mode selector and JEV status
        header = QWidget()
        header.setObjectName("taskPanelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(
            SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2
        )
        header_layout.setSpacing(SPACING.space_2)

        # Mode selector
        self.mode_combo = QComboBox()
        self.mode_combo.setFixedWidth(180)
        self.mode_combo.setCursor(Qt.PointingHandCursor)
        for entry in list_modes():
            self.mode_combo.addItem(entry["label"], entry["id"])
            idx = self.mode_combo.count() - 1
            self.mode_combo.setItemData(idx, entry["summary"], Qt.ToolTipRole)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.mode_combo.setStyleSheet(f"""
            QComboBox {{
                background: {s.bg_tertiary};
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_md}px;
                padding: 4px 12px;
                color: {s.text_primary};
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
        """)
        header_layout.addWidget(QLabel("Modo:"))
        header_layout.addWidget(self.mode_combo)

        # JEV Status indicator
        self.jev_status = QLabel("JEV: verificando...")
        self.jev_status.setStyleSheet(f"""
            QLabel {{
                background: {s.bg_tertiary};
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_md}px;
                padding: 4px 12px;
                color: {s.text_secondary};
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
        """)
        header_layout.addStretch()
        header_layout.addWidget(self.jev_status)

        layout.addWidget(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {s.border_default}; max-height: 1px;")
        layout.addWidget(sep)

        # Main content splitter
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        # Top: Current task info
        self.current_task_widget = self._create_current_task_widget()
        splitter.addWidget(self.current_task_widget)

        # Middle: Steps
        self.steps_widget = self._create_steps_widget()
        splitter.addWidget(self.steps_widget)

        # Bottom: History
        self.history_widget = TaskHistoryWidget(scheme=self._scheme)
        self.history_widget.task_selected.connect(self._on_history_task_selected)
        splitter.addWidget(self.history_widget)

        # Set initial sizes
        splitter.setSizes([200, 300, 200])
        layout.addWidget(splitter, 1)

        # Action buttons
        self._add_action_buttons(layout)

    def _create_current_task_widget(self) -> QWidget:
        s = self._scheme
        widget = QWidget()
        widget.setObjectName("currentTaskWidget")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(
            SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2
        )
        layout.setSpacing(SPACING.space_2)

        # Task header
        header = QHBoxLayout()
        header.setSpacing(SPACING.space_2)

        self.task_title = QLabel("Nenhuma tarefa ativa")
        self.task_title.setStyleSheet(
            f"font-weight: 700; font-size: {TYPOGRAPHY.text_lg}px; color: {s.text_primary};"
        )
        header.addWidget(self.task_title, 1)

        self.task_state = QLabel("")
        self.task_state.setStyleSheet(f"""
            QLabel {{
                background: {s.bg_tertiary};
                border-radius: {RADIUS.radius_md}px;
                padding: 4px 12px;
                font-size: {TYPOGRAPHY.text_sm}px;
                font-weight: 600;
                color: {s.text_secondary};
            }}
        """)
        header.addWidget(self.task_state)

        layout.addLayout(header)

        # Objective
        self.task_objective = QLabel("")
        self.task_objective.setWordWrap(True)
        self.task_objective.setStyleSheet(
            f"font-size: {TYPOGRAPHY.text_sm}px; color: {s.text_secondary};"
        )
        layout.addWidget(self.task_objective)

        # Plan
        self.plan_widget = TaskPlanWidget(scheme=self._scheme)
        layout.addWidget(self.plan_widget, 1)

        return widget

    def _create_steps_widget(self) -> QWidget:
        s = self._scheme
        widget = QWidget()
        widget.setObjectName("stepsWidget")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(
            SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2
        )
        layout.setSpacing(SPACING.space_2)

        title = QLabel("Passos Executados")
        title.setStyleSheet(
            f"font-weight: 700; font-size: {TYPOGRAPHY.text_lg}px; color: {s.text_primary};"
        )
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_md}px;
            }}
        """)

        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(
            SPACING.space_2, SPACING.space_2, SPACING.space_2, SPACING.space_2
        )
        self.steps_layout.setSpacing(SPACING.space_2)
        self.steps_layout.addStretch()

        scroll.setWidget(self.steps_container)
        layout.addWidget(scroll, 1)

        self.steps_empty = QLabel("Nenhum passo executado")
        self.steps_empty.setAlignment(Qt.AlignCenter)
        self.steps_empty.setStyleSheet(f"color: {s.text_muted}; font-size: {TYPOGRAPHY.text_sm}px;")
        self.steps_layout.insertWidget(self.steps_layout.count() - 1, self.steps_empty)
        self.steps_empty.hide()

        return widget

    def _add_action_buttons(self, layout: QVBoxLayout):
        s = self._scheme
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(SPACING.space_2)

        self.btn_confirm = QPushButton("✓ Confirmar")
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.setFixedHeight(40)
        self.btn_confirm.setStyleSheet(f"""
            QPushButton {{
                background: {s.success};
                border: none;
                border-radius: {RADIUS.radius_md}px;
                color: {s.text_on_accent};
                font-weight: 700;
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
            QPushButton:hover {{
                background: {s.success};
                opacity: 0.9;
            }}
            QPushButton:disabled {{
                background: {s.text_muted};
            }}
        """)
        self.btn_confirm.clicked.connect(self._on_confirm)
        self.btn_confirm.setEnabled(False)
        btn_layout.addWidget(self.btn_confirm)

        self.btn_cancel = QPushButton("✗ Cancelar Tarefa")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: {s.error};
                border: none;
                border-radius: {RADIUS.radius_md}px;
                color: {s.text_on_accent};
                font-weight: 700;
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
            QPushButton:hover {{
                background: {s.error};
                opacity: 0.9;
            }}
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_pause = QPushButton("⏸ Pausar")
        self.btn_pause.setCursor(Qt.PointingHandCursor)
        self.btn_pause.setFixedHeight(40)
        self.btn_pause.setStyleSheet(f"""
            QPushButton {{
                background: {s.warning};
                border: none;
                border-radius: {RADIUS.radius_md}px;
                color: {s.warning_text};
                font-weight: 700;
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
            QPushButton:hover {{
                background: {s.warning};
                opacity: 0.9;
            }}
        """)
        self.btn_pause.clicked.connect(self._on_pause)
        btn_layout.addWidget(self.btn_pause)

        self.btn_continue = QPushButton("▶ Continuar")
        self.btn_continue.setCursor(Qt.PointingHandCursor)
        self.btn_continue.setFixedHeight(40)
        self.btn_continue.setStyleSheet(f"""
            QPushButton {{
                background: {s.accent_primary};
                border: none;
                border-radius: {RADIUS.radius_md}px;
                color: {s.text_on_accent};
                font-weight: 700;
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
            QPushButton:hover {{
                background: {s.accent_hover};
            }}
        """)
        self.btn_continue.clicked.connect(self._on_continue)
        self.btn_continue.setEnabled(False)
        btn_layout.addWidget(self.btn_continue)

        layout.addLayout(btn_layout)

    def set_scope(self, scope: str):
        """Define o escopo da conversa atual."""
        self.current_scope = scope
        if self.store:
            self.history_widget.set_store(self.store, scope)
        self.refresh_current_task()

    def set_store(self, store: AgentTaskStore):
        """Define o store de tarefas."""
        self.store = store
        if self.current_scope:
            self.history_widget.set_store(store, self.current_scope)

    def set_mode(self, mode_id: str):
        """Define o modo ativo."""
        idx = self.mode_combo.findData(mode_id)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

    def _on_mode_changed(self, index: int):
        mode_id = self.mode_combo.itemData(index)
        if mode_id:
            self.mode_changed.emit(mode_id)

    def _on_confirm(self):
        if self.current_task:
            for step in self.current_task.get("steps", []):
                if step.get("status") in ("waiting_confirmation", "awaiting_approval"):
                    code = step.get("approval_code")
                    if code:
                        self.confirm_requested.emit(code, step)
                        break

    def _on_cancel(self):
        if self.current_task:
            self.cancel_requested.emit(self.current_task["id"])

    def _on_pause(self):
        if self.current_task:
            self.pause_requested.emit(self.current_task["id"])

    def _on_continue(self):
        if self.current_task:
            self.continue_requested.emit(self.current_task["id"])

    def _on_history_task_selected(self, task_id: str):
        if self.store and self.current_scope:
            task = self.store.get(task_id, self.current_scope)
            if task:
                self._display_task(task)

    def refresh_current_task(self):
        """Atualiza a exibição da tarefa atual."""
        if not self.store or not self.current_scope:
            return
        tasks = self.store.list(self.current_scope, limit=1)
        if tasks:
            self._display_task(tasks[0])
        else:
            self._clear_task_display()

    def _display_task(self, task: dict):
        self.current_task = task
        status = normalize_state(task.get("status", "unknown"))
        mode = get_mode(task.get("mode", ""))

        self.task_title.setText(f"Tarefa {task['id']} ({mode.label})")
        self.task_objective.setText(f"Objetivo: {task.get('objective', '')}")
        self.task_state.setText(status.replace("_", " ").title())
        self.task_state.setStyleSheet(self._state_style(status))

        # Plan
        plan = task.get("plan", [])
        self.plan_widget.set_plan(plan)

        # Steps
        self._update_steps(task.get("steps", []))

        # Update buttons based on state
        self._update_buttons(status)

        # Refresh history
        self.history_widget.refresh()

    def _update_steps(self, steps: list):
        # Clear existing step widgets
        for i in reversed(range(self.steps_layout.count() - 1)):  # -1 to keep stretch
            item = self.steps_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        if not steps:
            self.steps_empty.show()
            return

        self.steps_empty.hide()
        for i, step in enumerate(steps):
            step_widget = StepWidget(step, i)
            self.steps_layout.insertWidget(self.steps_layout.count() - 1, step_widget)

    def _clear_task_display(self):
        self.current_task = None
        self.task_title.setText("Nenhuma tarefa ativa")
        self.task_objective.setText("")
        self.task_state.setText("")
        self.task_state.setStyleSheet("")
        self.plan_widget.set_plan([])
        self._update_steps([])
        self._update_buttons("none")

    def _update_buttons(self, status: str):
        waiting = status in ("waiting_confirmation", "awaiting_approval")
        running = status == "running"
        paused = status == "paused"
        terminal = status in ("completed", "failed", "cancelled")

        self.btn_confirm.setEnabled(waiting)
        self.btn_cancel.setEnabled(not terminal)
        self.btn_pause.setEnabled(running)
        self.btn_continue.setEnabled(paused)

    def _state_style(self, status: str) -> str:
        s = self._scheme
        colors = {
            "created": (s.text_muted, s.bg_tertiary),
            "planning": (s.accent_primary, s.accent_subtle),
            "waiting_confirmation": (s.warning, s.warning_bg),
            "awaiting_approval": (s.warning, s.warning_bg),
            "running": (s.accent_primary, s.accent_subtle),
            "paused": (s.text_muted, s.bg_tertiary),
            "cancelled": (s.error, s.error_bg),
            "failed": (s.error, s.error_bg),
            "completed": (s.success, s.success_bg),
        }
        fg, bg = colors.get(status, (s.text_primary, s.bg_secondary))
        return f"""
            QLabel {{
                background: {bg};
                color: {fg};
                border-radius: {RADIUS.radius_md}px;
                padding: 4px 12px;
                font-size: {TYPOGRAPHY.text_sm}px;
                font-weight: 600;
            }}
        """

    def _refresh_jev_status(self):
        client = get_decision_client()
        health = client.health()
        s = self._scheme

        if health.state == "off":
            self.jev_status.setText("JEV: desativado")
            self.jev_status.setStyleSheet(f"""
                QLabel {{
                    background: {s.bg_tertiary};
                    border: 1px solid {s.border_default};
                    border-radius: {RADIUS.radius_md}px;
                    padding: 4px 12px;
                    color: {s.text_muted};
                    font-size: {TYPOGRAPHY.text_sm}px;
                }}
            """)
        elif health.state == "available":
            self.jev_status.setText("JEV: disponível")
            self.jev_status.setStyleSheet(f"""
                QLabel {{
                    background: {s.success_bg};
                    border: 1px solid {s.success};
                    border-radius: {RADIUS.radius_md}px;
                    padding: 4px 12px;
                    color: {s.success};
                    font-size: {TYPOGRAPHY.text_sm}px;
                    font-weight: 600;
                }}
            """)
        else:
            self.jev_status.setText("JEV: indisponível (fallback)")
            self.jev_status.setStyleSheet(f"""
                QLabel {{
                    background: {s.warning_bg};
                    border: 1px solid {s.warning};
                    border-radius: {RADIUS.radius_md}px;
                    padding: 4px 12px;
                    color: {s.warning};
                    font-size: {TYPOGRAPHY.text_sm}px;
                    font-weight: 600;
                }}
            """)

    def set_scheme(self, scheme):
        """Atualiza o esquema de cores."""
        # Would need to rebuild styles - simplified for now
        pass


# Export
__all__ = ["TaskPanel", "TaskPlanWidget", "TaskHistoryWidget", "StepWidget"]
