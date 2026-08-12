"""
Base Components - Componentes base para o sistema de UI do Celsius.
Componentes atômicos reutilizáveis com suporte a temas.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme.icons import icon as create_icon
from ui.theme.schemes import ColorScheme, get_scheme
from ui.theme.tokens import RADIUS, SPACING, TYPOGRAPHY, tokens


class ThemedWidget(QWidget):
    """Widget base que reage a mudanças de tema."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scheme = get_scheme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        pass

    def _color(self, role: str) -> str:
        return getattr(self._scheme, role, "#000000")

    def _token(self, name: str):
        return getattr(tokens, name, None)


class Card(ThemedWidget):
    """Card container com bordas e padding."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(f"""
            #Card {{
                background-color: {self._scheme.bg_secondary};
                border: 1px solid {self._scheme.border_default};
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_4}px;
            }}
            #Card:hover {{
                border-color: {self._scheme.border_strong};
            }}
        """)


class Badge(QLabel):
    """Badge de status inline."""

    _COLOR_MAP = {
        "default": ("text_primary", "bg_tertiary"),
        "primary": ("text_on_accent", "accent_primary"),
        "success": ("success_text", "success_bg"),
        "warning": ("warning_text", "warning_bg"),
        "danger": ("error_text", "error_bg"),
        "info": ("info_text", "info_bg"),
    }

    def __init__(self, text: str = "", variant: str = "default", parent=None):
        super().__init__(text, parent)
        self._variant = variant
        self._scheme = get_scheme()
        self.setAlignment(Qt.AlignCenter)
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        fg_role, bg_role = self._COLOR_MAP.get(self._variant, ("text_primary", "bg_tertiary"))
        fg = getattr(self._scheme, fg_role, "#000000")
        bg = getattr(self._scheme, bg_role, "#F5F5F5")
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border-radius: {RADIUS.radius_full}px;
                padding: {SPACING.space_1}px {SPACING.space_3}px;
                font-size: {TYPOGRAPHY.text_xs}px;
                font-weight: {TYPOGRAPHY.weight_medium};
            }}
        """)

    def set_variant(self, variant: str):
        self._variant = variant
        self._apply_theme()


class IconButton(QPushButton):
    """Botão de ícone compacto."""

    def __init__(self, icon_name: str = "", tooltip: str = "", size: int = 32, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._size = size
        self._scheme = get_scheme()
        self._hovered = False
        self._pressed = False

        if tooltip:
            self.setToolTip(tooltip)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self._update_icon()
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._update_icon()
        self._apply_theme()

    def _update_icon(self):
        if self._icon_name:
            self.setIcon(create_icon(self._icon_name, self._scheme.text_primary, self._size - 8))

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._scheme.bg_secondary};
                border: 1px solid {self._scheme.border_default};
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px;
            }}
            QPushButton:hover {{
                background-color: {self._scheme.bg_hover};
                border-color: {self._scheme.accent_primary};
            }}
            QPushButton:pressed {{
                background-color: {self._scheme.bg_active};
            }}
        """)

    def enterEvent(self, event):
        self._hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        super().leaveEvent(event)


class TextButton(QPushButton):
    """Botão de texto com variantes."""

    def __init__(self, text: str = "", variant: str = "default", parent=None):
        super().__init__(text, parent)
        self._variant = variant
        self._scheme = get_scheme()
        self.setCursor(Qt.PointingHandCursor)
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        variants = {
            "primary": (
                self._scheme.text_on_accent,
                self._scheme.accent_primary,
                self._scheme.accent_hover,
            ),
            "danger": (self._scheme.error_text, self._scheme.error, self._scheme.error),
            "default": (
                self._scheme.text_primary,
                self._scheme.bg_secondary,
                self._scheme.bg_hover,
            ),
        }
        fg, bg, hover = variants.get(self._variant, variants["default"])
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {self._scheme.border_default};
                border-radius: {RADIUS.radius_md}px;
                padding: {SPACING.space_2}px {SPACING.space_4}px;
                font-size: {TYPOGRAPHY.text_sm}px;
                font-weight: {TYPOGRAPHY.weight_medium};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {self._scheme.bg_active};
            }}
        """)


