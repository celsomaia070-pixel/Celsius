from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QTimer,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ui.theme.schemes import ColorScheme, get_scheme
from ui.theme.tokens import SPACING, TYPOGRAPHY


def fade_in(widget: QWidget, duration: int = 300, start: float = 0.0, end: float = 1.0):
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start()
    widget._fade_anim = anim
    return anim


def fade_out(widget: QWidget, duration: int = 200, on_done=None):
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.InCubic)
    if on_done:
        anim.finished.connect(on_done)
    anim.start()
    widget._fade_anim = anim
    return anim


def slide_up(widget: QWidget, duration: int = 300, offset: int = 20):
    anim = QPropertyAnimation(widget, b"pos")
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    widget.show()
    return anim


class ThinkingIndicator(QWidget):
    def __init__(self, text: str = "Pensando", scheme: ColorScheme = None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or get_scheme()
        self._base_text = text
        self._dots_count = 0
        self._setup_ui()
        self._start_animation()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACING.space_2, SPACING.space_1, SPACING.space_2, SPACING.space_1
        )
        layout.setSpacing(SPACING.space_2)
        self._label = QLabel(self._base_text)
        self._label.setStyleSheet(
            f"color: {self._scheme.text_muted};"
            f"font-size: {TYPOGRAPHY.text_sm}px;"
            f"font-style: italic;"
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._label)
        layout.addStretch()
        self._dots_label = QLabel()
        self._dots_label.setStyleSheet(
            f"color: {self._scheme.text_muted};"
            f"font-size: {TYPOGRAPHY.text_sm}px;"
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._dots_label)

    def _start_animation(self):
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._animate)
        self._timer.start()
        self._animate()

    def _animate(self):
        self._dots_count = (self._dots_count % 3) + 1
        self._dots_label.setText("." * self._dots_count)

    def set_text(self, text: str):
        self._base_text = text
        self._label.setText(text)

    def stop(self):
        self._timer.stop()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._label.setStyleSheet(
            f"color: {scheme.text_muted};"
            f"font-size: {TYPOGRAPHY.text_sm}px;"
            f"font-style: italic;"
            f"background: transparent; border: none;"
        )
        self._dots_label.setStyleSheet(
            f"color: {scheme.text_muted};"
            f"font-size: {TYPOGRAPHY.text_sm}px;"
            f"background: transparent; border: none;"
        )
