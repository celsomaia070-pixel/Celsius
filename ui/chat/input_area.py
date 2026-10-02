"""
ModernInputArea - Área de entrada moderna com anexos, microfone, modelo.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.icons import icon
from ui.theme import LIGHT_SCHEME
from ui.theme.tokens import RADIUS, SPACING, TYPOGRAPHY


class ModernInputArea(QWidget):
    """Modern floating input area with attachments, mic, model and mode selectors."""

    send_message = Signal(str)
    attach_file = Signal()
    toggle_mic = Signal()
    toggle_voice = Signal()
    stop_response = Signal()

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or LIGHT_SCHEME
        self._attachments = []  # list of filenames (for backwards compatibility)
        self._attachment_paths = {}  # filename -> filepath
        self._busy = False
        self._setup_ui()

    def _setup_ui(self):
        s = self._scheme
        self.setObjectName("inputArea")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 10, 24, 20)
        main_layout.setSpacing(0)

        # Container with rounded border
        self.container = QWidget()
        self.container.setObjectName("inputContainer")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(
            SPACING.space_3, SPACING.space_3, SPACING.space_3, SPACING.space_3
        )
        container_layout.setSpacing(SPACING.space_2)

        # Attachments row (hidden when empty)
        self.attachments_widget = QWidget()
        self.attachments_layout = QHBoxLayout(self.attachments_widget)
        self.attachments_layout.setContentsMargins(0, 0, 0, 0)
        self.attachments_layout.setSpacing(SPACING.space_2)
        self.attachments_widget.hide()
        container_layout.addWidget(self.attachments_widget)

        # Input row
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(SPACING.space_2)

        # Attach button
        self.btn_attach = QPushButton()
        self.btn_attach.setIcon(icon("paperclip", s.text_muted))
        self.btn_attach.setToolTip("Anexar arquivo (Ctrl+Shift+A)")
        self.btn_attach.setCursor(Qt.PointingHandCursor)
        self.btn_attach.setFixedSize(40, 40)
        self.btn_attach.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
        """)
        self.btn_attach.clicked.connect(self.attach_file.emit)
        input_row.addWidget(self.btn_attach)

        # Text input
        self.input = QLineEdit()
        self.input.setPlaceholderText("Mensagem...")
        self.input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input.setFixedHeight(44)
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {s.text_primary};
                padding: 6px 0px;
                font-size: {TYPOGRAPHY.text_lg}px;
            }}
            QLineEdit::placeholder {{
                color: {s.text_muted};
            }}
        """)
        self.input.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input)

        # Mic button
        self.btn_mic = QPushButton()
        self.btn_mic.setIcon(icon("microphone", s.text_muted))
        self.btn_mic.setToolTip("Ditar mensagem (Ctrl+M)")
        self.btn_mic.setCursor(Qt.PointingHandCursor)
        self.btn_mic.setCheckable(True)
        self.btn_mic.setFixedSize(40, 40)
        self.btn_mic.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
            QPushButton:checked {{
                background: {s.accent_primary}30;
                border: 2px solid {s.accent_primary};
            }}
        """)
        self.btn_mic.clicked.connect(self.toggle_mic.emit)
        input_row.addWidget(self.btn_mic)

