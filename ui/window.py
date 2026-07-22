import json
import os
import re
from datetime import datetime
from uuid import uuid4

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import get_settings
from core.memory import get_memory_service
from processors import processar_arquivo
from ui.command_palette import CommandPaletteManager
from ui.icons import icon
from ui.sidebar import Sidebar
from ui.theme import DARK_SCHEME, LIGHT_SCHEME, ThemeMode, get_stylesheet
from workers.ai_worker import WorkerManager


class MessageBubble(QWidget):
    """Clean message with label - no bubble, text directly on page."""

    def __init__(
        self,
        content: str,
        is_user: bool = False,
        is_streaming: bool = False,
        attachments: list = None,
        scheme=None,
        parent=None
    ):
        super().__init__(parent)
        self.content = content
        self.is_user = is_user
        self.is_streaming = is_streaming
        self.attachments = attachments or []
        self._full_content = content
        self._scheme = scheme or LIGHT_SCHEME
        self._setup_ui()
        self._render_content()
        self._fade_in()
        self._cursor_visible = True
        self._cursor_timer = QTimer()
        self._cursor_timer.setInterval(530)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        if self.is_streaming:
            self._cursor_timer.start()

    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.update_content(self._full_content)

    def _setup_ui(self):
        s = self._scheme

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 4, 0, 4)
        main_layout.setSpacing(4)

        # Container for alignment - expands full width
        self.container = QWidget()
        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        if self.is_user:
            container_layout.addStretch()
            self.message_widget = QWidget()
            msg_layout = QVBoxLayout(self.message_widget)
            msg_layout.setContentsMargins(8, 0, 8, 0)
            msg_layout.setSpacing(4)
        else:
            self.message_widget = QWidget()
            msg_layout = QVBoxLayout(self.message_widget)
            msg_layout.setContentsMargins(8, 0, 8, 0)
            msg_layout.setSpacing(4)

        # Label: "Voce" or "Celsius"
        self.name_label = QLabel("Voce" if self.is_user else "Celsius")
        self.name_label.setStyleSheet(f"color: {s.text_primary}; font-size: 14px; font-weight: 700; background: transparent; border: none;")
        if not self.is_user and self.is_streaming:
            self.name_label.hide()
        msg_layout.addWidget(self.name_label)

        # Attachments
        if self.attachments:
            self._add_attachments(msg_layout)

        # Text content
        self.content_label = QTextEdit()
        self.content_label.setReadOnly(True)
        self.content_label.setFocusPolicy(Qt.StrongFocus)
        self.content_label.setFrameStyle(0)
        self.content_label.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.content_label.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                color: {s.text_primary};
                font-size: 15px;
                selection-background-color: {s.accent_primary}40;
            }}
        """)
        self.content_label.document().contentsChanged.connect(self._adjust_height)
        msg_layout.addWidget(self.content_label)

        # Actions for assistant - on hover
        if not self.is_user:
            self.actions_widget = self._create_actions()
            msg_layout.addWidget(self.actions_widget)
            self.actions_widget.hide()
            self.setMouseTracking(True)
            self.content_label.enterEvent = lambda e: self._show_actions()
            self.content_label.leaveEvent = lambda e: self._hide_actions()

        # Add message_widget
        if self.is_user:
            container_layout.addWidget(self.message_widget, 0)
        else:
            container_layout.addWidget(self.message_widget, 1)

        main_layout.addWidget(self.container)

        # Ensure message widget expands properly
        if self.is_user:
            self.message_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        else:
            self.message_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def _add_attachments(self, layout):
        from PySide6.QtWidgets import QHBoxLayout
        s = self._scheme
        attach_layout = QHBoxLayout()
        attach_layout.setSpacing(8)
        attach_layout.setContentsMargins(0, 0, 0, 0)
        for att in self.attachments:
            chip = QLabel(f"arquivo: {att}")
            chip.setStyleSheet(f"""
                background: {s.accent_primary}15;
                border: 1px solid {s.accent_primary}40;
                border-radius: 6px;
                padding: 4px 10px;
                color: {s.accent_primary};
                font-size: 12px;
            """)
            attach_layout.addWidget(chip)
        attach_layout.addStretch()
        layout.addLayout(attach_layout)

    def _create_actions(self):
        s = self._scheme
        widget = QWidget()
        widget.setFixedHeight(28)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(4)
        layout.addStretch()

        btn = QPushButton()
        btn.setIcon(icon("copy", s.text_muted))
        btn.setToolTip("Copiar mensagem (Ctrl+C)")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(26, 26)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 4px; padding: 3px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
        """)
        btn.clicked.connect(self._copy_content)
        layout.addWidget(btn)
        return widget

    def _copy_content(self):
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.content_label.toPlainText())

    def _show_actions(self):
        if hasattr(self, 'actions_widget'):
            self.actions_widget.show()

    def _hide_actions(self):
        if hasattr(self, 'actions_widget'):
            self.actions_widget.hide()

    def _render_content(self):
        html = self._markdown_to_html(self.content)
        self.content_label.setHtml(html)
        self._adjust_height()

    def _markdown_to_html(self, text: str) -> str:
        s = self._scheme
        tp = s.text_primary

        # Escape HTML
        text = text.replace("&", "&").replace("<", "<").replace(">", ">")

        # Code blocks
        text = re.sub(r'```(\w*)\n(.*?)```', lambda m: (
            f'<div style="background:{s.code_bg}; border:1px solid {s.code_border}; border-radius:8px; padding:12px; margin:8px 0; font-family:Consolas,monospace; font-size:13px; color:{s.code_text};">'
            f'<pre style="margin:0; white-space:pre-wrap;">{m.group(2)}</pre></div>'
        ), text, flags=re.DOTALL)

        # Inline code
        text = re.sub(r'`([^`]+)`',
            f'<code style="background:{s.code_bg}; border:1px solid {s.code_border}; border-radius:4px; padding:2px 6px; font-family:Consolas,monospace; font-size:13px; color:{s.accent_primary};">\\1</code>', text)

        # Bold/italic
        text = re.sub(r'\*\*(.+?)\*\*', f'<b style="color:{tp};">\\1</b>', text)
        text = re.sub(r'\*(.+?)\*', f'<i style="color:{s.text_secondary};">\\1</i>', text)

        # Headers
        text = re.sub(r'^### (.+)$', f'<h4 style="color:{tp}; margin:12px 0 4px 0; font-size:15px;">\\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', f'<h3 style="color:{tp}; margin:14px 0 6px 0; font-size:16px;">\\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', f'<h2 style="color:{tp}; margin:16px 0 8px 0; font-size:18px;">\\1</h2>', text, flags=re.MULTILINE)

        # Lists
        def process_list(match):
            items = match.group(0).strip().split("\n")
            html = f'<ul style="margin:6px 0; padding-left:20px; color:{tp};">'
            for item in items:
                item = re.sub(r'^[-*]\s+', '', item.strip())
                if item:
                    html += f'<li style="margin:3px 0; color:{tp};">{item}</li>'
            html += '</ul>'
            return html

        text = re.sub(r'(?:^[-*] .+\n?)+', process_list, text, flags=re.MULTILINE)

        # Numbered lists
        def process_num_list(match):
            items = match.group(0).strip().split("\n")
            html = f'<ol style="margin:6px 0; padding-left:20px; color:{tp};">'
            for item in items:
                item = re.sub(r'^\d+\.\s+', '', item.strip())
                if item:
                    html += f'<li style="margin:3px 0; color:{tp};">{item}</li>'
            html += '</ol>'
            return html

        text = re.sub(r'(?:^\d+\. .+\n?)+', process_num_list, text, flags=re.MULTILINE)

        # Tables
        def process_table(match):
            lines = match.group(0).strip().split("\n")
            rows = [l for l in lines if l.strip() and not re.match(r'^\|[-:|]+\|$', l.strip())]
            if len(rows) < 2:
                return match.group(0)
            html = '<table style="border-collapse:collapse; width:100%; margin:10px 0; font-size:13px;">'
            for i, row in enumerate(rows):
                cells = [c.strip() for c in row.strip("|").split("|")]
                tag = "th" if i == 0 else "td"
                style = f"border:1px solid {s.code_border}; padding:8px 12px; text-align:left;"
                if i == 0:
                    style += f" background:{s.code_bg}; color:{tp}; font-weight:600;"
                else:
                    style += f" color:{tp};"
                html += "<tr>"
                for cell in cells:
                    html += f'<{tag} style="{style}">{cell}</{tag}>'
                html += "</tr>"
            html += "</table>"
            return html

        text = re.sub(r'(?:^\|.+\|\n?)+', process_table, text, flags=re.MULTILINE)

        # Newlines
        text = re.sub(r'\n\n+', '<br><br>', text)
        text = re.sub(r'\n', '<br>', text)

        return text

    def _adjust_height(self):
        doc = self.content_label.document()
        # Use the content_label's width, fallback to parent widget width
        w = self.content_label.width()
        if w <= 0:
            w = self.message_widget.width()
        if w <= 0:
            w = self.container.width()
        if w <= 0:
            w = 600  # fallback
        doc.setTextWidth(w)
        h = int(doc.size().height()) + 8
        self.content_label.setMinimumHeight(h)

    def _fade_in(self):
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._fade_anim = QPropertyAnimation(effect, b"opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

    def update_content(self, content: str):
        self.content = content
        self._full_content = content
        display = content
        if self.is_streaming and self._cursor_visible:
            display += "▌"
        self.content_label.setHtml(self._markdown_to_html(display))
        self._adjust_height()

    def finish_streaming(self):
        self.is_streaming = False
        self._cursor_timer.stop()
        if hasattr(self, 'name_label'):
            self.name_label.show()
        self.update_content(self._full_content)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Reflow text when bubble resizes
        self._adjust_height()


class ModernChatView(QWidget):
    """Modern chat view with message bubbles and streaming support."""

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or LIGHT_SCHEME
        self.messages = []
        self._streaming_bubble = None
        self._streaming_content = ""
        self._auto_scroll = True
        self._user_scrolled_up = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
        """)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 20, 0, 20)
        self.content_layout.setSpacing(4)
        self.content_layout.addStretch()

        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area)

        # Track scroll position for auto-scroll
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _on_scroll(self, value):
        bar = self.scroll_area.verticalScrollBar()
        at_bottom = value >= bar.maximum() - 50
        self._auto_scroll = at_bottom
        self._user_scrolled_up = not at_bottom

    def add_user_message(self, content: str, attachments: list = None):
        bubble = MessageBubble(content, is_user=True, attachments=attachments, scheme=self._scheme)
        self.content_layout.insertWidget(self.content_layout.count() - 1, bubble)
        self.messages.append(("user", content))
        if self._auto_scroll:
            self._scroll_to_bottom()

    def add_assistant_message(self, content: str) -> MessageBubble:
        bubble = MessageBubble(content, is_user=False, scheme=self._scheme)
        self.content_layout.insertWidget(self.content_layout.count() - 1, bubble)
        self.messages.append(("assistant", content))
        if self._auto_scroll:
            self._scroll_to_bottom()
        return bubble

    def start_streaming(self) -> MessageBubble:
        self.hide_thinking()
        bubble = MessageBubble("", is_user=False, is_streaming=True, scheme=self._scheme)
        self.content_layout.insertWidget(self.content_layout.count() - 1, bubble)
        self._streaming_bubble = bubble
        self._streaming_content = ""
        return bubble

    def append_streaming(self, token: str):
        if self._streaming_bubble:
            try:
                self._streaming_content += token
                self._streaming_bubble.update_content(self._streaming_content)
                if self._auto_scroll:
                    self._scroll_to_bottom()
            except RuntimeError:
                # Widget was deleted
                self._streaming_bubble = None
                self._streaming_content = ""

    def finish_streaming(self):
        if self._streaming_bubble:
            try:
                self._streaming_bubble.finish_streaming()
                self.messages.append(("assistant", self._streaming_content))
                self._streaming_bubble = None
                self._streaming_content = ""
            except RuntimeError:
                self._streaming_bubble = None
                self._streaming_content = ""

    def _scroll_to_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def clear(self):
        for i in reversed(range(self.content_layout.count() - 1)):
            widget = self.content_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.messages.clear()

    def show_thinking(self, text: str):
        self.hide_thinking()
        # Remove the bottom stretch
        self._saved_stretch = self.content_layout.takeAt(self.content_layout.count() - 1)
        # Add stretch before thinking to push it to center
        self.content_layout.addStretch()
        # Thinking widget
        self._thinking_widget = QWidget()
        vl = QVBoxLayout(self._thinking_widget)
        vl.setContentsMargins(8, 4, 8, 4)
        vl.setSpacing(2)
        self._thinking_label = QLabel(text)
        self._thinking_label.setStyleSheet("color: #6E6E73; font-size: 14px; font-style: italic; background: transparent; border: none;")
        vl.addWidget(self._thinking_label)
        self.content_layout.addWidget(self._thinking_widget)
        # Add stretch after thinking
        self.content_layout.addStretch()
        self._scroll_to_bottom()

    def update_thinking(self, text: str):
        if hasattr(self, '_thinking_label') and self._thinking_label:
            self._thinking_label.setText(text)

    def hide_thinking(self):
        if hasattr(self, '_thinking_widget') and self._thinking_widget:
            # Remove thinking widget and its surrounding stretches
            for i in range(self.content_layout.count() - 1, -1, -1):
                item = self.content_layout.itemAt(i)
                if item and item.widget() == self._thinking_widget:
                    self.content_layout.takeAt(i)
                    self._thinking_widget.deleteLater()
                    self._thinking_widget = None
                    self._thinking_label = None
                    # Remove stretch after
                    if i < self.content_layout.count():
                        after = self.content_layout.itemAt(i)
                        if after and after.spacerItem():
                            self.content_layout.takeAt(i)
                    # Remove stretch before
                    if i > 0:
                        before = self.content_layout.itemAt(i - 1)
                        if before and before.spacerItem():
                            self.content_layout.takeAt(i - 1)
                    break
            # Restore the bottom stretch
            if hasattr(self, '_saved_stretch') and self._saved_stretch:
                self.content_layout.addItem(self._saved_stretch)
                self._saved_stretch = None

    def set_scheme(self, scheme):
        self._scheme = scheme


class ModernInputArea(QWidget):
    """Modern floating input area with attachments, mic, model selector."""

    send_message = Signal(str)
    attach_file = Signal()
    toggle_mic = Signal()
    toggle_voice = Signal()
    change_model = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._attachments = []
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("inputContainer")
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        # Attachment button
        self.btn_attach = QPushButton()
        self.btn_attach.setIcon(icon("paperclip", "#9E9EA3"))
        self.btn_attach.setToolTip("Anexar arquivo")
        self.btn_attach.setCursor(Qt.PointingHandCursor)
        self.btn_attach.setFixedSize(40, 40)
        self.btn_attach.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                padding: 8px;
            }
            QPushButton:hover {
                background: #F0F0F1;
            }
        """)
        self.btn_attach.clicked.connect(self.attach_file.emit)
        layout.addWidget(self.btn_attach)

        # Attachments preview
        self.attachments_widget = QWidget()
        self.attachments_layout = QHBoxLayout(self.attachments_widget)
        self.attachments_layout.setContentsMargins(0, 0, 0, 0)
        self.attachments_layout.setSpacing(6)
        self.attachments_widget.hide()
        layout.addWidget(self.attachments_widget)

        # Input
        self.input = QLineEdit()
        self.input.setPlaceholderText("Pergunte ao Celsius...")
        self.input.setFont(QFont("Segoe UI", 14))
        self.input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #1A1A1B;
                padding: 6px 0px;
                font-size: 14px;
            }
            QLineEdit::placeholder {
                color: #9E9EA3;
            }
        """)
        self.input.returnPressed.connect(self._on_send)
        layout.addWidget(self.input, 1)

        # Mic button
        self.btn_mic = QPushButton()
        self.btn_mic.setIcon(icon("microphone", "#9E9EA3"))
        self.btn_mic.setToolTip("Gravar áudio")
        self.btn_mic.setCursor(Qt.PointingHandCursor)
        self.btn_mic.setFixedSize(40, 40)
        self.btn_mic.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                padding: 8px;
            }
            QPushButton:hover {
                background: #F0F0F1;
            }
        """)
        self.btn_mic.clicked.connect(self.toggle_mic.emit)
        layout.addWidget(self.btn_mic)

        # Voice toggle button
        self.btn_voice = QPushButton()
        self.btn_voice.setIcon(icon("volume-up", "#9E9EA3"))
        self.btn_voice.setToolTip("Leitura em voz alta")
        self.btn_voice.setCursor(Qt.PointingHandCursor)
        self.btn_voice.setFixedSize(40, 40)
        self.btn_voice.setCheckable(True)
        self.btn_voice.setChecked(True)
        self.btn_voice.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                padding: 8px;
            }
            QPushButton:hover {
                background: #F0F0F1;
            }
            QPushButton:checked {
                background: #00000015;
            }
        """)
        self.btn_voice.clicked.connect(self.toggle_voice.emit)
        layout.addWidget(self.btn_voice)

        # Send button
        self.btn_send = QPushButton()
        self.btn_send.setIcon(icon("paper-plane", "#FFFFFF"))
        self.btn_send.setToolTip("Enviar (Enter)")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setFixedSize(40, 40)
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: #000000;
                border: none;
                border-radius: 10px;
                padding: 8px;
            }
            QPushButton:hover {
                background: #1A1A1A;
            }
        """)
        self.btn_send.clicked.connect(self._on_send)
        layout.addWidget(self.btn_send)

        # Model selector (compact)
        self.model_combo = QComboBox()
        self.model_combo.setFixedWidth(220)
        self.model_combo.setStyleSheet("""
            QComboBox {
                background: #F7F7F8;
                border: 1px solid #E5E5E7;
                border-radius: 8px;
                color: #6E6E73;
                font-size: 11px;
                padding: 6px 10px;
                padding-right: 28px;
            }
            QComboBox:hover {
                background: #F0F0F1;
                color: #1A1A1B;
                border-color: #D1D1D6;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #FFFFFF;
                border: 1px solid #E5E5E7;
                color: #1A1A1B;
                selection-background-color: #00000030;
                outline: none;
            }
        """)
        layout.addWidget(self.model_combo)

        # Load models from GGUF registry
        from core.config import GGUF_MODELS
        from core.model_downloader import is_model_downloaded
        self._combo_models = GGUF_MODELS
        current_id = get_settings().llm_model
        for i, model in enumerate(GGUF_MODELS):
            status = "✓" if is_model_downloaded(model.id) else "↓"
            self.model_combo.addItem(f"{status} {model.name} ({model.quant})", model.id)
        idx = next((i for i, m in enumerate(GGUF_MODELS) if m.id == current_id), 0)
        self.model_combo.setCurrentIndex(idx)
        self.model_combo.currentIndexChanged.connect(
            lambda: self.change_model.emit(self.model_combo.currentData())
        )

    def _on_send(self):
        text = self.input.text().strip()
        if text or self._attachments:
            self.send_message.emit(text)
            self.input.clear()

    def add_attachment(self, name: str):
        self._attachments.append(name)
        chip = QLabel(f"📎 {name}")
        chip.setStyleSheet("""
            background: #00000030;
            border: 1px solid #000000;
            border-radius: 6px;
            padding: 4px 10px;
            color: #000000;
            font-size: 11px;
        """)
        # Add remove button
        from PySide6.QtWidgets import QHBoxLayout
        chip_layout = QHBoxLayout()
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setSpacing(4)

        label = QLabel(f"📎 {name}")
        label.setStyleSheet("color: #000000; font-size: 11px;")
        chip_layout.addWidget(label)

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #9E9EA3;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #D32F2F;
            }
        """)
        remove_btn.clicked.connect(lambda: self._remove_attachment(name))
        chip_layout.addWidget(remove_btn)

        container = QWidget()
        container.setLayout(chip_layout)
        container.setStyleSheet("""
            background: #00000030;
            border: 1px solid #000000;
            border-radius: 6px;
            padding: 2px 8px;
        """)
        self.attachments_layout.addWidget(container)
        self.attachments_widget.show()

    def _remove_attachment(self, name: str):
        self._attachments = [a for a in self._attachments if a != name]
        self._update_attachments_ui()

    def clear_attachments(self):
        self._attachments.clear()
        self._update_attachments_ui()

    def _update_attachments_ui(self):
        # Clear existing
        while self.attachments_layout.count():
            item = self.attachments_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._attachments:
            for name in self._attachments:
                chip = QWidget()
                chip_layout = QHBoxLayout(chip)
                chip_layout.setContentsMargins(8, 4, 8, 4)
                chip_layout.setSpacing(4)

                label = QLabel(f"📎 {name}")
                label.setStyleSheet("color: #000000; font-size: 11px;")
                chip_layout.addWidget(label)

                remove_btn = QPushButton("×")
                remove_btn.setFixedSize(16, 16)
                remove_btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: none;
                        color: #9E9EA3;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        color: #D32F2F;
                    }
                """)
                remove_btn.clicked.connect(lambda _, n=name: self._remove_attachment(n))
                chip_layout.addWidget(remove_btn)

                chip.setStyleSheet("""
                    background: #00000030;
                    border: 1px solid #000000;
                    border-radius: 6px;
                    padding: 2px 8px;
                """)
                self.attachments_layout.addWidget(chip)
            self.attachments_widget.show()
        else:
            self.attachments_widget.hide()

    def get_attachments(self):
        return self._attachments.copy()