class SectionHeader(ThemedWidget):
    """Cabeçalho de seção com título e ações."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, SPACING.space_2, 0, SPACING.space_2)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(f"""
            font-size: {TYPOGRAPHY.text_sm}px;
            font-weight: {TYPOGRAPHY.weight_semibold};
            color: {self._scheme.text_secondary};
            text-transform: uppercase;
            letter-spacing: 0.5px;
        """)
        layout.addWidget(self._title_label)
        layout.addStretch()

        self._actions_layout = QHBoxLayout()
        self._actions_layout.setSpacing(SPACING.space_1)
        layout.addLayout(self._actions_layout)

    def add_action(self, button: IconButton):
        self._actions_layout.addWidget(button)

    def set_title(self, title: str):
        self._title_label.setText(title)

    def _apply_theme(self):
        self._title_label.setStyleSheet(f"""
            font-size: {TYPOGRAPHY.text_sm}px;
            font-weight: {TYPOGRAPHY.weight_semibold};
            color: {self._scheme.text_secondary};
            text-transform: uppercase;
            letter-spacing: 0.5px;
        """)


class Divider(QFrame):
    """Divisor horizontal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scheme = get_scheme()
        self.setFixedHeight(1)
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {self._scheme.border_subtle};
            }}
        """)


class EmptyState(ThemedWidget):
    """Estado vazio com ícone e mensagem."""

    def __init__(self, icon_name: str = "inbox", title: str = "", message: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(SPACING.space_4)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setPixmap(
            create_icon(icon_name, self._scheme.text_muted, 48).pixmap(48, 48)
        )
        layout.addWidget(self._icon_label)

        self._title_label = QLabel(title)
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet(f"""
            font-size: {TYPOGRAPHY.text_lg}px;
            font-weight: {TYPOGRAPHY.weight_semibold};
            color: {self._scheme.text_primary};
        """)
        layout.addWidget(self._title_label)

        self._message_label = QLabel(message)
        self._message_label.setAlignment(Qt.AlignCenter)
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet(f"""
            font-size: {TYPOGRAPHY.text_sm}px;
            color: {self._scheme.text_secondary};
        """)
        layout.addWidget(self._message_label)

    def _apply_theme(self):
        self._icon_label.setPixmap(create_icon("inbox", self._scheme.text_muted, 48).pixmap(48, 48))
        self._title_label.setStyleSheet(f"""
            font-size: {TYPOGRAPHY.text_lg}px;
            font-weight: {TYPOGRAPHY.weight_semibold};
            color: {self._scheme.text_primary};
        """)
        self._message_label.setStyleSheet(f"""
            font-size: {TYPOGRAPHY.text_sm}px;
            color: {self._scheme.text_secondary};
        """)


class SearchInput(QLineEdit):
    """Campo de busca com ícone integrado."""

    def __init__(self, placeholder: str = "Buscar...", icon_name: str = "search", parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._scheme = get_scheme()
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(36)
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {s.bg_primary};
                border: 1px solid {s.border_default};
                border-radius: {RADIUS.radius_md}px;
                padding: 0 {SPACING.space_3}px;
                padding-left: 36px;
                color: {s.text_primary};
                font-size: {TYPOGRAPHY.text_sm}px;
            }}
            QLineEdit:focus {{
                border-color: {s.accent_primary};
            }}
        """)
        for action in self.actions():
            self.removeAction(action)
        self.addAction(
            create_icon(self._icon_name, self._scheme.text_muted),
            QLineEdit.LeadingPosition,
        )


