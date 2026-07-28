"""Diálogo de ativação e aviso de trial do Celsius."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.license import (
    activate_license,
    check_license_status,
    ensure_trial_started,
)
from ui.theme.schemes import ColorScheme, get_scheme


class ActivationDialog(QDialog):
    """Diálogo principal de ativação e trial."""

    def __init__(self, parent=None, scheme: ColorScheme | None = None):
        super().__init__(parent)
        self._scheme = scheme or get_scheme()
        self._result_status: bool = False
        self.setWindowTitle("Celsius - Ativação")
        self.setFixedSize(520, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._apply_theme()
        self._update_status()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: 12px;
            }}
            QLabel {{
                color: {s.text_primary};
                font-size: 13px;
            }}
            QLineEdit {{
                background-color: {s.bg_primary};
                border: 1px solid {s.border_default};
                border-radius: 8px;
                color: {s.text_primary};
                padding: 10px 14px;
                font-size: 14px;
                font-family: Consolas, 'Courier New', monospace;
                letter-spacing: 2px;
            }}
            QLineEdit:focus {{
                border-color: {s.accent_primary};
            }}
            QPushButton {{
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 24px;
            }}
            QPushButton#btn_ativar {{
                background-color: {s.accent_primary};
                color: {s.accent_text};
            }}
            QPushButton#btn_ativar:hover {{
                background-color: {s.accent_hover};
            }}
            QPushButton#btn_trial {{
                background-color: {s.bg_tertiary};
                color: {s.text_secondary};
                border: 1px solid {s.border_default};
            }}
            QPushButton#btn_trial:hover {{
                background-color: {s.bg_hover};
            }}
            QPushButton#btn_sair {{
                background-color: transparent;
                color: {s.text_muted};
            }}
            QPushButton#btn_sair:hover {{
                color: {s.text_primary};
            }}
            QFrame#separator {{
                background-color: {s.border_default};
                max-height: 1px;
            }}
            QTextEdit {{
                background-color: {s.bg_tertiary};
                border: 1px solid {s.border_default};
                border-radius: 8px;
                color: {s.text_secondary};
                font-size: 11px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(16)

        title = QLabel("Celsius")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {self._scheme.text_primary}; border: none; font-size: 28px;")

        subtitle = QLabel("Agente Multimodal de IA Local")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {self._scheme.text_muted}; border: none; font-size: 12px;")

        self._status_frame = QFrame()
        self._status_frame.setObjectName("separator")

        self._status_icon = QLabel()
        self._status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_icon.setStyleSheet("border: none; font-size: 32px;")

        self._status_label = QLabel()
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("border: none; font-size: 13px;")

        self._input = QLineEdit()
        self._input.setPlaceholderText("Cole sua chave de licença aqui...")
        self._input.setMaxLength(512)

        self._feedback = QLabel()
        self._feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._feedback.setWordWrap(True)
        self._feedback.setStyleSheet("border: none; font-size: 12px;")

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._btn_activate = QPushButton("Ativar Licença", objectName="btn_ativar")
        self._btn_activate.clicked.connect(self._on_activate)

        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_activate)
        btn_layout.addStretch()

        bottom_layout = QHBoxLayout()

        self._btn_trial = QPushButton("Continuar em modo teste", objectName="btn_trial")
        self._btn_trial.clicked.connect(self._on_trial)

        self._btn_exit = QPushButton("Sair", objectName="btn_sair")
        self._btn_exit.clicked.connect(self.reject)

        bottom_layout.addWidget(self._btn_trial)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self._btn_exit)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._status_frame)
        layout.addWidget(self._status_icon)
        layout.addWidget(self._status_label)
        layout.addWidget(self._input)
        layout.addWidget(self._feedback)
        layout.addLayout(btn_layout)
        layout.addStretch()
        layout.addLayout(bottom_layout)

    def _update_status(self):
        status = check_license_status()

        if status["licensed"]:
            self._status_icon.setText("✓")
            self._status_label.setText(
                f"<b style='color: {self._scheme.success}'>Licenciado</b><br>"
                f"<span style='color: {self._scheme.text_secondary}'>"
                f"Cliente: {status.get('customer', '')}<br>"
                f"Válido até: {status.get('expiry', '')}</span>"
            )
            self._input.setVisible(False)
            self._btn_activate.setVisible(False)
            self._btn_trial.setVisible(False)
            self._feedback.setText("")
        elif status["trial"]:
            days = status.get("days_remaining", 0)
            color = self._scheme.warning if days <= 1 else self._scheme.info
            self._status_icon.setText("⏱")
            self._status_label.setText(
                f"<b style='color: {color}'>Modo Teste</b><br>"
                f"<span style='color: {self._scheme.text_secondary}'>"
                f"{days} dia(s) restante(s)</span>"
            )
            self._btn_trial.setVisible(False)
        else:
            self._status_icon.setText("🔒")
            self._status_label.setText(
                f"<b style='color: {self._scheme.error}'>Acesso Bloqueado</b><br>"
                f"<span style='color: {self._scheme.text_secondary}'>"
                f"O período de teste expirou.</span>"
            )
            self._btn_trial.setVisible(False)

    def _on_activate(self):
        key = self._input.text().strip()
        if not key:
            self._feedback.setStyleSheet(
                f"border: none; color: {self._scheme.error}; font-size: 12px;"
            )
            self._feedback.setText("Digite uma chave de licença.")
            return

        success, message = activate_license(key)
        if success:
            self._feedback.setStyleSheet(
                f"border: none; color: {self._scheme.success}; font-size: 12px;"
            )
            self._feedback.setText(message)
            self._result_status = True
            QTimer.singleShot(1500, self.accept)
        else:
            self._feedback.setStyleSheet(
                f"border: none; color: {self._scheme.error}; font-size: 12px;"
            )
            self._feedback.setText(message)

    def _on_trial(self):
        ensure_trial_started()
        self._result_status = True
        self.accept()

    def was_successful(self) -> bool:
        return self._result_status


class TrialWarningBar(QWidget):
    """Barra sutil de aviso de trial exibida na janela principal."""

    def __init__(self, parent=None, scheme: ColorScheme | None = None):
        super().__init__(parent)
        self._scheme = scheme or get_scheme()
        self._setup_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(60000)
        self._refresh()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self._scheme.warning_bg};
                border-bottom: 1px solid {self._scheme.warning};
            }}
            QLabel {{
                color: {self._scheme.warning_text};
                font-size: 11px;
                border: none;
            }}
            QPushButton {{
                background-color: {self._scheme.warning};
                color: {self._scheme.text_on_accent};
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background-color: {self._scheme.warning_text};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(8)

        self._icon = QLabel("⏱")
        self._label = QLabel()
        self._btn = QPushButton("Ativar")
        self._btn.setFixedHeight(24)
        self._btn.clicked.connect(self._on_activate_click)

        layout.addWidget(self._icon)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._btn)

    def _refresh(self):
        status = check_license_status()
        if status["licensed"]:
            self.hide()
            return

        if status["trial"]:
            days = status.get("days_remaining", 0)
            self._label.setText(f"Modo teste — {days} dia(s) restante(s)")
            if days <= 1:
                self._icon.setStyleSheet(f"color: {self._scheme.error}; font-size: 11px;")
                self._label.setStyleSheet(
                    f"color: {self._scheme.error}; font-size: 11px; border: none;"
                )
            else:
                self._icon.setStyleSheet(f"color: {self._scheme.warning}; font-size: 11px;")
                self._label.setStyleSheet(
                    f"color: {self._scheme.warning_text}; font-size: 11px; border: none;"
                )
            self.show()
        else:
            self.hide()

    def _on_activate_click(self):
        parent = self.window()
        dialog = ActivationDialog(parent=parent, scheme=self._scheme)
        dialog.exec()
        self._refresh()
