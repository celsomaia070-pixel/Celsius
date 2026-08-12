"""
MessageBubble - Widget para exibir mensagens do chat.
"""

import re

from PySide6.QtCore import Qt, QTimer
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

from ui.icons import icon
from ui.theme import LIGHT_SCHEME
from ui.theme.tokens import RADIUS, SPACING, TYPOGRAPHY


class MessageBubble(QWidget):
    """Clean message with label - no bubble, text directly on page."""

    def __init__(
        self,
        content: str,
        is_user: bool = False,
        is_streaming: bool = False,
        attachments: list = None,
        scheme=None,
        parent=None,
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
            msg_layout.setContentsMargins(16, 12, 16, 10)
            msg_layout.setSpacing(6)
        else:
            self.message_widget = QWidget()
            msg_layout = QVBoxLayout(self.message_widget)
            msg_layout.setContentsMargins(16, 12, 16, 10)
            msg_layout.setSpacing(6)

        self.message_widget.setObjectName("messageSurface")
        self.message_widget.setMaximumWidth(760 if self.is_user else 860)

        # Label: "Voce" or "Celsius"
        self.name_label = QLabel("Voce" if self.is_user else "Celsius")
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(SPACING.space_2)
        name_row.addWidget(self.name_label)
        name_row.addStretch()
        msg_layout.addLayout(name_row)

        self.status_label = QLabel()
        self.status_label.hide()
        if not self.is_user:
            msg_layout.addWidget(self.status_label)

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
        self.content_label.document().contentsChanged.connect(self._adjust_height)
        self.content_label.document().documentLayout().documentSizeChanged.connect(
            lambda _: self._adjust_height()
        )
        msg_layout.addWidget(self.content_label)

        # Actions for assistant - on hover
        if not self.is_user:
            self.actions_widget = self._create_actions()
            msg_layout.addWidget(self.actions_widget)
            self.actions_widget.hide()
            self.setMouseTracking(True)
            self.content_label.setMouseTracking(True)
            self.content_label.enterEvent = lambda e: self._show_actions()
            self.content_label.leaveEvent = lambda e: self._schedule_hide_actions()
            self.actions_widget.setMouseTracking(True)
            self.actions_widget.enterEvent = lambda e: self._cancel_hide_actions()
            self.actions_widget.leaveEvent = lambda e: self._schedule_hide_actions()

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
        self._apply_message_style()

    def _apply_message_style(self):
        s = self._scheme
        background = s.user_bubble_bg if self.is_user else s.assistant_bubble_bg
        foreground = s.user_bubble_text if self.is_user else s.assistant_bubble_text
        border = s.accent_primary if self.is_user else s.border_default
        name_color = s.text_secondary if self.is_user else s.accent_primary

        self.message_widget.setStyleSheet(f"""
            #messageSurface {{
                background: {background};
                border: 1px solid {border};
                border-radius: {RADIUS.radius_lg}px;
            }}
        """)
        self.name_label.setStyleSheet(
            f"color: {name_color}; font-size: {TYPOGRAPHY.text_base}px; "
            f"font-weight: {TYPOGRAPHY.weight_bold}; background: transparent; border: none;"
        )
        self.status_label.setStyleSheet(
            f"color: {s.accent_primary}; font-size: {TYPOGRAPHY.text_sm}px; "
            f"font-weight: {TYPOGRAPHY.weight_semibold}; background: transparent; border: none;"
        )
        self.content_label.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                color: {foreground};
                font-size: {TYPOGRAPHY.text_base}px;
                selection-background-color: {s.accent_subtle};
            }}
        """)

    def _add_attachments(self, layout):
        s = self._scheme
        attach_layout = QHBoxLayout()
        attach_layout.setSpacing(SPACING.space_2)
        attach_layout.setContentsMargins(0, 0, 0, 0)
        for att in self.attachments:
            chip = QLabel(f"arquivo: {att}")
            chip.setStyleSheet(f"""
                background: {s.accent_primary}15;
                border: 1px solid {s.accent_primary}40;
                border-radius: {RADIUS.radius_sm}px;
                padding: {SPACING.space_1}px {SPACING.space_3}px;
                color: {s.accent_primary};
                font-size: {TYPOGRAPHY.text_xs}px;
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
        layout.setSpacing(SPACING.space_1)
        layout.addStretch()

        # Copiar
        btn_copy = QPushButton()
        btn_copy.setIcon(icon("copy", s.text_muted))
        btn_copy.setToolTip("Copiar mensagem")
        btn_copy.setCursor(Qt.PointingHandCursor)
        btn_copy.setFixedSize(26, 26)
        btn_copy.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: {RADIUS.radius_sm}px;
                padding: {SPACING.space_1}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
        """)
        btn_copy.clicked.connect(self._copy_content)
        layout.addWidget(btn_copy)

        # Imprimir
        btn_print = QPushButton()
        btn_print.setIcon(icon("print", s.text_muted))
        btn_print.setToolTip("Imprimir mensagem")
        btn_print.setCursor(Qt.PointingHandCursor)
        btn_print.setFixedSize(26, 26)
        btn_print.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: {RADIUS.radius_sm}px;
                padding: {SPACING.space_1}px;
            }}
            QPushButton:hover {{
                background: {s.bg_hover};
            }}
        """)
        btn_print.clicked.connect(self._print_content)
        layout.addWidget(btn_print)

        return widget

    def _copy_content(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.content_label.toPlainText())

    def _print_content(self):
        from PySide6.QtGui import QTextDocument
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.Accepted:
            doc = QTextDocument()
            doc.setPlainText(self.content_label.toPlainText())
            doc.print_(printer)

    def _show_actions(self):
        if hasattr(self, "actions_widget"):
            self._cancel_hide_actions()
            self.actions_widget.show()

    def _hide_actions(self):
        if hasattr(self, "actions_widget"):
            self.actions_widget.hide()

    def _schedule_hide_actions(self):
        if hasattr(self, "_hide_timer"):
            self._hide_timer.stop()
        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(200)
        self._hide_timer.timeout.connect(self._hide_actions)
        self._hide_timer.start()

    def _cancel_hide_actions(self):
        if hasattr(self, "_hide_timer"):
            self._hide_timer.stop()

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
        text = re.sub(
            r"```(\w*)\n(.*?)```",
            lambda m: (
                f'<div style="background:{s.code_bg}; border:1px solid {s.code_border}; border-radius:8px; padding:12px; margin:8px 0; font-family:Consolas,monospace; font-size:13px; color:{s.code_text};">'
                f'<pre style="margin:0; white-space:pre-wrap;">{m.group(2)}</pre></div>'
            ),
            text,
            flags=re.DOTALL,
        )

        # Inline code
        text = re.sub(
            r"`([^`]+)`",
            f'<code style="background:{s.code_bg}; border:1px solid {s.code_border}; border-radius:4px; padding:2px 6px; font-family:Consolas,monospace; font-size:13px; color:{s.accent_primary};">\\1</code>',
            text,
        )

        # Bold/italic
        text = re.sub(r"\*\*(.+?)\*\*", f'<b style="color:{tp};">\\1</b>', text)
        text = re.sub(r"\*(.+?)\*", f'<i style="color:{s.text_secondary};">\\1</i>', text)

        # Headers
        text = re.sub(
            r"^### (.+)$",
            f'<h4 style="color:{tp}; margin:12px 0 4px 0; font-size:15px;">\\1</h4>',
            text,
            flags=re.MULTILINE,
        )
        text = re.sub(
            r"^## (.+)$",
            f'<h3 style="color:{tp}; margin:14px 0 6px 0; font-size:16px;">\\1</h3>',
            text,
            flags=re.MULTILINE,
        )
        text = re.sub(
            r"^# (.+)$",
            f'<h2 style="color:{tp}; margin:16px 0 8px 0; font-size:18px;">\\1</h2>',
            text,
            flags=re.MULTILINE,
        )

        # Lists
        def process_list(match):
            items = match.group(0).strip().split("\n")
            html = f'<ul style="margin:6px 0; padding-left:20px; color:{tp};">'
            for item in items:
                item = re.sub(r"^[-*]\s+", "", item.strip())
                if item:
                    html += f'<li style="margin:3px 0; color:{tp};">{item}</li>'
            html += "</ul>"
            return html

        text = re.sub(r"(?:^[-*] .+\n?)+", process_list, text, flags=re.MULTILINE)

        # Numbered lists
        def process_num_list(match):
            items = match.group(0).strip().split("\n")
            html = f'<ol style="margin:6px 0; padding-left:20px; color:{tp};">'
            for item in items:
                item = re.sub(r"^\d+\.\s+", "", item.strip())
                if item:
                    html += f'<li style="margin:3px 0; color:{tp};">{item}</li>'
            html += "</ol>"
            return html

        text = re.sub(r"(?:^\d+\. .+\n?)+", process_num_list, text, flags=re.MULTILINE)

        # Tables
        def process_table(match):
            lines = match.group(0).strip().split("\n")
            rows = [
                line
                for line in lines
                if line.strip() and not re.match(r"^\|[-:|]+\|$", line.strip())
            ]
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

        text = re.sub(r"(?:^\|.+\|\n?)+", process_table, text, flags=re.MULTILINE)

        # Images: ![alt](path) -> <img>
        def process_image(m):
            alt = m.group(1)
            src = m.group(2)
            if not src.startswith(("http://", "https://", "data:image")):
                from pathlib import Path as _Path

                p = _Path(src)
                if not p.is_absolute():
                    p = _Path(__file__).parent.parent.parent / src
                src = p.as_posix()
            return f'<img src="{src}" alt="{alt}" style="max-width:100%; border-radius:8px; margin:8px 0;">'

        text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", process_image, text)

        # Links
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            f'<a href="\\2" style="color:{s.accent_primary}; text-decoration:none;">\\1</a>',
            text,
        )

        # Newlines to <br>
        text = text.replace("\n", "<br>")

        return text

    def _adjust_height(self):
        doc = self.content_label.document()
        doc.setTextWidth(self.content_label.viewport().width())
        h = int(doc.size().height()) + 8
        self.content_label.setMinimumHeight(max(h, 24))

    def _fade_in(self):
        from ui.animations import fade_in

        fade_in(self)

    def update_content(self, content: str):
        self.content = content
        self._full_content = content
        display = content
        if self.is_streaming and self._cursor_visible:
            display += "▌"
        self.content_label.setHtml(self._markdown_to_html(display))
        self._adjust_height()

    def set_status(self, text: str):
        if self.is_user:
            return
        cleaned = text.strip()
        self.status_label.setText(cleaned)
        self.status_label.setVisible(bool(cleaned))

    def clear_status(self):
        if self.is_user:
            return
        self.status_label.clear()
        self.status_label.hide()

    def finish_streaming(self):
        self.is_streaming = False
        self._cursor_timer.stop()
        self.clear_status()
        if hasattr(self, "name_label"):
            self.name_label.show()
        self.update_content(self._full_content)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Reflow text when bubble resizes
        self._adjust_height()

    def set_scheme(self, scheme):
        self._scheme = scheme
        self._apply_message_style()
        if hasattr(self, "actions_widget"):
            # Recreate actions with new scheme
            self.actions_widget.deleteLater()
            self.actions_widget = self._create_actions()
            self.layout().itemAt(0).widget().layout().addWidget(self.actions_widget)
            self.actions_widget.hide()
        self._render_content()
