"""Theme - Sistema de temas e tokens do Celsius."""

from ui.theme.schemes import ColorScheme, ThemeMode, get_scheme, SCHEMES, LIGHT_SCHEME, DARK_SCHEME
from ui.theme.tokens import tokens, Tokens
from ui.theme.stylesheet import get_stylesheet
from ui.theme.icons import icon, create_icon, list_icons


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