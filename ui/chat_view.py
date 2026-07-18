import re

import qtawesome as qta
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class CodeBlockWidget(QWidget):
    """Widget for rendering code blocks with syntax highlighting and copy button."""

    def __init__(self, code: str, language: str = "", parent=None):
        super().__init__(parent)
        self.code = code
        self.language = language.lower() if language else ""
        self._setup_ui()
        self._highlight_code()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with language and copy button
        header = QWidget()
        header.setFixedHeight(36)
        header.setStyleSheet("""
            background-color: #161B22;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            border-bottom: 1px solid #30363D;
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)

        self.lang_label = QLabel(self.language or "text")
        self.lang_label.setStyleSheet("color: #8B949E; font-size: 11px; font-weight: 500;")
        header_layout.addWidget(self.lang_label)
        header_layout.addStretch()

        self.copy_btn = QPushButton()
        self.copy_btn.setIcon(qta.icon("fa5s.copy", color="#8B949E"))
        self.copy_btn.setToolTip("Copiar código")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setFixedSize(28, 28)
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton:hover {
                background: #30363D;
            }
        """)
        self.copy_btn.clicked.connect(self._copy_code)
        header_layout.addWidget(self.copy_btn)

        layout.addWidget(header)

        # Code editor (read-only)
        self.editor = QTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setFont(QFont("JetBrains Mono", "Consolas", "Monospace", 12))
        self.editor.setLineWrapMode(QTextEdit.NoWrap)
        self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #161B22;
                border: none;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                color: #E6EDF3;
                padding: 12px;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
                font-size: 13px;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.editor)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def _highlight_code(self):
        try:
            if self.language:
                lexer = get_lexer_by_name(self.language, stripall=True)
            else:
                lexer = guess_lexer(self.code)
        except (ClassNotFound, ValueError):
            lexer = TextLexer()

        formatter = HtmlFormatter(
            style="github-dark",
            noclasses=True,
            linenos=False,
            wrapcode=True,
        )

        highlighted = highlight(self.code, lexer, formatter)

        # Extract just the code part (without HTML wrapper)
        # Pygments HTMLFormatter wraps in <div class="highlight"><pre>...</pre></div>
        match = re.search(r'<pre[^>]*>(.*?)</pre>', highlighted, re.DOTALL)
        if match:
            code_html = match.group(1)
        else:
            code_html = highlighted

        self.editor.setHtml(code_html)

        # Adjust height based on content
        doc_height = self.editor.document().size().height()
        self.editor.setFixedHeight(min(max(doc_height + 24, 100), 400))

    def _copy_code(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code)

        # Visual feedback
        self.copy_btn.setIcon(qta.icon("fa5s.check", color="#3FB950"))
        QTimer.singleShot(1500, lambda: self.copy_btn.setIcon(
            qta.icon("fa5s.copy", color="#8B949E")
        ))


