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
# LIGHT THEME (Ollama-style - clean, white)
# ============================================================
LIGHT_SCHEME = ColorScheme(
    # Backgrounds
    bg_primary=COLORS.gray_0,  # #FFFFFF
    bg_secondary=COLORS.gray_50,  # #FAFAFA
    bg_tertiary=COLORS.gray_100,  # #F5F5F5
    bg_hover=COLORS.gray_100,  # #F5F5F5
    bg_active=COLORS.gray_200,  # #E5E5E5
    bg_inverse=COLORS.gray_900,  # #171717
    # Text
    text_primary=COLORS.gray_900,  # #171717
    text_secondary=COLORS.gray_600,  # #525252
    text_muted=COLORS.gray_400,  # #A3A3A3
    text_inverse=COLORS.gray_0,  # #FFFFFF
    text_on_accent=COLORS.gray_0,  # #FFFFFF
    # Accent (preto para estilo Ollama)
    accent_primary=COLORS.gray_900,  # #171717
    accent_hover=COLORS.gray_800,  # #262626
    accent_pressed=COLORS.gray_700,  # #404040
    accent_subtle=COLORS.gray_100,  # #F5F5F5
    accent_text=COLORS.gray_0,  # #FFFFFF
    # Borders
    border_subtle=COLORS.gray_100,  # #F5F5F5
    border_default=COLORS.gray_200,  # #E5E5E5
    border_strong=COLORS.gray_300,  # #D4D4D4
    border_focus=COLORS.gray_900,  # #171717
    border_error=COLORS.error_500,  # #EF4444
    # Semantic
    success=COLORS.success_600,  # #16A34A
    success_bg=COLORS.success_50,  # #F0FDF4
    success_text=COLORS.success_700,  # #15803D
    warning=COLORS.warning_600,  # #D97706
    warning_bg=COLORS.warning_50,  # #FFFBEB
    warning_text=COLORS.warning_700,  # #B45309
    error=COLORS.error_600,  # #DC2626
    error_bg=COLORS.error_50,  # #FEF2F2
    error_text=COLORS.error_700,  # #B91C1C
    info=COLORS.info_600,  # #2563EB
    info_bg=COLORS.info_50,  # #EFF6FF
    info_text=COLORS.info_700,  # #1D4ED8
    # Chat Bubbles
    user_bubble_bg=COLORS.gray_900,  # #171717
    user_bubble_text=COLORS.gray_0,  # #FFFFFF
    assistant_bubble_bg=COLORS.gray_50,  # #FAFAFA
    assistant_bubble_text=COLORS.gray_900,  # #171717
    # Code
    code_bg=COLORS.gray_100,  # #F5F5F5
    code_text=COLORS.gray_900,  # #171717
    code_border=COLORS.gray_200,  # #E5E5E5
    # Scrollbar
    scrollbar_bg=COLORS.gray_0,  # #FFFFFF
    scrollbar_handle=COLORS.gray_300,  # #D4D4D4
    scrollbar_handle_hover=COLORS.gray_400,  # #A3A3A3
    # Shadows
    shadow_1=SHADOWS.shadow_sm,
    shadow_2=SHADOWS.shadow_md,
    shadow_3=SHADOWS.shadow_lg,
)


# ============================================================
# DARK THEME (GitHub Dark / VS Code style)
# ============================================================
DARK_SCHEME = ColorScheme(
    # Backgrounds
    bg_primary="#0D1117",
    bg_secondary="#161B22",
    bg_tertiary="#21262D",
    bg_hover="#30363D",
    bg_active="#1F6FEB",
    bg_inverse="#E6EDF3",
    # Text
    text_primary="#E6EDF3",
    text_secondary="#8B949E",
    text_muted="#484F58",
    text_inverse="#0D1117",
    text_on_accent="#FFFFFF",
    # Accent
    accent_primary="#58A6FF",
    accent_hover="#79C0FF",
    accent_pressed="#388BF0",
    accent_subtle="#1A3A5C",
    accent_text="#0D1117",
    # Borders
    border_subtle="#21262D",
    border_default="#30363D",
    border_strong="#484F58",
    border_focus="#58A6FF",
    border_error="#F85149",
    # Semantic
    success="#3FB950",
    success_bg="#163D2A",
    success_text="#7EE787",
    warning="#D29922",
    warning_bg="#3D2E00",
    warning_text="#E3B341",
    error="#F85149",
    error_bg="#4D1A1A",
    error_text="#FFA198",
    info="#58A6FF",
    info_bg="#1A3A5C",
    info_text="#79C0FF",
    # Chat Bubbles
    user_bubble_bg="#007AFF",
    user_bubble_text="#FFFFFF",
    assistant_bubble_bg="#1E1E1E",
    assistant_bubble_text="#E6EDF3",
    # Code
    code_bg="#161B22",
    code_text="#E6EDF3",
    code_border="#30363D",
    # Scrollbar
    scrollbar_bg="#0D1117",
    scrollbar_handle="#30363D",
    scrollbar_handle_hover="#484F58",
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
