"""Theme - Sistema de temas e tokens do Celsius."""

from ui.theme.icons import create_icon, icon, list_icons
from ui.theme.schemes import DARK_SCHEME, LIGHT_SCHEME, SCHEMES, ColorScheme, ThemeMode, get_scheme
from ui.theme.stylesheet import get_stylesheet
from ui.theme.tokens import Tokens, tokens


def scheme_from_name(name: str) -> ColorScheme:
    """Retorna um ColorScheme a partir do nome (light/dark)."""
    try:
        mode = ThemeMode(name)
    except ValueError:
        mode = ThemeMode.LIGHT
    return get_scheme(mode)


__all__ = [
    "ColorScheme",
    "ThemeMode",
    "get_scheme",
    "SCHEMES",
    "LIGHT_SCHEME",
    "DARK_SCHEME",
    "tokens",
    "Tokens",
    "get_stylesheet",
    "icon",
    "create_icon",
    "list_icons",
    "scheme_from_name",
]