class MessageBubble(QWidget):
    """Modern message bubble with avatar, content, and actions."""

    copy_requested = Signal(str)
    regenerate_requested = Signal()

    def __init__(
        self,
        content: str,
        is_user: bool = False,
        is_streaming: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.content = content
        self.is_user = is_user
        self.is_streaming = is_streaming
        self._full_content = content
        self._setup_ui()
        self._render_content()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 4, 8, 4)
        main_layout.setSpacing(10)

        if self.is_user:
            main_layout.addStretch()

        # Bubble container
        bubble_container = QWidget()
        bubble_layout = QVBoxLayout(bubble_container)
        bubble_layout.setContentsMargins(0, 0, 0, 0)
        bubble_layout.setSpacing(6)

        # Avatar row (for assistant)
        if not self.is_user:
            avatar_row = QHBoxLayout()
            avatar_row.setSpacing(8)

            self.avatar = QLabel()
            self.avatar.setFixedSize(28, 28)
            self.avatar.setAlignment(Qt.AlignCenter)
            self.avatar.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #58A6FF, stop:1 #388BF0);
                border-radius: 14px;
                color: white;
                font-weight: 600;
                font-size: 12px;
            """)
            self.avatar.setText("C")
            avatar_row.addWidget(self.avatar)

            name_label = QLabel("Celsius")
            name_label.setStyleSheet("color: #8B949E; font-size: 11px; font-weight: 500;")
            avatar_row.addWidget(name_label)
            avatar_row.addStretch()
            bubble_layout.addLayout(avatar_row)

        # Content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(14, 10, 14, 10)
        self.content_layout.setSpacing(8)
        bubble_layout.addWidget(self.content_widget)

        # Actions row (for assistant)
        if not self.is_user:
            self.actions_row = QHBoxLayout()
            self.actions_row.setSpacing(6)
            self.actions_row.addStretch()

            self.copy_btn = self._create_action_btn("fa5s.copy", "Copiar")
            self.copy_btn.clicked.connect(lambda: self.copy_requested.emit(self._full_content))
            self.actions_row.addWidget(self.copy_btn)

            self.regen_btn = self._create_action_btn("fa5s.sync", "Regenerar")
            self.regen_btn.clicked.connect(self.regenerate_requested.emit)
            self.actions_row.addWidget(self.regen_btn)

            self.actions_widget = QWidget()
            self.actions_widget.setLayout(self.actions_row)
            self.actions_widget.setVisible(False)  # Show on hover
            bubble_layout.addWidget(self.actions_widget)

        # Styling
        if self.is_user:
            bubble_container.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #007AFF, stop:1 #0056CC);
                border-radius: 18px;
                border-bottom-right-radius: 4px;
            """)
        else:
            bubble_container.setStyleSheet("""
                background: #1E1E1E;
                border: 1px solid #30363D;
                border-radius: 18px;
                border-bottom-left-radius: 4px;
            """)
            bubble_container.setMouseTracking(True)
            bubble_container.enterEvent = lambda e: self._show_actions(True)
            bubble_container.leaveEvent = lambda e: self._show_actions(False)

        main_layout.addWidget(bubble_container)

        if not self.is_user:
            main_layout.addStretch()

    def _create_action_btn(self, icon_name: str, tooltip: str) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(qta.icon(icon_name, color="#8B949E"))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(28, 28)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #30363D;
                icon-color: #E6EDF3;
            }
        """)
        return btn

    def _show_actions(self, show: bool):
        if hasattr(self, 'actions_widget'):
            self.actions_widget.setVisible(show)

    def _render_content(self):
        # Clear existing
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Parse markdown-like content
        parts = self._parse_markdown(self.content)

        for part_type, part_content in parts:
            if part_type == "text":
                label = QLabel(part_content)
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                label.setStyleSheet(self._get_text_style())
                label.setFont(QFont("Segoe UI", 13))
                self.content_layout.addWidget(label)

            elif part_type == "code":
                lang, code = part_content
                code_widget = CodeBlockWidget(code, lang)
                self.content_layout.addWidget(code_widget)

            elif part_type == "table":
                table_widget = self._create_table(part_content)
                self.content_layout.addWidget(table_widget)

    def _get_text_style(self):
        if self.is_user:
            return "color: white; line-height: 1.6;"
        return "color: #E6EDF3; line-height: 1.6;"

    def _parse_markdown(self, text: str):
        """Parse markdown into (type, content) parts."""
        parts = []

        # Split by code blocks first
        code_pattern = r'```(\w*)\n(.*?)```'
        last_end = 0

        for match in re.finditer(code_pattern, text, re.DOTALL):
            # Text before code block
            if match.start() > last_end:
                text_part = text[last_end:match.start()]
                if text_part.strip():
                    parts.append(("text", text_part.strip()))

            # Code block
            lang = match.group(1)
            code = match.group(2)
            parts.append(("code", (lang, code)))
            last_end = match.end()

        # Remaining text
        if last_end < len(text):
            text_part = text[last_end:]
            if text_part.strip():
                parts.append(("text", text_part.strip()))

        # If no code blocks, treat as text
        if not parts:
            parts.append(("text", text))

        return parts

    def _create_table(self, rows: list) -> QWidget:
        """Create a table widget from parsed rows."""
        from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

        table = QTableWidget()
        table.setRowCount(len(rows))
        table.setColumnCount(len(rows[0]) if rows else 0)
        table.setStyleSheet("""
            QTableWidget {
                background: #161B22;
                border: 1px solid #30363D;
                border-radius: 8px;
                gridline-color: #30363D;
                color: #E6EDF3;
            }
            QHeaderView::section {
                background: #21262D;
                color: #58A6FF;
                padding: 8px 12px;
                border: none;
                border-right: 1px solid #30363D;
                border-bottom: 1px solid #30363D;
                font-weight: 600;
            }
            QTableWidget::item {
                padding: 8px 12px;
                border-bottom: 1px solid #21262D;
            }
            QTableWidget::item:selected {
                background: #58A6FF30;
            }
        """)

        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setFocusPolicy(Qt.NoFocus)

        for i, row in enumerate(rows):
            for j, cell in enumerate(row):
                item = QTableWidgetItem(cell.strip())
                table.setItem(i, j, item)

        table.resizeColumnsToContents()
        table.setMaximumHeight(300)
        return table

    def append_content(self, token: str):
        """Append token during streaming."""
        self._full_content += token
        self.content = self._full_content
        self._render_content()

    def set_content(self, content: str):
        self._full_content = content
        self.content = content
        self._render_content()

    def set_streaming(self, streaming: bool):
        self.is_streaming = streaming
        # Add cursor animation if streaming


class StreamingCursor(QWidget):
    """Animated cursor for streaming messages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(2)
        self.setFixedHeight(20)
        self._timer = QTimer()
        self._timer.timeout.connect(self._blink)
        self._visible = True
        self._timer.start(500)

    def _blink(self):
        self._visible = not self._visible
        self.update()

    def paintEvent(self, event):
        if self._visible:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.fillRect(self.rect(), QColor("#58A6FF"))

    def stop(self):
        self._timer.stop()
        self._visible = False
        self.update()