# Voice toggle
        self.btn_voice = QPushButton()
        self.btn_voice.setIcon(icon("volume-up", s.text_muted))
        self.btn_voice.setToolTip("Modo voz (Ctrl+Shift+V)")
        self.btn_voice.setCursor(Qt.PointingHandCursor)
        self.btn_voice.setCheckable(True)
        self.btn_voice.setFixedSize(40, 40)
        self.btn_voice.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
            QPushButton:checked {{
                background: {s.accent_primary}20;
            }}
        """)
        self.btn_voice.clicked.connect(self.toggle_voice.emit)
        input_row.addWidget(self.btn_voice)

        self.btn_send = QPushButton()
        self.btn_send.setIcon(icon("paper-plane", s.text_on_accent))
        self.btn_send.setToolTip("Enviar mensagem (Enter)")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setFixedSize(40, 40)
        self.btn_send.setStyleSheet(f"""
            QPushButton {{
                background: {s.accent_primary};
                border: 1px solid {s.accent_primary};
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background: {s.accent_hover};
                border-color: {s.accent_hover};
            }}
            QPushButton:pressed {{
                background: {s.accent_pressed};
                border-color: {s.accent_pressed};
            }}
        """)
        self.btn_send.clicked.connect(self._on_send)
        input_row.addWidget(self.btn_send)

        self.btn_stop = QPushButton()
        self.btn_stop.setIcon(icon("stop", s.text_on_accent))
        self.btn_stop.setToolTip("Interromper resposta (Esc)")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setFixedSize(40, 40)
        self.btn_stop.setStyleSheet(f"""
            QPushButton {{
                background: {s.error};
                border: 1px solid {s.error};
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background: {s.error_bg};
                border-color: {s.error};
            }}
        """)
        self.btn_stop.clicked.connect(self.stop_response.emit)
        self.btn_stop.hide()
        input_row.addWidget(self.btn_stop)

        container_layout.addLayout(input_row)

        main_layout.addWidget(self.container)

        self.setStyleSheet(f"""
            #inputArea {{
                background: {s.bg_primary};
                border: none;
            }}
            #inputContainer {{
                background: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_lg}px;
            }}
        """)

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+Shift+A"), self, activated=self.attach_file.emit)
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self.toggle_mic.emit)
        QShortcut(QKeySequence("Ctrl+Shift+V"), self, activated=self._toggle_voice_shortcut)
        stop_shortcut = QShortcut(QKeySequence("Esc"), self, activated=self._on_stop)
        stop_shortcut.setContext(Qt.WidgetWithChildrenShortcut)

    def _toggle_voice_shortcut(self):
        self.btn_voice.setChecked(not self.btn_voice.isChecked())
        self.toggle_voice.emit()


    def _on_stop(self):
        self.stop_response.emit()

    def _on_send(self):
        if self._busy:
            return
        text = self.input.text().strip()
        if text:
            self.send_message.emit(text)
            self.input.clear()

    def add_attachment(self, file_path: str, file_name: str = None):
        from pathlib import Path

        name = file_name or Path(file_path).name
        chip = QLabel(f"arquivo: {name}")
        chip.setStyleSheet(f"""
            background: {self._scheme.accent_primary}15;
            border: 1px solid {self._scheme.accent_primary}40;
            border-radius: {RADIUS.radius_sm}px;
            padding: {SPACING.space_1}px {SPACING.space_3}px;
            color: {self._scheme.accent_primary};
            font-size: {TYPOGRAPHY.text_xs}px;
        """)
        self._attachments.append(name)
        self._attachment_paths[name] = file_path
        self.attachments_layout.addWidget(chip)
        self.attachments_widget.show()

    def clear_attachments(self):
        for i in reversed(range(self.attachments_layout.count())):
            widget = self.attachments_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self._attachments.clear()
        self._attachment_paths.clear()
        self.attachments_widget.hide()

    def _remove_attachment(self, file_name: str):
        """Remove attachment by filename (for backwards compatibility with tests)."""
        if file_name in self._attachments:
            idx = self._attachments.index(file_name)
            self._attachments.pop(idx)
            self._attachment_paths.pop(file_name, None)
            # Remove corresponding widget
            item = self.attachments_layout.itemAt(idx)
            if item and item.widget():
                item.widget().deleteLater()
                self.attachments_layout.takeAt(idx)
            if not self._attachments:
                self.attachments_widget.hide()

    def get_attachments(self):
        """Return list of (filepath, filename) tuples for sending to AI."""
        return [(self._attachment_paths[name], name) for name in self._attachments]

    def set_mic_active(self, active: bool):
        """Set mic button active state (recording or not)."""
        self.btn_mic.setChecked(active)
        if active:
            self.btn_mic.setToolTip("Gravando... Clique para parar (Ctrl+M)")
            self.btn_mic.setIcon(icon("microphone-off", self._scheme.accent_primary))
        else:
            self.btn_mic.setToolTip("Ditar mensagem (Ctrl+M)")
            self.btn_mic.setIcon(icon("microphone", self._scheme.text_muted))

    def set_busy(self, busy: bool):
        """Set busy state: disables input, shows stop button, hides send button."""
        self._busy = busy
        self.btn_send.setVisible(not busy)
        self.btn_stop.setVisible(busy)
        self.input.setEnabled(not busy)


    def set_scheme(self, scheme):
        self._scheme = scheme
        s = scheme
        self.setStyleSheet(f"""
            #inputArea {{
                background: {s.bg_primary};
                border: none;
            }}
            #inputContainer {{
                background: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_lg}px;
            }}
        """)
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {s.text_primary};
                padding: 6px 0px;
                font-size: {TYPOGRAPHY.text_lg}px;
            }}
            QLineEdit::placeholder {{
                color: {s.text_muted};
            }}
        """)
        self.btn_attach.setIcon(icon("paperclip", s.text_muted))
        self.btn_attach.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
        """)
        self.btn_mic.setIcon(icon("microphone", s.text_muted))
        self.btn_mic.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
            QPushButton:checked {{
                background: {s.accent_subtle};
                border: 1px solid {s.accent_primary};
            }}
        """)
        self.btn_voice.setIcon(icon("volume-up", s.text_muted))
        self.btn_voice.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
            QPushButton:checked {{
                background: {s.accent_primary}20;
            }}
        """)
        self.btn_send.setIcon(icon("paper-plane", s.text_on_accent))
        self.btn_send.setStyleSheet(f"""
            QPushButton {{
                background: {s.accent_primary};
                border: 1px solid {s.accent_primary};
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background: {s.accent_hover};
                border-color: {s.accent_hover};
            }}
            QPushButton:pressed {{
                background: {s.accent_pressed};
                border-color: {s.accent_pressed};
            }}
        """)