class Avatar(QLabel):
    """Avatar circular com iniciais ou ícone."""

    def __init__(self, text: str = "", icon_name: str = "", size: int = 32, parent=None):
        super().__init__(parent)
        self._text = text
        self._icon_name = icon_name
        self._size = size
        self._scheme = get_scheme()
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        s = self._scheme
        if self._icon_name:
            pixmap = create_icon(self._icon_name, s.text_on_accent, self._size - 8).pixmap(
                self._size - 8, self._size - 8
            )
            self.setPixmap(pixmap)
        else:
            initials = self._text[:2].upper() if self._text else "?"
            font = QFont("Segoe UI", int(self._size * 0.35), QFont.Weight.Bold)
            self.setFont(font)
            self.setText(initials)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {s.accent_primary};
                color: {s.text_on_accent};
                border-radius: {self._size // 2}px;
            }}
        """)

    def set_text(self, text: str):
        self._text = text
        self._icon_name = ""
        self._apply_theme()

    def set_icon(self, icon_name: str):
        self._icon_name = icon_name
        self._apply_theme()


class StatusIndicator(QLabel):
    """Indicador de status com dot colorido."""

    _STATUS_COLORS = {
        "success": "success",
        "warning": "warning",
        "error": "error",
        "info": "info",
        "default": "text_muted",
    }

    def __init__(self, status: str = "default", size: int = 8, parent=None):
        super().__init__(parent)
        self._status = status
        self._size = size
        self._scheme = get_scheme()
        self.setFixedSize(size, size)
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def set_status(self, status: str):
        self._status = status
        self._apply_theme()

    def _apply_theme(self):
        color_attr = self._STATUS_COLORS.get(self._status, "text_muted")
        color = getattr(self._scheme, color_attr, "#AEAEB2")
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: {self._size // 2}px;
            }}
        """)


class Toast(ThemedWidget):
    """Notificação toast animada."""

    def __init__(self, text: str = "", variant: str = "info", duration: int = 3000, parent=None):
        super().__init__(parent)
        self._variant = variant
        self._duration = duration
        self._setup_ui(text)
        self._apply_theme()

    def _setup_ui(self, text: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACING.space_4, SPACING.space_3, SPACING.space_4, SPACING.space_3
        )
        layout.setSpacing(SPACING.space_3)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(20, 20)
        layout.addWidget(self._icon_label)

        self._text_label = QLabel(text)
        self._text_label.setWordWrap(True)
        layout.addWidget(self._text_label, 1)

        self._close_btn = QPushButton()
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setFlat(True)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self._dismiss)
        layout.addWidget(self._close_btn)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        s = self._scheme
        variant_map = {
            "success": (s.success, s.success_bg, s.success_text, "check-circle"),
            "warning": (s.warning, s.warning_bg, s.warning_text, "alert-triangle"),
            "error": (s.error, s.error_bg, s.error_text, "alert-circle"),
            "info": (s.info, s.info_bg, s.info_text, "info"),
        }
        border_color, bg_color, text_color, icon_name = variant_map.get(
            self._variant, (s.border_default, s.bg_secondary, s.text_primary, "info")
        )
        self.setStyleSheet(f"""
            Toast {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: {RADIUS.radius_md}px;
            }}
        """)
        self._text_label.setStyleSheet(
            f"color: {text_color}; font-size: {TYPOGRAPHY.text_sm}px; background: transparent; border: none;"
        )
        self._icon_label.setPixmap(create_icon(icon_name, text_color, 20).pixmap(20, 20))
        self._close_btn.setIcon(create_icon("x", text_color, 16))

    def show_toast(self):
        """Mostra o toast com animação de fade-in, espera, depois fade-out."""
        self.show()
        anim_in = QPropertyAnimation(self._opacity, b"opacity")
        anim_in.setDuration(200)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.setEasingCurve(QEasingCurve.OutCubic)
        anim_in.start()
        self._anim_in = anim_in

        QTimer.singleShot(self._duration, self._dismiss)

    def _dismiss(self):
        anim_out = QPropertyAnimation(self._opacity, b"opacity")
        anim_out.setDuration(200)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.InCubic)
        anim_out.finished.connect(self.hide)
        anim_out.start()
        self._anim_out = anim_out
