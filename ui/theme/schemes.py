"""
Color Schemes - Esquemas de cores Light/Dark baseados nos design tokens.
"""

from dataclasses import dataclass, field
from enum import Enum

from ui.theme.tokens import (
    BORDERS,
    COLORS,
    RADIUS,
    SHADOWS,
    SPACING,
    TRANSITIONS,
    TYPOGRAPHY,
    Z_INDEX,
)


class ThemeMode(Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


@dataclass(frozen=True)
class ColorScheme:
    """Esquema de cores completo para um tema."""

    # === Backgrounds ===
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_hover: str
    bg_active: str
    bg_inverse: str

    # === Text ===
    text_primary: str
    text_secondary: str
    text_muted: str
    text_inverse: str
    text_on_accent: str

    # === Accent / Brand ===
    accent_primary: str
    accent_hover: str
    accent_pressed: str
    accent_subtle: str
    accent_text: str

    # === Borders ===
    border_subtle: str
    border_default: str
    border_strong: str
    border_focus: str
    border_error: str

    # === Semantic ===
    success: str
    success_bg: str
    success_text: str

    warning: str
    warning_bg: str
    warning_text: str

    error: str
    error_bg: str
    error_text: str

    info: str
    info_bg: str
    info_text: str

    # === Chat Bubbles ===
    user_bubble_bg: str
    user_bubble_text: str
    assistant_bubble_bg: str
    assistant_bubble_text: str

    # === Code ===
    code_bg: str
    code_text: str
    code_border: str

    # === Scrollbar ===
    scrollbar_bg: str
    scrollbar_handle: str
    scrollbar_handle_hover: str

    # === Shadows ===
    shadow_1: str
    shadow_2: str
    shadow_3: str

    # === Tokens reference (não serializados) ===
    spacing: object = field(default=SPACING, repr=False)
    radius: object = field(default=RADIUS, repr=False)
    typography: object = field(default=TYPOGRAPHY, repr=False)
    shadows: object = field(default=SHADOWS, repr=False)
    borders: object = field(default=BORDERS, repr=False)
    transitions: object = field(default=TRANSITIONS, repr=False)
    z_index: object = field(default=Z_INDEX, repr=False)


# ============================================================
# LIGHT THEME (Celsius Project AI)
# ============================================================
LIGHT_SCHEME = ColorScheme(
    # Backgrounds
    bg_primary=COLORS.celsius_page,
    bg_secondary=COLORS.celsius_surface,
    bg_tertiary=COLORS.celsius_surface_soft,
    bg_hover="#E1ECE9",
    bg_active="#D4E8E4",
    bg_inverse=COLORS.celsius_ink,
    # Text
    text_primary=COLORS.celsius_ink,
    text_secondary=COLORS.celsius_muted,
    text_muted="#7C8A86",
    text_inverse=COLORS.celsius_surface,
    text_on_accent=COLORS.celsius_surface,
    # Accent
    accent_primary=COLORS.celsius_primary,
    accent_hover=COLORS.celsius_primary_strong,
    accent_pressed="#044E47",
    accent_subtle="#DFF1ED",
    accent_text=COLORS.celsius_surface,
    # Borders
    border_subtle="#DDE6E3",
    border_default=COLORS.celsius_line,
    border_strong="#A9BBB5",
    border_focus="#E59B2D",
    border_error=COLORS.celsius_coral,
    # Semantic
    success=COLORS.celsius_green,
    success_bg="#E2F1E8",
    success_text="#185E39",
    warning=COLORS.celsius_gold,
    warning_bg="#F7EDD7",
    warning_text="#76500D",
    error=COLORS.celsius_coral,
    error_bg="#F8E3E1",
    error_text="#94332C",
    info=COLORS.celsius_blue,
    info_bg="#E0ECF4",
    info_text="#1F587F",
    # Chat Bubbles
    user_bubble_bg="#DFF1ED",
    user_bubble_text=COLORS.celsius_ink,
    assistant_bubble_bg=COLORS.celsius_surface,
    assistant_bubble_text=COLORS.celsius_ink,
    # Code
    code_bg="#EDF3F1",
    code_text=COLORS.celsius_ink,
    code_border=COLORS.celsius_line,
    # Scrollbar
    scrollbar_bg=COLORS.celsius_page,
    scrollbar_handle="#B7C8C3",
    scrollbar_handle_hover="#8FA49E",
    # Shadows
    shadow_1=SHADOWS.shadow_sm,
    shadow_2=SHADOWS.shadow_md,
    shadow_3=SHADOWS.shadow_lg,
)


# ============================================================
# DARK THEME (Celsius Project AI)
# ============================================================
DARK_SCHEME = ColorScheme(
    # Backgrounds
    bg_primary="#101715",
    bg_secondary="#18211F",
    bg_tertiary="#202D2A",
    bg_hover="#283733",
    bg_active="#304A45",
    bg_inverse="#EDF5F2",
    # Text
    text_primary="#EDF5F2",
    text_secondary="#AABBB5",
    text_muted="#728780",
    text_inverse="#101715",
    text_on_accent="#FFFFFF",
    # Accent
    accent_primary="#42C6B7",
    accent_hover="#7ED8CE",
    accent_pressed="#2FA899",
    accent_subtle="#1D403B",
    accent_text="#101715",
    # Borders
    border_subtle="#293733",
    border_default="#344440",
    border_strong="#52655F",
    border_focus="#FFC267",
    border_error="#FF8178",
    # Semantic
    success="#69C58D",
    success_bg="#1D3D2A",
    success_text="#8DDBAA",
    warning="#E8B759",
    warning_bg="#453819",
    warning_text="#F2CC80",
    error="#FF8178",
    error_bg="#4A2623",
    error_text="#FFAAA4",
    info="#73B8E3",
    info_bg="#1D3545",
    info_text="#9BCFEE",
    # Chat Bubbles
    user_bubble_bg="#1D403B",
    user_bubble_text="#EDF5F2",
    assistant_bubble_bg="#18211F",
    assistant_bubble_text="#EDF5F2",
    # Code
    code_bg="#131D1A",
    code_text="#EDF5F2",
    code_border="#344440",
    # Scrollbar
    scrollbar_bg="#101715",
    scrollbar_handle="#344440",
    scrollbar_handle_hover="#52655F",
    # Shadows
    shadow_1="rgba(0, 0, 0, 0.2)",
    shadow_2="rgba(0, 0, 0, 0.3)",
    shadow_3="rgba(0, 0, 0, 0.4)",
)


# Mapping de modo para esquema
SCHEMES = {
    ThemeMode.LIGHT: LIGHT_SCHEME,
    ThemeMode.DARK: DARK_SCHEME,
}


def get_scheme(mode: ThemeMode = ThemeMode.LIGHT) -> ColorScheme:
    """Retorna o esquema de cores para o modo especificado."""
    if mode == ThemeMode.SYSTEM:
        return LIGHT_SCHEME
    return SCHEMES.get(mode, LIGHT_SCHEME)
