from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ui.theme.schemes import ColorScheme, get_scheme
from ui.theme.tokens import RADIUS, SPACING, TYPOGRAPHY


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


class PulsingDots(QWidget):
    def __init__(self, scheme: ColorScheme = None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or get_scheme()
        self._dot_count = 3
        self._dot_size = 6
        self._spacing = 4
        self._opacity = [1.0, 1.0, 1.0]
        self._effects = []
        self._timers = []
        self._setup_ui()
        self._start_animation()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._spacing)
        for _i in range(self._dot_count):
            dot = QLabel()
            dot.setFixedSize(self._dot_size, self._dot_size)
            dot.setStyleSheet(
                f"background: {self._scheme.text_muted};border-radius: {self._dot_size // 2}px;"
            )
            effect = QGraphicsOpacityEffect(dot)
            dot.setGraphicsEffect(effect)
            self._effects.append(effect)
            layout.addWidget(dot)

    def _start_animation(self):
        for i in range(self._dot_count):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda idx=i: self._pulse(idx))
            self._timers.append(timer)
            timer.start(i * 300)

    def _pulse(self, index):
        if index >= len(self._effects):
            return
        effect = self._effects[index]
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(600)
        anim.setKeyValueAt(0.0, 0.3)
        anim.setKeyValueAt(0.5, 1.0)
        anim.setKeyValueAt(1.0, 0.3)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.start()
        effect._pulse_anim = anim
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._pulse(index))
        timer.start(1200)
        self._timers.append(timer)

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        for dot in self.findChildren(QLabel):
            dot.setStyleSheet(
                f"background: {scheme.text_muted};border-radius: {self._dot_size // 2}px;"
            )


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


class TypingIndicator(QWidget):
    def __init__(self, scheme: ColorScheme = None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or get_scheme()
        self._setup_ui()
        self._start_animation()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2
        )
        layout.setSpacing(0)
        self._container = QWidget()
        self._container.setStyleSheet(
            f"background: {self._scheme.bg_secondary};"
            f"border-radius: {RADIUS.radius_lg}px;"
            f"padding: {SPACING.space_2}px {SPACING.space_3}px;"
        )
        container_layout = QHBoxLayout(self._container)
        container_layout.setContentsMargins(
            SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2
        )
        container_layout.setSpacing(SPACING.space_1)
        self._dots = []
        for _i in range(3):
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {self._scheme.text_muted};border-radius: 4px;")
            effect = QGraphicsOpacityEffect(dot)
            dot.setGraphicsEffect(effect)
            self._dots.append((dot, effect))
            container_layout.addWidget(dot)
        layout.addWidget(self._container)
        layout.addStretch()

    def _start_animation(self):
        for i, (_dot, _effect) in enumerate(self._dots):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda idx=i: self._pulse_dot(idx))
            timer.start(i * 250)
            self._timers = getattr(self, "_timers", [])
            self._timers.append(timer)

    def _pulse_dot(self, index):
        if index >= len(self._dots):
            return
        _, effect = self._dots[index]
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(800)
        anim.setKeyValueAt(0.0, 0.3)
        anim.setKeyValueAt(0.5, 1.0)
        anim.setKeyValueAt(1.0, 0.3)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.start()
        effect._pulse_anim = anim
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda idx=index: self._pulse_dot(idx))
        timer.start(1000)
        if not hasattr(self, "_timers"):
            self._timers = []
        self._timers.append(timer)

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._container.setStyleSheet(
            f"background: {scheme.bg_secondary};border-radius: {RADIUS.radius_lg}px;"
        )
        for dot, _ in self._dots:
            dot.setStyleSheet(f"background: {scheme.text_muted};border-radius: 4px;")


class ShimmerOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._animate)
        self.hide()

    def start(self):
        self._offset = 0
        self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _animate(self):
        self._offset = (self._offset + 2) % (self.width() + 200) if self.width() > 0 else 0
        self.update()

    def paintEvent(self, event):
        if not self.isVisible():
            return
        from PySide6.QtGui import QLinearGradient, QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(self._offset - 100, 0, self._offset + 100, 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 40))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(self.rect(), gradient)
        painter.end()
