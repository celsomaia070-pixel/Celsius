"""
ModernChatView - Área de chat com bolhas de mensagem e streaming.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.animations import ThinkingIndicator
from ui.chat.message_bubble import MessageBubble
from ui.theme import LIGHT_SCHEME


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
        self.setObjectName("chatView")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("chatScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_widget = QWidget()
        self.content_widget.setObjectName("chatContent")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(56, 28, 56, 28)
        self.content_layout.setSpacing(12)
        self.content_layout.addStretch()

        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area)

        # Track scroll position for auto-scroll
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._apply_theme()

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            #chatView, #chatScroll, #chatContent {{
                background: {s.bg_primary};
                border: none;
            }}
            #chatScroll > QWidget > QWidget {{
                background: {s.bg_primary};
            }}
        """)

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

    def finish_streaming(self, final_content: str = ""):
        if self._streaming_bubble:
            try:
                if final_content:
                    self._streaming_content = final_content
                    self._streaming_bubble.update_content(final_content)
                self._streaming_bubble.finish_streaming()
                self.messages.append(("assistant", self._streaming_content))
                self._streaming_bubble = None
                self._streaming_content = ""
            except RuntimeError:
                self._streaming_bubble = None
                self._streaming_content = ""

    def _scroll_to_bottom(self):
        QTimer.singleShot(
            0,
            lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            ),
        )

    def clear(self):
        for i in reversed(range(self.content_layout.count() - 1)):
            widget = self.content_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.messages.clear()

    def show_thinking(self, text: str):
        if self._streaming_bubble:
            self._streaming_bubble.set_status(text)
            if self._auto_scroll:
                self._scroll_to_bottom()
            return

        if hasattr(self, "_thinking_widget") and self._thinking_widget:
            self._thinking_widget.set_text(text)
            if self._auto_scroll:
                self._scroll_to_bottom()
            return

        self.hide_thinking()
        self._saved_stretch = self.content_layout.takeAt(self.content_layout.count() - 1)
        self.content_layout.addStretch()
        self._thinking_widget = ThinkingIndicator(text=text, scheme=self._scheme)
        self.content_layout.addWidget(self._thinking_widget)
        self.content_layout.addStretch()
        self._scroll_to_bottom()

    def update_thinking(self, text: str):
        if self._streaming_bubble:
            self._streaming_bubble.set_status(text)
            return

        if hasattr(self, "_thinking_widget") and isinstance(
            self._thinking_widget, ThinkingIndicator
        ):
            self._thinking_widget.set_text(text)

    def hide_thinking(self):
        if self._streaming_bubble:
            self._streaming_bubble.clear_status()

        if hasattr(self, "_thinking_widget") and self._thinking_widget:
            for i in range(self.content_layout.count() - 1, -1, -1):
                item = self.content_layout.itemAt(i)
                if item and item.widget() == self._thinking_widget:
                    self.content_layout.takeAt(i)
                    self._thinking_widget.deleteLater()
                    self._thinking_widget = None
                    if i < self.content_layout.count():
                        after = self.content_layout.itemAt(i)
                        if after and after.spacerItem():
                            self.content_layout.takeAt(i)
                    if i > 0:
                        before = self.content_layout.itemAt(i - 1)
                        if before and before.spacerItem():
                            self.content_layout.takeAt(i - 1)
                    break
            if hasattr(self, "_saved_stretch") and self._saved_stretch:
                self.content_layout.addItem(self._saved_stretch)
                self._saved_stretch = None

    def set_scheme(self, scheme):
        self._scheme = scheme
        self._apply_theme()
        if hasattr(self, "_thinking_widget") and hasattr(self._thinking_widget, "set_scheme"):
            self._thinking_widget.set_scheme(scheme)
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageBubble):
                item.widget().set_scheme(scheme)
