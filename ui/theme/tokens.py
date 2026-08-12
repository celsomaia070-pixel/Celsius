"""
Design Tokens - Fonte única da verdade para o sistema de design.
Todos os valores de design (cores, espaçamento, tipografia, etc.) são definidos aqui.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ColorTokens:
    """Tokens de cor semânticos (referenciam cores primitivas)."""

    # Primitive colors (escala 0-900)
    gray_0: str = "#FFFFFF"
    gray_50: str = "#FAFAFA"
    gray_100: str = "#F5F5F5"
    gray_200: str = "#E5E5E5"
    gray_300: str = "#D4D4D4"
    gray_400: str = "#A3A3A3"
    gray_500: str = "#737373"
    gray_600: str = "#525252"
    gray_700: str = "#404040"
    gray_800: str = "#262626"
    gray_900: str = "#171717"
    gray_950: str = "#0A0A0A"

    # Brand colors (escala 0-900)
    brand_50: str = "#F0F9FF"
    brand_100: str = "#E0F2FE"
    brand_200: str = "#BAE6FD"
    brand_300: str = "#7DD3FC"
    brand_400: str = "#38BDF8"
    brand_500: str = "#0EA5E9"
    brand_600: str = "#0284C7"
    brand_700: str = "#0369A1"
    brand_800: str = "#075985"
    brand_900: str = "#0C4A6E"

    # Accent (para ações primárias)
    accent_50: str = "#F8FAFC"
    accent_100: str = "#F1F5F9"
    accent_200: str = "#E2E8F0"
    accent_300: str = "#CBD5E1"
    accent_400: str = "#94A3B8"
    accent_500: str = "#64748B"
    accent_600: str = "#475569"
    accent_700: str = "#334155"
    accent_800: str = "#1E293B"
    accent_900: str = "#0F172A"

    # Semantic colors
    success_50: str = "#F0FDF4"
    success_100: str = "#DCFCE7"
    success_500: str = "#22C55E"
    success_600: str = "#16A34A"
    success_700: str = "#15803D"

    warning_50: str = "#FFFBEB"
    warning_100: str = "#FEF3C7"
    warning_500: str = "#F59E0B"
    warning_600: str = "#D97706"
    warning_700: str = "#B45309"

    error_50: str = "#FEF2F2"
    error_100: str = "#FEE2E2"
    error_500: str = "#EF4444"
    error_600: str = "#DC2626"
    error_700: str = "#B91C1C"

    info_50: str = "#EFF6FF"
    info_100: str = "#DBEAFE"
    info_500: str = "#3B82F6"
    info_600: str = "#2563EB"
    info_700: str = "#1D4ED8"

    # Celsius Project AI - identidade compartilhada com o site
    celsius_page: str = "#F4F7F6"
    celsius_surface: str = "#FFFFFF"
    celsius_surface_soft: str = "#EAF1EF"
    celsius_ink: str = "#14211F"
    celsius_muted: str = "#52615E"
    celsius_line: str = "#CFDBD7"
    celsius_primary: str = "#087E72"
    celsius_primary_strong: str = "#05645B"
    celsius_green: str = "#237B4B"
    celsius_coral: str = "#C9463C"
    celsius_gold: str = "#9A6B13"
    celsius_blue: str = "#286FA1"


@dataclass(frozen=True)
class SpacingTokens:
    """Escala de espaçamento baseada em 4px."""

    space_0: int = 0
    space_1: int = 4
    space_2: int = 8
    space_3: int = 12
    space_4: int = 16
    space_5: int = 20
    space_6: int = 24
    space_8: int = 32
    space_10: int = 40
    space_12: int = 48
    space_16: int = 64
    space_20: int = 80
    space_24: int = 96


@dataclass(frozen=True)
class RadiusTokens:
    """Raio de borda."""

    radius_none: int = 0
    radius_sm: int = 4
    radius_md: int = 6
    radius_lg: int = 8
    radius_xl: int = 8
    radius_2xl: int = 8
    radius_full: int = 9999


@dataclass(frozen=True)
class TypographyTokens:
    """Tokens de tipografia."""

    # Font families
    font_sans: str = "Segoe UI"
    font_mono: str = "JetBrains Mono"
    font_fallback_sans: str = "Segoe UI, system-ui, -apple-system, sans-serif"
    font_fallback_mono: str = "Consolas, 'Courier New', monospace"

    # Font sizes (px)
    text_xs: int = 11
    text_sm: int = 12
    text_base: int = 13
    text_lg: int = 14
    text_xl: int = 16
    text_2xl: int = 18
    text_3xl: int = 22
    text_4xl: int = 28

    # Font weights
    weight_normal: int = 400
    weight_medium: int = 500
    weight_semibold: int = 600
    weight_bold: int = 700

    # Line heights
    leading_tight: float = 1.25
    leading_normal: float = 1.5
    leading_relaxed: float = 1.625


@dataclass(frozen=True)
class ShadowTokens:
    """Tokens de sombra (elevation)."""

    shadow_none: str = "none"
    shadow_sm: str = "0 1px 2px rgba(0, 0, 0, 0.05)"
    shadow_md: str = "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1)"
    shadow_lg: str = "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)"
    shadow_xl: str = "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)"
    shadow_inner: str = "inset 0 2px 4px rgba(0, 0, 0, 0.05)"


@dataclass(frozen=True)
class BorderTokens:
    """Tokens de borda."""

    width_thin: int = 1
    width_normal: int = 1
    width_thick: int = 2
    width_focus: int = 2


@dataclass(frozen=True)
class TransitionTokens:
    """Tokens de transição/animação."""

    duration_fast: int = 150
    duration_normal: int = 200
    duration_slow: int = 300
    easing_ease_out: str = "cubic-bezier(0.4, 0, 0.2, 1)"
    easing_ease_in_out: str = "cubic-bezier(0.4, 0, 0.6, 1)"


@dataclass(frozen=True)
class ZIndexTokens:
    """Tokens de z-index."""

    z_hide: int = -1
    z_base: int = 0
    z_dropdown: int = 100
    z_sticky: int = 200
    z_fixed: int = 300
    z_modal_backdrop: int = 400
    z_modal: int = 500
    z_popover: int = 600
    z_tooltip: int = 700
    z_toast: int = 800


@dataclass(frozen=True)
class BreakpointTokens:
    """Breakpoints para layouts responsivos (se necessário no futuro)."""

    sm: int = 640
    md: int = 768
    lg: int = 1024
    xl: int = 1280
    xxl: int = 1536


# Instâncias globais (singleton tokens)
COLORS: Final = ColorTokens()
SPACING: Final = SpacingTokens()
RADIUS: Final = RadiusTokens()
TYPOGRAPHY: Final = TypographyTokens()
SHADOWS: Final = ShadowTokens()
BORDERS: Final = BorderTokens()
TRANSITIONS: Final = TransitionTokens()
Z_INDEX: Final = ZIndexTokens()
BREAKPOINTS: Final = BreakpointTokens()


# Funções utilitárias
def px(value: int) -> str:
    """Converte int para string com px."""
    return f"{value}px"


def rem(value: int, base: int = 16) -> str:
    """Converte px para rem."""
    return f"{value / base:.3f}rem"


@dataclass(frozen=True)
class Tokens:
    """Container unificado para todos os design tokens."""

    colors: Final = COLORS
    spacing: Final = SPACING
    borderRadius: Final = RADIUS
    typography: Final = TYPOGRAPHY
    shadows: Final = SHADOWS
    borders: Final = BORDERS
    transitions: Final = TRANSITIONS
    zIndex: Final = Z_INDEX
    breakpoints: Final = BREAKPOINTS


tokens = Tokens()