class ModernChatWindow(QMainWindow):
    """Main window with sidebar and chat area."""

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.memory_service = get_memory_service()
        self.worker_manager = WorkerManager()

        self._theme_mode = ThemeMode.LIGHT
        self._current_conv_id = None
        self._conversations = {}
        self._mic_worker = None
        self._voz_worker = None
        self._pending_doc_text = ""
        self._pending_doc_name = ""
        self._pending_image_path = ""
        self._pending_file_path = ""
        self._memories_enabled = True

        # Thinking animation
        self._thinking_timer = QTimer()
        self._thinking_timer.setInterval(400)
        self._thinking_timer.timeout.connect(self._animate_thinking)
        self._thinking_base_text = ""
        self._thinking_dots = 0

        self.setWindowTitle("Celsius")
        self.resize(1100, 700)
        self._setup_ui()
        self._apply_theme()
        self._load_conversations()

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
        self.hamburger_btn.setIcon(icon("bars", "#6E6E73"))
        self.hamburger_btn.setToolTip("Mostrar/esconder sidebar")
        self.hamburger_btn.setFixedSize(36, 36)
        self.hamburger_btn.setCursor(Qt.PointingHandCursor)
        self.hamburger_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; border-radius: 8px; padding: 6px;
            }
            QPushButton:hover { background: #F0F0F1; }
        """)
        self.hamburger_btn.clicked.connect(self._toggle_sidebar)
        top_bar_layout.addWidget(self.hamburger_btn)

        # Logo centered
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        logo_path = os.path.join(self.settings.base_dir, "logo", "logo.png")
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            self.logo_label.setPixmap(pixmap.scaledToHeight(80, Qt.SmoothTransformation))
        top_bar_layout.addWidget(self.logo_label, 1)

        top_bar_layout.addStretch()

        main_layout.addWidget(self._top_bar)

        # Chat view
        self.chat_view = ModernChatView(scheme=LIGHT_SCHEME)
        main_layout.addWidget(self.chat_view, 1)

        # Input area
        self.input_area = ModernInputArea()
        self.input_area.send_message.connect(self._on_send_message)
        self.input_area.attach_file.connect(self._attach_file)
        self.input_area.toggle_mic.connect(self._toggle_microphone)
        self.input_area.toggle_voice.connect(self._toggle_voice)
        self.input_area.change_model.connect(self._change_model)
        main_layout.addWidget(self.input_area)

        root_layout.addWidget(content_widget, 1)

    def _apply_theme(self):
        scheme = DARK_SCHEME if self._theme_mode == ThemeMode.DARK else LIGHT_SCHEME
        self.setStyleSheet(get_stylesheet(scheme))

        self._top_bar.setStyleSheet(f"""
            background: {scheme.bg_primary};
        """)

        self.chat_view.set_scheme(scheme)
        self.sidebar.set_scheme(scheme)

    def _animate_thinking(self):
        """Animate thinking dots: . -> .. -> ... -> ."""
        self._thinking_dots = (self._thinking_dots % 3) + 1
        dots = "." * self._thinking_dots
        self.chat_view.update_thinking(f"{self._thinking_base_text}{dots}")

    def _start_thinking(self, base_text: str):
        """Start thinking animation with base text."""
        self._thinking_base_text = base_text
        self._thinking_dots = 0
        self.chat_view.show_thinking(f"{base_text}.")
        self._thinking_timer.start()

    def _stop_thinking(self):
        """Stop thinking animation."""
        self._thinking_timer.stop()
        self.chat_view.hide_thinking()

    def _toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def _register_shortcuts(self):
        # Command palette (Ctrl+K is registered in CommandPaletteManager.__init__)
        # New chat
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new_conversation)
        # Clear chat
        QShortcut(QKeySequence("Ctrl+Shift+Delete"), self, activated=self.chat_view.clear)
        # Toggle theme
        QShortcut(QKeySequence("Ctrl+Shift+L"), self, activated=self._toggle_theme)
        # Settings
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._show_settings)

    def _handle_palette_action(self, action_id: str):
        handlers = {
            "new_chat": self._new_conversation,
            "clear_chat": self.chat_view.clear,
            "toggle_theme": self._toggle_theme,
            "settings": self._show_settings,
            "change_model": lambda: self.input_area.model_combo.showPopup(),
            "voice_toggle": self._toggle_voice,
            "generate_report": self._generate_report,
        }
        if action_id in handlers:
            handlers[action_id]()

    def _new_conversation(self):
        conv_id = str(uuid4())
        title = f"Conversa {len(self._conversations) + 1}"
        self._create_conversation(conv_id, title)
        self.sidebar.add_conversation(conv_id, title)
        self.sidebar.set_current_conversation(conv_id)
        self._save_conversations()

    def _create_conversation(self, conv_id: str, title: str):
        self._current_conv_id = conv_id
        self._conversations[conv_id] = {
            "title": title,
            "messages": [],
            "created": datetime.now().isoformat(),
        }
        self.chat_view.clear()
        self.input_area.clear_attachments()

    def _switch_conversation(self, conv_id: str):
        if conv_id == self._current_conv_id:
            return
        if conv_id not in self._conversations:
            return
        self._current_conv_id = conv_id
        conv = self._conversations[conv_id]
        self.chat_view.clear()
        for role, content in conv.get("messages", []):
            if role == "user":
                self.chat_view.add_user_message(content)
            elif role == "assistant":
                self.chat_view.add_assistant_message(content)
        self.sidebar.set_current_conversation(conv_id)

    def _delete_conversation(self, conv_id: str):
        if conv_id in self._conversations:
            del self._conversations[conv_id]
        self.sidebar.remove_conversation(conv_id)
        if conv_id == self._current_conv_id:
            if self._conversations:
                cid = next(iter(self._conversations))
                self._switch_conversation(cid)
            else:
                self._new_conversation()
        self._save_conversations()

    def _rename_conversation(self, conv_id: str, new_title: str):
        if conv_id in self._conversations:
            self._conversations[conv_id]["title"] = new_title
        self.sidebar.update_conversation(conv_id, new_title)
        self._save_conversations()

    def _on_toggle_memories(self, enabled: bool):
        self._memories_enabled = enabled

    def _show_memories_dialog(self):
        from PySide6.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("Memorias do Usuario")
        dialog.setMinimumSize(500, 450)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title
        title = QLabel("Memorias salvas")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        # Memories list
        self._mem_list = QListWidget()
        self._mem_list.setStyleSheet("""
            QListWidget {
                background: #F5F5F7;
                border: 1px solid #E5E5EA;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                background: white;
                border: 1px solid #E5E5EA;
                border-radius: 6px;
                padding: 8px 12px;
                margin: 2px 0;
            }
            QListWidget::item:selected {
                background: #E8E8ED;
            }
        """)

        # Load memories
        memories = self.memory_service.get_all()
        for mem in memories:
            texto = mem.get("texto", "") if isinstance(mem, dict) else str(mem)
            data = mem.get("data", "") if isinstance(mem, dict) else ""
            item = QListWidgetItem(f"{texto}" + (f"  ({data})" if data else ""))
            item.setData(Qt.UserRole, texto)
            self._mem_list.addItem(item)

        layout.addWidget(self._mem_list, 1)

        # Add memory section
        add_label = QLabel("Adicionar nova memoria:")
        add_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(add_label)

        self._mem_input = QTextEdit()
        self._mem_input.setPlaceholderText("Digite uma informacao para o Celsius lembrar...")
        self._mem_input.setMaximumHeight(80)
        self._mem_input.setStyleSheet("""
            QTextEdit {
                background: white;
                border: 1px solid #E5E5EA;
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self._mem_input)

        # Buttons row
        btn_row = QHBoxLayout()

        btn_add = QPushButton("Salvar Memoria")
        btn_add.setIcon(icon("save", "#FFFFFF"))
        btn_add.setStyleSheet("""
            QPushButton {
                background: #000000;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background: #1A1A1A; }
        """)
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(lambda: self._add_memory_from_dialog())
        btn_row.addWidget(btn_add)

        btn_delete = QPushButton("Excluir Selecionada")
        btn_delete.setIcon(icon("trash", "#FF3B30"))
        btn_delete.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FF3B30;
                border: 1px solid #FF3B30;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background: #FDEDEC; }
        """)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.clicked.connect(lambda: self._delete_memory_from_dialog())
        btn_row.addWidget(btn_delete)

        btn_clear_all = QPushButton("Limpar Todas")
        btn_clear_all.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8E8E93;
                border: 1px solid #E5E5EA;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background: #F5F5F7; }
        """)
        btn_clear_all.setCursor(Qt.PointingHandCursor)
        btn_clear_all.clicked.connect(lambda: self._clear_all_memories_from_dialog())
        btn_row.addWidget(btn_clear_all)

        layout.addLayout(btn_row)

        # Close button
        close_btn = QPushButton("Fechar")
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #E5E5EA;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background: #F5F5F7; }
        """)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        self._mem_dialog = dialog
        dialog.exec()

    def _add_memory_from_dialog(self):
        texto = self._mem_input.toPlainText().strip()
        if not texto:
            return
        self.memory_service.add(texto)
        self._mem_input.clear()
        # Refresh list
        item = QListWidgetItem(texto)
        item.setData(Qt.UserRole, texto)
        self._mem_list.addItem(item)
        self.chat_view.add_assistant_message(f"Memoria salva: **{texto}**")

    def _delete_memory_from_dialog(self):
        item = self._mem_list.currentItem()
        if not item:
            return
        texto = item.data(Qt.UserRole)
        row = self._mem_list.row(item)
        self._mem_list.takeItem(row)
        # Remove from service
        memories = self.memory_service.get_all()
        memories = [m for m in memories if m.get("texto", "") != texto]
        from core.memory import salvar_memorias
        salvar_memorias(memories)

    def _clear_all_memories_from_dialog(self):
        self.memory_service.clear()
        self._mem_list.clear()
        self.chat_view.add_assistant_message("Todas as memorias foram limpas.")

    def _save_conversations(self):
        try:
            data = {}
            for cid, conv in self._conversations.items():
                created = conv["created"]
                if isinstance(created, datetime):
                    created = created.isoformat()
                data[cid] = {
                    "title": conv["title"],
                    "messages": conv["messages"],
                    "created": created,
                }
            path = self.settings.chats_file
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Celsius] Erro ao salvar conversas: {e}")

    def _load_conversations(self):
        path = self.settings.chats_file
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for cid, conv in data.items():
                created = datetime.fromisoformat(conv["created"])
                self._conversations[cid] = {
                    "title": conv["title"],
                    "messages": conv.get("messages", []),
                    "created": created,
                }
                self.sidebar.add_conversation(cid, conv["title"], created)
        except Exception as e:
            print(f"[Celsius] Erro ao carregar conversas: {e}")

    def _on_send_message(self, text: str):
        if not text and not self.input_area.get_attachments():
            return

        attachments = self.input_area.get_attachments()
        self.chat_view.add_user_message(text, attachments)
        self.input_area.clear_attachments()

        # Save to conversation
        if self._current_conv_id and self._current_conv_id in self._conversations:
            self._conversations[self._current_conv_id]["messages"].append(("user", text))
            # Update title with first message
            if len(self._conversations[self._current_conv_id]["messages"]) == 1:
                title = text[:40] + ("..." if len(text) > 40 else "")
                self._conversations[self._current_conv_id]["title"] = title
                self.sidebar.update_conversation(self._current_conv_id, title)
            self._save_conversations()

        # Prepare payload
        payload = {
            "pergunta": text,
            "documento": self._pending_doc_text,
            "nome_documento": self._pending_doc_name,
            "caminho_documento": self._pending_file_path,
            "caminho_imagem": self._pending_image_path,
            "tipo_documento": "",
            "memorias_ativas": self._memories_enabled,
        }
        self._pending_doc_text = ""
        self._pending_doc_name = ""
        self._pending_file_path = ""
        self._pending_image_path = ""

        # Start streaming
        self.chat_view.start_streaming()

        self.worker_manager.submit_ai_task(
            payload,
            on_finished=self._on_ai_finished,
            on_status=self._on_ai_status,
            on_step=self._on_ai_step,
            on_chunk=lambda token: (print(f"[DEBUG] chunk: {token[:20]}"), self.chat_view.append_streaming(token)),
        )

    def _on_ai_status(self, msg: str):
        """Handle AI status updates - show thinking animation."""
        if not msg:
            self._stop_thinking()
            return

        # Start thinking animation with appropriate message
        if "Raciocinando" in msg or "pensando" in msg.lower():
            self._start_thinking("Pensando")
        elif "Executando" in msg:
            self._start_thinking("Espere enquanto busco as informações")
        elif "Analisando" in msg:
            self._start_thinking("Analisando")
        else:
            self._start_thinking("Processando")

    def _on_ai_step(self, step):
        pass

    def _on_ai_finished(self, response: str):
        print(f"[DEBUG] _on_ai_finished called, response len: {len(response)}")
        self._stop_thinking()
        self.chat_view.finish_streaming()
        if self._current_conv_id and self._current_conv_id in self._conversations:
            self._conversations[self._current_conv_id]["messages"].append(("assistant", response))
            self._save_conversations()
        if self.input_area.btn_voice.isChecked() and response.strip():
            self._speak_text(response)

    def _speak_text(self, texto: str):
        if self._voz_worker is not None:
            self._voz_worker.stop()
        from workers.tts_worker import VozWorker
        worker = VozWorker(texto)
        self._voz_worker = worker
        worker.erro_tts.connect(lambda msg: print(f"[TTS] {msg}"))
        worker.finished.connect(lambda: self._on_tts_finished(worker))
        worker.start()

    def _on_tts_finished(self, worker):
        if self._voz_worker is worker:
            self._voz_worker = None

    def _attach_file(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Arquivo", "",
            f"Arquivos Suportados ({self.settings.file_filter})"
        )
        if not caminho:
            return

        nome = os.path.basename(caminho)
        extensao = os.path.splitext(caminho)[1].lower()
        image_exts = [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"]

        try:
            if extensao in image_exts:
                self._pending_image_path = caminho
                self._pending_doc_text = ""
                self._pending_doc_name = nome
                self.input_area.add_attachment(f"🖼 {nome}")
            else:
                from pathlib import Path as _Path
                texto = processar_arquivo(caminho, base_dir=_Path(caminho).parent)
                self._pending_doc_text = texto or ""
                self._pending_doc_name = nome
                self._pending_file_path = caminho
                self._pending_image_path = ""
                self.input_area.add_attachment(nome)
        except Exception as e:
            self.chat_view.add_assistant_message(f"Erro ao processar arquivo: {e}")

    def _toggle_microphone(self):
        if self._mic_worker is not None:
            self._mic_worker.stop()
            self._mic_worker = None
            self.input_area.btn_mic.setIcon(icon("microphone", "#9E9EA3"))
            self.input_area.btn_mic.setToolTip("Gravar áudio")
        else:
            try:
                from workers.mic_worker import MicWorker
                self._mic_worker = MicWorker()
                self._mic_worker.signals.recognized.connect(self._on_mic_recognized)
                self._mic_worker.signals.error.connect(self._on_mic_error)
                self.worker_manager.pool.start(self._mic_worker)
                self.input_area.btn_mic.setIcon(icon("microphone", "#D32F2F"))
                self.input_area.btn_mic.setToolTip("Parar gravação")
            except Exception as e:
                self.chat_view.add_assistant_message(f"Erro ao iniciar microfone: {e}")

    def _on_mic_recognized(self, text: str):
        print(f"[DEBUG] _on_mic_recognized: '{text}'")
        self._mic_worker = None
        self.input_area.btn_mic.setIcon(icon("microphone", "#9E9EA3"))
        self.input_area.btn_mic.setToolTip("Gravar áudio")
        if text.strip():
            self.input_area.input.setText(text)
            self._on_send_message(text)

    def _on_mic_error(self, msg: str):
        print(f"[DEBUG] _on_mic_error: {msg}")
        self._mic_worker = None
        self.input_area.btn_mic.setIcon(icon("microphone", "#9E9EA3"))
        self.input_area.btn_mic.setToolTip("Gravar áudio")
        self.chat_view.add_assistant_message(f"Erro no microfone: {msg}")

    def _toggle_voice(self):
        if self._voz_worker is not None:
            self._voz_worker.stop()
            self._voz_worker = None

    def _change_model(self, model_id: str):
        from core.config import get_model_by_id
        from core.model_downloader import download_mmproj, download_model, is_model_downloaded

        model = get_model_by_id(model_id)
        if not model:
            self.chat_view.add_assistant_message(f"Modelo '{model_id}' nao encontrado.")
            return

        self.settings.set_llm_model(model_id)

        if not is_model_downloaded(model_id):
            self._start_thinking(f"Baixando {model.name} ({model.size_gb}GB)")
            self.chat_view.add_assistant_message(
                f"Baixando **{model.name}** ({model.quant}, {model.size_gb}GB)...\n"
                f"Isso pode levar alguns minutos dependendo da velocidade da internet."
            )
            # Download in background
            from PySide6.QtCore import QThread
            from PySide6.QtCore import Signal as QSignal

            class DownloadWorker(QThread):
                finished = QSignal(bool, str)

                def run(self):
                    try:
                        download_model(model_id, fn_status=lambda s: None)
                        if model.has_mmproj:
                            download_mmproj(model_id, fn_status=lambda s: None)
                        self.finished.emit(True, "")
                    except Exception as e:
                        self.finished.emit(False, str(e))

            self._download_worker = DownloadWorker()
            self._download_worker.finished.connect(
                lambda ok, err: self._on_model_downloaded(ok, err, model_id)
            )
            self._download_worker.start()
        else:
            self._do_switch_model(model_id)

    def _on_model_downloaded(self, ok: bool, error: str, model_id: str):
        self._stop_thinking()
        if ok:
            self._do_switch_model(model_id)
        else:
            self.chat_view.add_assistant_message(f"Erro ao baixar modelo: {error}")

    def _do_switch_model(self, model_id: str):
        from core.config import get_model_by_id
        model = get_model_by_id(model_id)
        name = model.name if model else model_id

        self._start_thinking(f"Carregando {name}")
        self.chat_view.add_assistant_message(f"Alterando modelo para **{name}**...")

        from PySide6.QtCore import QThread
        from PySide6.QtCore import Signal as QSignal

        class SwitchWorker(QThread):
            finished = QSignal(bool, str)

            def run(self):
                try:
                    from core.llama_cpp import switch_llama_model
                    switch_llama_model(model_id, n_gpu_layers=-1, n_ctx=8192, n_batch=1024)
                    self.finished.emit(True, "")
                except Exception as e:
                    self.finished.emit(False, str(e))

        self._switch_worker = SwitchWorker()
        self._switch_worker.finished.connect(
            lambda ok, err: self._on_model_switched(ok, err, model_id)
        )
        self._switch_worker.start()

    def _on_model_switched(self, ok: bool, error: str, model_id: str):
        self._stop_thinking()
        if ok:
            from core.config import get_model_by_id
            model = get_model_by_id(model_id)
            name = model.name if model else model_id
            self.chat_view.add_assistant_message(
                f"Modelo alterado para **{name}**. Pronto para uso."
            )
            # Refresh combo indicators
            self._refresh_model_combo()
        else:
            self.chat_view.add_assistant_message(
                f"Erro ao trocar modelo: {error}\n"
                f"Verifique se o arquivo GGUF esta na pasta resources/."
            )

    def _refresh_model_combo(self):
        """Update download status indicators in model combo."""
        from core.model_downloader import is_model_downloaded
        combo = self.input_area.model_combo
        for i in range(combo.count()):
            model_id = combo.itemData(i)
            model = next((m for m in self.input_area._combo_models if m.id == model_id), None)
            if model:
                status = "✓" if is_model_downloaded(model_id) else "↓"
                combo.setItemText(i, f"{status} {model.name} ({model.quant})")

    def _generate_report(self):
        pass

    def _show_settings(self):
        self.chat_view.add_assistant_message("Configuracoes em desenvolvimento.")

    def _toggle_theme(self):
        self._theme_mode = ThemeMode.DARK if self._theme_mode == ThemeMode.LIGHT else ThemeMode.LIGHT
        self._apply_theme()

    def closeEvent(self, event):
        self.worker_manager.cancel_all()
        event.accept()


def main():
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = ModernChatWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
