"""
Theme Manager - Gerenciador de temas com persistência.
Gerencia troca de tema em tempo real e salva preferências.
"""

import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ui.theme.schemes import SCHEMES, ColorScheme, ThemeMode, get_scheme


class ThemeManager(QObject):
    """Gerenciador central de temas.

    Features:
    - Troca de tema em tempo real
    - Persistência em arquivo JSON
    - Sinal para notificar mudanças
    - Suporte a tema do sistema
    """

    scheme_changed = Signal(str)  # Emite o nome do novo tema

    _CONFIG_DIR = Path.home() / ".celsius"
    _CONFIG_FILE = _CONFIG_DIR / "theme.json"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_name: ThemeMode = ThemeMode.LIGHT
        self._current_scheme: ColorScheme = get_scheme(ThemeMode.LIGHT)
        self._system_follow: bool = False
        self._listeners: list[QObject] = []
        self._load()

    @property
    def name(self) -> str:
        return self._current_name

    @property
    def scheme(self) -> ColorScheme:
        return self._current_scheme

    @property
    def system_follow(self) -> bool:
        return self._system_follow

    def set_system_follow(self, enabled: bool):
        """Define se o tema deve seguir o tema do sistema."""
        self._system_follow = enabled
        self._save()

    def register_listener(self, widget: QObject):
        """Registra um widget para receber notificações de mudança de tema."""
        if widget not in self._listeners:
            self._listeners.append(widget)

    def unregister_listener(self, widget: QObject):
        """Remove um widget da lista de listeners."""
        if widget in self._listeners:
            self._listeners.remove(widget)

    def set_scheme(self, mode: ThemeMode):
        """Troca o tema e notifica todos os listeners.

        Args:
            mode: Modo do tema (ThemeMode.LIGHT ou ThemeMode.DARK)
        """
        if mode not in SCHEMES:
            return

        self._current_name = mode
        self._current_scheme = get_scheme(mode)
        self._save()
        self._notify_listeners()
        self.scheme_changed.emit(mode.value)

    def toggle(self):
        """Alterna entre light e dark."""
        new_mode = ThemeMode.DARK if self._current_name == ThemeMode.LIGHT else ThemeMode.LIGHT
        self.set_scheme(new_mode)

    def get_available_schemes(self) -> list[str]:
        """Retorna lista de temas disponíveis."""
        return [mode.value for mode in SCHEMES]

    def _notify_listeners(self):
        """Notifica todos os widgets registrados sobre a mudança de tema."""
        for widget in self._listeners:
            if hasattr(widget, "set_scheme"):
                widget.set_scheme(self._current_scheme)

    def _load(self):
        """Carrega tema salvo do disco."""
        try:
            if self._CONFIG_FILE.exists():
                data = json.loads(self._CONFIG_FILE.read_text(encoding="utf-8"))
                name = data.get("scheme", "light")
                try:
                    mode = ThemeMode(name)
                except ValueError:
                    mode = ThemeMode.LIGHT
                self._current_name = mode
                self._current_scheme = get_scheme(mode)
                self._system_follow = data.get("system_follow", False)
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self):
        """Salva tema atual no disco."""
        try:
            self._CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "scheme": self._current_name.value,
                "system_follow": self._system_follow,
            }
            self._CONFIG_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass
