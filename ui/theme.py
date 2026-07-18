from dataclasses import dataclass
from enum import Enum


class ThemeMode(Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


@dataclass
class ColorScheme:
    # Backgrounds
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_hover: str
    bg_active: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str
    text_inverse: str

    # Accent
    accent_primary: str
    accent_hover: str
    accent_pressed: str

    # Borders
    border_subtle: str
    border_default: str
    border_strong: str

    # Semantic
    success: str
    success_bg: str
    warning: str
    warning_bg: str
    error: str
    error_bg: str
    info: str
    info_bg: str

    # User/Assistant bubbles
    user_bubble_bg: str
    user_bubble_text: str
    assistant_bubble_bg: str
    assistant_bubble_text: str

    # Code
    code_bg: str
    code_text: str
    code_border: str

    # Scrollbar
    scrollbar_bg: str
    scrollbar_handle: str
    scrollbar_handle_hover: str

    # Shadows
    shadow_1: str
    shadow_2: str
    shadow_3: str


# Ollama-style all-white light theme (DEFAULT)
LIGHT_SCHEME = ColorScheme(
    bg_primary="#FFFFFF",
    bg_secondary="#FFFFFF",
    bg_tertiary="#F7F7F8",
    bg_hover="#F0F0F1",
    bg_active="#E8E8EA",

    text_primary="#1A1A1B",
    text_secondary="#6E6E73",
    text_muted="#9E9EA3",
    text_inverse="#FFFFFF",

    accent_primary="#000000",
    accent_hover="#1A1A1A",
    accent_pressed="#333333",

    border_subtle="#E5E5E7",
    border_default="#E5E5E7",
    border_strong="#D1D1D6",

    success="#008000",
    success_bg="#E8F5E9",
    warning="#B8860B",
    warning_bg="#FFF8E1",
    error="#D32F2F",
    error_bg="#FDEDEC",
    info="#0066CC",
    info_bg="#E3F2FD",

    user_bubble_bg="#000000",
    user_bubble_text="#FFFFFF",
    assistant_bubble_bg="#F7F7F8",
    assistant_bubble_text="#1A1A1B",

    code_bg="#F7F7F8",
    code_text="#1A1A1B",
    code_border="#E5E5E7",

    scrollbar_bg="#FFFFFF",
    scrollbar_handle="#D1D1D6",
    scrollbar_handle_hover="#9E9EA3",

    shadow_1="rgba(0, 0, 0, 0.04)",
    shadow_2="rgba(0, 0, 0, 0.08)",
    shadow_3="rgba(0, 0, 0, 0.12)",
)


# Dark theme (alternative)
DARK_SCHEME = ColorScheme(
    bg_primary="#0D1117",
    bg_secondary="#161B22",
    bg_tertiary="#21262D",
    bg_hover="#30363D",
    bg_active="#1F6FEB",

    text_primary="#E6EDF3",
    text_secondary="#8B949E",
    text_muted="#484F58",
    text_inverse="#0D1117",

    accent_primary="#58A6FF",
    accent_hover="#79C0FF",
    accent_pressed="#388BF0",

    border_subtle="#21262D",
    border_default="#30363D",
    border_strong="#484F58",

    success="#3FB950",
    success_bg="#163D2A",
    warning="#D29922",
    warning_bg="#3D2E00",
    error="#F85149",
    error_bg="#4D1A1A",
    info="#58A6FF",
    info_bg="#1A3A5C",

    user_bubble_bg="#007AFF",
    user_bubble_text="#FFFFFF",
    assistant_bubble_bg="#1E1E1E",
    assistant_bubble_text="#E6EDF3",

    code_bg="#161B22",
    code_text="#E6EDF3",
    code_border="#30363D",

    scrollbar_bg="#0D1117",
    scrollbar_handle="#30363D",
    scrollbar_handle_hover="#484F58",

    shadow_1="rgba(0, 0, 0, 0.2)",
    shadow_2="rgba(0, 0, 0, 0.3)",
    shadow_3="rgba(0, 0, 0, 0.4)",
)


def get_stylesheet(scheme: ColorScheme) -> str:
    return f"""
/* ===== BASE ===== */
QMainWindow, QWidget {{
    background-color: {scheme.bg_primary};
    color: {scheme.text_primary};
    font-family: 'Segoe UI', 'Segoe UI Variable', system-ui, sans-serif;
    font-size: 14px;
}}

QLabel {{
    color: {scheme.text_primary};
}}

/* ===== SCROLLBARS ===== */
QScrollBar:vertical {{
    background: {scheme.scrollbar_bg};
    width: 8px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {scheme.scrollbar_handle};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {scheme.scrollbar_handle_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* Horizontal */
QScrollBar:horizontal {{
    background: {scheme.scrollbar_bg};
    height: 8px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {scheme.scrollbar_handle};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {scheme.scrollbar_handle_hover};
}}

/* ===== BUTTONS ===== */
QPushButton {{
    background-color: {scheme.bg_secondary};
    border: 1px solid {scheme.border_default};
    border-radius: 10px;
    color: {scheme.text_primary};
    padding: 8px 16px;
    font-weight: 500;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {scheme.bg_hover};
    border-color: {scheme.border_strong};
}}
QPushButton:pressed {{
    background-color: {scheme.accent_pressed};
    border-color: {scheme.accent_pressed};
    color: {scheme.text_inverse};
}}
QPushButton:disabled {{
    background-color: {scheme.bg_secondary};
    border-color: {scheme.border_subtle};
    color: {scheme.text_muted};
}}

/* Primary button */
QPushButton[primary="true"] {{
    background-color: {scheme.accent_primary};
    border-color: {scheme.accent_primary};
    color: {scheme.text_inverse};
}}
QPushButton[primary="true"]:hover {{
    background-color: {scheme.accent_hover};
    border-color: {scheme.accent_hover};
}}
QPushButton[primary="true"]:pressed {{
    background-color: {scheme.accent_pressed};
}}

/* Icon button */
QPushButton[icon="true"] {{
    padding: 8px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    border-radius: 10px;
}}

/* ===== INPUT ===== */
QLineEdit, QTextEdit {{
    background-color: {scheme.bg_secondary};
    border: 1px solid {scheme.border_default};
    border-radius: 10px;
    color: {scheme.text_primary};
    padding: 10px 14px;
    font-size: 14px;
    selection-background-color: {scheme.accent_primary}40;
}}
QLineEdit:focus, QTextEdit:focus {{
    border-color: {scheme.accent_primary};
    outline: none;
}}
QLineEdit::placeholder {{
    color: {scheme.text_muted};
}}

/* ===== COMBOBOX ===== */
QComboBox {{
    background-color: {scheme.bg_secondary};
    border: 1px solid {scheme.border_default};
    border-radius: 10px;
    color: {scheme.text_primary};
    padding: 8px 14px;
    padding-right: 32px;
    min-width: 180px;
}}
QComboBox:hover {{
    border-color: {scheme.border_strong};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {scheme.bg_secondary};
    border: 1px solid {scheme.border_default};
    color: {scheme.text_primary};
    selection-background-color: {scheme.accent_primary}30;
    outline: none;
    padding: 4px;
}}

/* ===== TOOLTIP ===== */
QToolTip {{
    background-color: {scheme.bg_tertiary};
    color: {scheme.text_primary};
    border: 1px solid {scheme.border_default};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
}}

/* ===== SEPARATOR ===== */
QFrame[frameShape="4"] {{  /* HLine */
    background-color: {scheme.border_subtle};
    max-height: 1px;
    border: none;
}}
QFrame[frameShape="5"] {{  /* VLine */
    background-color: {scheme.border_subtle};
    max-width: 1px;
    border: none;
}}

/* ===== MENU ===== */
QMenu {{
    background-color: {scheme.bg_secondary};
    border: 1px solid {scheme.border_default};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 24px;
    border-radius: 6px;
    color: {scheme.text_primary};
}}
QMenu::item:selected {{
    background-color: {scheme.accent_primary}30;
}}
QMenu::separator {{
    height: 1px;
    background: {scheme.border_subtle};
    margin: 4px 8px;
}}

/* ===== DIALOG ===== */
QDialog {{
    background-color: {scheme.bg_primary};
    border: 1px solid {scheme.border_default};
    border-radius: 12px;
}}

/* ===== SPLITTER ===== */
QSplitter::handle {{
    background: {scheme.border_subtle};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:vertical {{
    height: 1px;
}}
QSplitter::handle:hover {{
    background: {scheme.border_default};
}}

/* ===== INPUT CONTAINER ===== */
#inputContainer {{
    background: {scheme.bg_secondary};
    border: 1px solid {scheme.border_default};
    border-radius: 24px;
}}

/* ===== TREE/LIST VIEW (Sidebar) ===== */
QTreeView, QListView {{
    background-color: {scheme.bg_primary};
    border: none;
    outline: none;
    color: {scheme.text_primary};
}}
QTreeView::item, QListView::item {{
    padding: 8px 12px;
    border-radius: 8px;
    margin: 2px 4px;
}}
QTreeView::item:hover, QListView::item:hover {{
    background-color: {scheme.bg_hover};
}}
QTreeView::item:selected, QListView::item:selected {{
    background-color: {scheme.accent_primary}30;
    color: {scheme.accent_primary};
}}

/* ===== TAB WIDGET ===== */
QTabWidget::pane {{
    border: 1px solid {scheme.border_default};
    border-radius: 8px;
    background: {scheme.bg_primary};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    border: none;
    padding: 10px 20px;
    margin-right: 4px;
    border-radius: 8px;
    color: {scheme.text_secondary};
    font-weight: 500;
}}
QTabBar::tab:hover {{
    background: {scheme.bg_hover};
    color: {scheme.text_primary};
}}
QTabBar::tab:selected {{
    background: {scheme.accent_primary}20;
    color: {scheme.accent_primary};
}}
"""

