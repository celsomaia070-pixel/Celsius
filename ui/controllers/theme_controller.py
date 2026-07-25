"""
ThemeController - Gerencia temas (light/dark) e propagação.
"""
from PySide6.QtCore import QObject, Signal

from ui.theme import ThemeMode, scheme_from_name, get_stylesheet


class ThemeController(QObject):
    """Controller para gerenciamento de temas."""

    theme_changed = Signal(str)  # ThemeMode value

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = ThemeMode.LIGHT

    @property
    def mode(self):
        return self._mode

    def toggle(self):
        self._mode = ThemeMode.DARK if self._mode == ThemeMode.LIGHT else ThemeMode.LIGHT
        self.theme_changed.emit(self._mode.value)
        return self._mode

    def set_mode(self, mode: ThemeMode):
        self._mode = mode
        self.theme_changed.emit(mode.value)

    def get_scheme(self):
        return scheme_from_name(self._mode.value)

    def propagate(self, *components):
        """Propaga scheme para componentes."""
        scheme = self.get_scheme()
        for comp in components:
            if hasattr(comp, 'set_scheme'):
                comp.set_scheme(scheme)

    def apply_theme(self, window):
        """Aplica tema à janela principal."""
        scheme = self.get_scheme()
        window.setStyleSheet(get_stylesheet(scheme))
        self.propagate(
            window.sidebar,
            window.chat_view,
            window.input_area,
            window.inventory_panel,
            window.kanban_container,
        )
        if hasattr(window, 'palette_manager'):
            window.palette_manager.set_scheme(scheme)

        # Update theme button icon
        if hasattr(window, 'theme_btn'):
            is_dark = self._mode == ThemeMode.DARK
            from ui.icons import icon
            window.theme_btn.setIcon(icon("sun" if is_dark else "moon", scheme.text_secondary))