class ChatView(QWidget):
    """Modern chat view with message bubbles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._messages = []
        self._auto_scroll = True
        self._user_scrolled_up = False

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area
        from PySide6.QtWidgets import QScrollArea
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
        """)

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(20, 20, 20, 20)
        self.messages_layout.setSpacing(12)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area)

        # Scroll to bottom button
        self.scroll_bottom_btn = QPushButton()
        self.scroll_bottom_btn.setIcon(qta.icon("fa5s.chevron-down", color="#8B949E"))
        self.scroll_bottom_btn.setFixedSize(40, 40)
        self.scroll_bottom_btn.setStyleSheet("""
            QPushButton {
                background: #1E1E1E;
                border: 1px solid #30363D;
                border-radius: 20px;
            }
            QPushButton:hover {
                background: #30363D;
                border-color: #484F58;
            }
        """)
        self.scroll_bottom_btn.setCursor(Qt.PointingHandCursor)
        self.scroll_bottom_btn.clicked.connect(self._scroll_to_bottom)
        self.scroll_bottom_btn.hide()

        # Overlay button
        self.scroll_bottom_btn.setParent(self.scroll_area)

    def add_message(self, content: str, is_user: bool = False) -> MessageBubble:
        bubble = MessageBubble(content, is_user)
        bubble.copy_requested.connect(lambda c: self._copy_to_clipboard(c))

        # Remove stretch
        self.messages_layout.takeAt(self.messages_layout.count() - 1)

        self.messages_layout.addWidget(bubble)
        self.messages_layout.addStretch()
        self._messages.append(bubble)

        if self._auto_scroll and not self._user_scrolled_up:
            QTimer.singleShot(50, self._scroll_to_bottom)

        return bubble

    def add_streaming_message(self, is_user: bool = False) -> MessageBubble:
        bubble = MessageBubble("", is_user, is_streaming=True)
        bubble.copy_requested.connect(lambda c: self._copy_to_clipboard(c))

        self.messages_layout.takeAt(self.messages_layout.count() - 1)
        self.messages_layout.addWidget(bubble)
        self.messages_layout.addStretch()
        self._messages.append(bubble)

        if self._auto_scroll and not self._user_scrolled_up:
            QTimer.singleShot(50, self._scroll_to_bottom)

        return bubble

    def _scroll_to_bottom(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.scroll_bottom_btn.hide()

    def _copy_to_clipboard(self, text: str):
        QApplication.clipboard().setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position scroll to bottom button
        btn_size = 40
        margin = 20
        self.scroll_bottom_btn.move(
            self.width() - btn_size - margin,
            self.height() - btn_size - margin - 80  # Above input area
        )

    def wheelEvent(self, event):
        # Detect user scrolling up
        scrollbar = self.scroll_area.verticalScrollBar()
        at_bottom = scrollbar.value() == scrollbar.maximum()

        if not at_bottom and event.angleDelta().y() > 0:
            self._user_scrolled_up = True
            self.scroll_bottom_btn.show()
        elif at_bottom:
            self._user_scrolled_up = False
            self.scroll_bottom_btn.hide()

        super().wheelEvent(event)
