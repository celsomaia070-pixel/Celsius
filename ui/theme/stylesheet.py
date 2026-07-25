"""
Stylesheet Generator - Gera QSS a partir dos ColorScheme e tokens.
Fonte única de verdade para todos os estilos QSS da aplicação.
"""

from ui.theme.tokens import (
    SPACING, RADIUS, TYPOGRAPHY, SHADOWS, BORDERS, TRANSITIONS
)
from ui.theme.schemes import ColorScheme, ThemeMode


def px(value: int) -> str:
    return f"{value}px"


def _rgba_to_hex_with_alpha(color: str, alpha: float) -> str:
    """Converte hex para rgba string para QSS."""
    color = color.lstrip('#')
    if len(color) == 6:
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"
    return color


def generate_base_stylesheet(scheme: ColorScheme) -> str:
    """Gera o QSS base para a aplicação."""
    s = scheme
    sp = scheme.spacing
    rad = scheme.radius
    typo = scheme.typography
    sh = scheme.shadows
    bd = scheme.borders
    tr = scheme.transitions

    return f"""
/* ============================================================
   BASE STYLESHEET - Gerado a partir de design tokens
   Theme: {'Light' if s.bg_primary == '#FFFFFF' else 'Dark'}
   ============================================================ */

/* ----- Global ----- */
QMainWindow, QWidget {{
    background-color: {s.bg_primary};
    color: {s.text_primary};
    font-family: '{typo.font_sans}', {typo.font_fallback_sans};
    font-size: {px(typo.text_base)};
    font-weight: {typo.weight_normal};
}}

QLabel {{
    color: {s.text_primary};
    background: transparent;
    border: none;
}}

/* ----- Scrollbars ----- */
QScrollBar:vertical {{
    background: {s.scrollbar_bg};
    width: {px(8)};
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {s.scrollbar_handle};
    border-radius: {px(4)};
    min-height: {px(30)};
}}
QScrollBar::handle:vertical:hover {{
    background: {s.scrollbar_handle_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: {s.scrollbar_bg};
    height: {px(8)};
    margin: 0;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {s.scrollbar_handle};
    border-radius: {px(4)};
    min-width: {px(30)};
}}
QScrollBar::handle:horizontal:hover {{
    background: {s.scrollbar_handle_hover};
}}

/* ----- Buttons ----- */
QPushButton {{
    background-color: {s.bg_secondary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    color: {s.text_primary};
    padding: {px(sp.space_2)} {px(sp.space_4)};
    font-weight: {typo.weight_medium};
    font-size: {px(typo.text_sm)};
    min-height: {px(20)};
}}
QPushButton:hover {{
    background-color: {s.bg_hover};
    border-color: {s.border_strong};
}}
QPushButton:pressed {{
    background-color: {s.accent_pressed};
    border-color: {s.accent_pressed};
    color: {s.text_on_accent};
}}
QPushButton:disabled {{
    background-color: {s.bg_secondary};
    border-color: {s.border_subtle};
    color: {s.text_muted};
}}

/* Primary button */
QPushButton[primary="true"] {{
    background-color: {s.accent_primary};
    border-color: {s.accent_primary};
    color: {s.text_on_accent};
}}
QPushButton[primary="true"]:hover {{
    background-color: {s.accent_hover};
    border-color: {s.accent_hover};
}}
QPushButton[primary="true"]:pressed {{
    background-color: {s.accent_pressed};
}}

/* Icon button */
QPushButton[icon="true"] {{
    padding: {px(sp.space_2)};
    min-width: {px(36)};
    max-width: {px(36)};
    min-height: {px(36)};
    max-height: {px(36)};
    border-radius: {px(rad.radius_md)};
}}

/* Ghost button */
QPushButton[ghost="true"] {{
    background-color: transparent;
    border-color: transparent;
}}
QPushButton[ghost="true"]:hover {{
    background-color: {s.bg_hover};
}}

/* Danger button */
QPushButton[danger="true"] {{
    background-color: {s.error};
    border-color: {s.error};
    color: {s.error_text};
}}
QPushButton[danger="true"]:hover {{
    background-color: {s.error_bg};
    border-color: {s.error};
}}

/* ----- Inputs ----- */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {s.bg_secondary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    color: {s.text_primary};
    padding: {px(sp.space_2)} {px(sp.space_3)};
    font-size: {px(typo.text_base)};
    selection-background-color: {_rgba_to_hex_with_alpha(s.accent_primary, 0.25)};
    selection-color: {s.text_primary};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {s.border_focus};
    outline: none;
}}
QLineEdit::placeholder {{
    color: {s.text_muted};
}}

/* ----- ComboBox ----- */
QComboBox {{
    background-color: {s.bg_secondary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    color: {s.text_primary};
    padding: {px(sp.space_2)} {px(sp.space_3)};
    padding-right: {px(32)};
    min-width: {px(180)};
    font-size: {px(typo.text_sm)};
}}
QComboBox:hover {{
    border-color: {s.border_strong};
}}
QComboBox::drop-down {{
    border: none;
    width: {px(24)};
    subcontrol-origin: padding;
    subcontrol-position: top right;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: {px(5)} solid transparent;
    border-right: {px(5)} solid transparent;
    border-top: {px(6)} solid {s.text_secondary};
    margin-right: {px(8)};
}}
QComboBox QAbstractItemView {{
    background-color: {s.bg_secondary};
    border: {px(bd.width_normal)} solid {s.border_default};
    color: {s.text_primary};
    selection-background-color: {_rgba_to_hex_with_alpha(s.accent_primary, 0.18)};
    outline: none;
    padding: {px(sp.space_1)};
}}
QComboBox QAbstractItemView::item {{
    padding: {px(sp.space_2)} {px(sp.space_3)};
    border-radius: {px(rad.radius_sm)};
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {_rgba_to_hex_with_alpha(s.accent_primary, 0.18)};
    color: {s.accent_primary};
}}

/* ----- Tooltip ----- */
QToolTip {{
    background-color: {s.bg_tertiary};
    color: {s.text_primary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    padding: {px(sp.space_2)} {px(sp.space_3)};
    font-size: {px(typo.text_xs)};
}}

/* ----- Separator ----- */
QFrame[frameShape="4"] {{  /* HLine */
    background-color: {s.border_subtle};
    max-height: {px(1)};
    border: none;
}}
QFrame[frameShape="5"] {{  /* VLine */
    background-color: {s.border_subtle};
    max-width: {px(1)};
    border: none;
}}

/* ----- Menu ----- */
QMenu {{
    background-color: {s.bg_secondary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    padding: {px(sp.space_1)};
}}
QMenu::item {{
    padding: {px(sp.space_2)} {px(sp.space_5)};
    border-radius: {px(rad.radius_sm)};
    color: {s.text_primary};
}}
QMenu::item:selected {{
    background-color: {_rgba_to_hex_with_alpha(s.accent_primary, 0.18)};
}}
QMenu::separator {{
    height: {px(1)};
    background: {s.border_subtle};
    margin: {px(sp.space_1)} {px(sp.space_3)};
}}

/* ----- Dialog ----- */
QDialog {{
    background-color: {s.bg_primary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_lg)};
}}

/* ----- Splitter ----- */
QSplitter::handle {{
    background: {s.border_subtle};
}}
QSplitter::handle:horizontal {{
    width: {px(1)};
}}
QSplitter::handle:vertical {{
    height: {px(1)};
}}
QSplitter::handle:hover {{
    background: {s.border_default};
}}

/* ----- TabWidget ----- */
QTabWidget::pane {{
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    background: {s.bg_primary};
    top: -{px(1)};
}}
QTabBar::tab {{
    background: transparent;
    border: none;
    padding: {px(sp.space_2)} {px(sp.space_4)};
    margin-right: {px(sp.space_1)};
    border-radius: {px(rad.radius_md)};
    color: {s.text_secondary};
    font-weight: {typo.weight_medium};
    font-size: {px(typo.text_sm)};
}}
QTabBar::tab:hover {{
    background: {s.bg_hover};
    color: {s.text_primary};
}}
QTabBar::tab:selected {{
    background: {_rgba_to_hex_with_alpha(s.accent_primary, 0.12)};
    color: {s.accent_primary};
}}

/* ----- ListView / TreeView (Sidebar) ----- */
QListView, QTreeView {{
    background-color: {s.bg_primary};
    border: none;
    outline: none;
    color: {s.text_primary};
    show-decoration-selected: 1;
}}
QListView::item, QTreeView::item {{
    padding: {px(sp.space_2)} {px(sp.space_3)};
    border-radius: {px(rad.radius_md)};
    margin: {px(sp.space_1)} {px(sp.space_2)};
}}
QListView::item:hover, QTreeView::item:hover {{
    background-color: {s.bg_hover};
}}
QListView::item:selected, QTreeView::item:selected {{
    background-color: {_rgba_to_hex_with_alpha(s.accent_primary, 0.18)};
    color: {s.accent_primary};
}}

/* ----- ProgressBar ----- */
QProgressBar {{
    background-color: {s.bg_secondary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_full)};
    text-align: center;
    color: {s.text_primary};
    font-size: {px(typo.text_xs)};
    font-weight: {typo.weight_medium};
}}
QProgressBar::chunk {{
    background-color: {s.accent_primary};
    border-radius: {px(rad.radius_full)};
}}

/* ----- Slider ----- */
QSlider::groove:horizontal {{
    background: {s.bg_secondary};
    height: {px(4)};
    border-radius: {px(2)};
}}
QSlider::handle:horizontal {{
    background: {s.accent_primary};
    border: none;
    width: {px(16)};
    height: {px(16)};
    margin: -{px(6)} 0;
    border-radius: {px(8)};
}}
QSlider::handle:horizontal:hover {{
    background: {s.accent_hover};
}}

/* ----- CheckBox / RadioButton ----- */
QCheckBox, QRadioButton {{
    color: {s.text_primary};
    spacing: {px(sp.space_2)};
    font-size: {px(typo.text_sm)};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: {px(18)};
    height: {px(18)};
    border-radius: {px(rad.radius_sm)};
    border: {px(bd.width_normal)} solid {s.border_default};
    background: {s.bg_secondary};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {s.accent_primary};
    border-color: {s.accent_primary};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {s.border_strong};
}}

/* ----- SpinBox ----- */
QSpinBox, QDoubleSpinBox {{
    background-color: {s.bg_secondary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    color: {s.text_primary};
    padding: {px(sp.space_2)} {px(sp.space_3)};
    font-size: {px(typo.text_sm)};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {s.border_focus};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: {px(20)};
    border: none;
    background: transparent;
    border-radius: 0 {px(rad.radius_md)} 0 0;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: {px(20)};
    border: none;
    background: transparent;
    border-radius: 0 0 {px(rad.radius_md)} 0;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none;
    border-left: {px(4)} solid transparent;
    border-right: {px(4)} solid transparent;
    border-bottom: {px(5)} solid {s.text_secondary};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none;
    border-left: {px(4)} solid transparent;
    border-right: {px(4)} solid transparent;
    border-top: {px(5)} solid {s.text_secondary};
}}

/* ----- GroupBox ----- */
QGroupBox {{
    background: transparent;
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    margin-top: {px(sp.space_4)};
    padding-top: {px(sp.space_3)};
    font-weight: {typo.weight_semibold};
    color: {s.text_primary};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {px(sp.space_3)};
    padding: 0 {px(sp.space_1)};
    color: {s.text_secondary};
}}

/* ----- StatusBar ----- */
QStatusBar {{
    background: {s.bg_secondary};
    border-top: {px(bd.width_normal)} solid {s.border_default};
    color: {s.text_secondary};
    font-size: {px(typo.text_xs)};
}}

/* ----- ToolBar ----- */
QToolBar {{
    background: {s.bg_secondary};
    border: none;
    border-bottom: {px(bd.width_normal)} solid {s.border_default};
    spacing: {px(sp.space_2)};
    padding: {px(sp.space_1)} {px(sp.space_3)};
}}

/* ----- DockWidget ----- */
QDockWidget {{
    background: {s.bg_primary};
    titlebar-close-icon: url(close.svg);
    titlebar-normal-icon: url(undock.svg);
}}
QDockWidget::title {{
    background: {s.bg_secondary};
    padding: {px(sp.space_2)} {px(sp.space_3)};
    border-bottom: {px(bd.width_normal)} solid {s.border_default};
    color: {s.text_primary};
    font-weight: {typo.weight_medium};
}}

/* ----- ToolTip (custom) ----- */
#toolTip {{
    background-color: {s.bg_tertiary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    padding: {px(sp.space_2)} {px(sp.space_3)};
    color: {s.text_primary};
    font-size: {px(typo.text_xs)};
}}
"""


def generate_chat_stylesheet(scheme: ColorScheme) -> str:
    """Estilos específicos para componentes de chat."""
    s = scheme
    sp = scheme.spacing
    rad = scheme.radius
    typo = scheme.typography
    bd = scheme.borders

    return f"""
/* ============================================================
   CHAT COMPONENTS
   ============================================================ */

/* Message Bubble */
.MessageBubble {{
    background: transparent;
    border: none;
}}
.MessageBubble--user {{
    /* Alinhamento à direita via layout */
}}
.MessageBubble--assistant {{
    /* Alinhamento à esquerda via layout */
}}

/* Message Header */
.MessageBubble__header {{
    color: {s.text_secondary};
    font-size: {px(typo.text_xs)};
    font-weight: {typo.weight_medium};
    margin-bottom: {px(sp.space_1)};
}}

/* Message Content */
.MessageBubble__content {{
    color: {s.text_primary};
    font-size: {px(typo.text_base)};
    line-height: {typo.leading_relaxed};
    background: transparent;
    border: none;
}}

/* Code Block */
.MessageBubble__codeBlock {{
    background: {s.code_bg};
    border: {px(bd.width_normal)} solid {s.code_border};
    border-radius: {px(rad.radius_md)};
    padding: {px(sp.space_3)};
    margin: {px(sp.space_2)} 0;
    font-family: '{typo.font_mono}', {typo.font_fallback_mono};
    font-size: {px(typo.text_sm)};
    line-height: {typo.leading_normal};
    color: {s.code_text};
}}
.MessageBubble__codeBlock pre {{
    margin: 0;
    background: transparent;
    border: none;
}}
.MessageBubble__codeBlock code {{
    background: transparent;
    color: inherit;
    padding: 0;
}}
.MessageBubble__codeBlock .copy-btn {{
    background: {s.bg_tertiary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_sm)};
    color: {s.text_secondary};
    padding: {px(sp.space_1)} {px(sp.space_2)};
    font-size: {px(typo.text_xs)};
}}
.MessageBubble__codeBlock .copy-btn:hover {{
    background: {s.bg_hover};
    color: {s.text_primary};
}}

/* Inline Code */
.MessageBubble__inlineCode {{
    background: {s.code_bg};
    color: {s.accent_primary};
    padding: {px(2)} {px(sp.space_1)};
    border-radius: {px(rad.radius_sm)};
    font-family: '{typo.font_mono}', {typo.font_fallback_mono};
    font-size: {px(typo.text_sm)};
}}

/* Attachment Chip */
.MessageBubble__attachment {{
    background: {s.bg_secondary};
    border: {px(bd.width_normal)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    padding: {px(sp.space_1)} {px(sp.space_2)};
    margin: {px(sp.space_1)} 0;
}}
.MessageBubble__attachment--image {{
    border-radius: {px(rad.radius_md)};
    overflow: hidden;
}}

/* Thinking Indicator */
.ThinkingIndicator {{
    color: {s.text_muted};
    font-size: {px(typo.text_sm)};
    font-style: italic;
}}
.ThinkingIndicator__dots::after {{
    content: "";
    animation: thinking-dots 1.5s infinite;
}}
@keyframes thinking-dots {{
    0%, 20% {{ content: "."; }}
    40% {{ content: ".."; }}
    60% {{ content: "..."; }}
    80%, 100% {{ content: ""; }}
}}

/* Streaming Cursor */
.StreamingCursor {{
    display: inline-block;
    width: {px(2)};
    height: {px(1.2)}em;
    background: {s.accent_primary};
    margin-left: {px(2)};
    animation: blink 1.06s infinite;
}}
@keyframes blink {{
    0%, 50% {{ opacity: 1; }}
    51%, 100% {{ opacity: 0; }}
}}
"""


def generate_sidebar_stylesheet(scheme: ColorScheme) -> str:
    """Estilos específicos para sidebar."""
    s = scheme
    sp = scheme.spacing
    rad = scheme.radius
    typo = scheme.typography

    return f"""
/* ============================================================
   SIDEBAR COMPONENTS
   ============================================================ */

.Sidebar {{
    background: {s.bg_primary};
    border-right: {px(1)} solid {s.border_default};
}}

.Sidebar__header {{
    background: {s.bg_primary};
    border-bottom: {px(1)} solid {s.border_default};
    padding: {px(sp.space_3)} {px(sp.space_4)};
}}

.Sidebar__title {{
    font-size: {px(typo.text_xl)};
    font-weight: {typo.weight_bold};
    color: {s.text_primary};
}}

.Sidebar__tabBar {{
    background: {s.bg_primary};
    border-bottom: {px(1)} solid {s.border_default};
    padding: 0 {px(sp.space_2)};
}}

.Sidebar__tab {{
    background: transparent;
    border: none;
    border-bottom: {px(2)} solid transparent;
    padding: {px(sp.space_2)} {px(sp.space_3)};
    color: {s.text_muted};
    font-size: {px(typo.text_sm)};
    font-weight: {typo.weight_semibold};
    border-radius: {px(rad.radius_sm)} {px(rad.radius_sm)} 0 0;
}}
.Sidebar__tab:hover {{
    color: {s.text_primary};
    background: {s.bg_hover};
}}
.Sidebar__tab:checked {{
    color: {s.text_primary};
    border-bottom-color: {s.accent_primary};
    background: {_rgba_to_hex_with_alpha(s.accent_primary, 0.08)};
}}

.Sidebar__search {{
    margin: {px(sp.space_3)} {px(sp.space_3)} {px(sp.space_2)};
}}

.Sidebar__list {{
    background: transparent;
    border: none;
    outline: none;
    padding: {px(sp.space_1)} {px(sp.space_2)};
}}
.Sidebar__list::item {{
    padding: {px(sp.space_2)} {px(sp.space_3)};
    border-radius: {px(rad.radius_md)};
    margin: {px(sp.space_1)} {px(sp.space_1)};
    color: {s.text_primary};
}}
.Sidebar__list::item:hover {{
    background: {s.bg_hover};
}}
.Sidebar__list::item:selected {{
    background: {_rgba_to_hex_with_alpha(s.accent_primary, 0.18)};
    color: {s.accent_primary};
}}

.Sidebar__footer {{
    border-top: {px(1)} solid {s.border_default};
    background: {s.bg_primary};
    padding: {px(sp.space_3)};
}}

.Sidebar__actionBtn {{
    text-align: left;
    padding: {px(sp.space_2)} {px(sp.space_3)};
    border-radius: {px(rad.radius_md)};
    color: {s.text_secondary};
    font-size: {px(typo.text_sm)};
}}
.Sidebar__actionBtn:hover {{
    background: {s.bg_hover};
    color: {s.text_primary};
    border-color: {s.accent_primary};
}}
"""


def generate_inventory_stylesheet(scheme: ColorScheme) -> str:
    """Estilos específicos para inventory/kanban."""
    s = scheme
    sp = scheme.spacing
    rad = scheme.radius
    typo = scheme.typography

    return f"""
/* ============================================================
   INVENTORY / KANBAN COMPONENTS
   ============================================================ */

.InventoryPanel {{
    background: {s.bg_primary};
}}

.InventoryPanel__header {{
    background: {s.bg_primary};
    border-bottom: {px(1)} solid {s.border_default};
    padding: {px(sp.space_3)} {px(sp.space_4)};
}}

.InventoryPanel__title {{
    font-size: {px(typo.text_lg)};
    font-weight: {typo.weight_bold};
    color: {s.text_primary};
}}

.InventoryPanel__search {{
    margin: {px(sp.space_2)} {px(sp.space_3)};
}}

.InventoryPanel__tabs {{
    border-bottom: {px(1)} solid {s.border_default};
}}

.KanbanBoard {{
    background: {s.bg_secondary};
    border: none;
}}

.KanbanColumn {{
    background: {s.bg_tertiary};
    border-radius: {px(rad.radius_lg)};
    border: {px(1)} solid {s.border_default};
}}

.KanbanColumn__header {{
    background: {s.accent_subtle};
    border-radius: {px(rad.radius_lg)} {px(rad.radius_lg)} 0 0;
    padding: {px(sp.space_2)} {px(sp.space_3)};
    color: {s.accent_primary};
    font-weight: {typo.weight_semibold};
    font-size: {px(typo.text_sm)};
}}

.KanbanColumn__count {{
    background: {s.accent_primary};
    color: {s.text_on_accent};
    border-radius: {px(rad.radius_full)};
    padding: {px(2)} {px(sp.space_2)};
    font-size: {px(typo.text_xs)};
    font-weight: {typo.weight_bold};
}}

.KanbanCard {{
    background: {s.bg_primary};
    border: {px(1)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    padding: {px(sp.space_3)};
    margin: {px(sp.space_2)} {px(sp.space_2)} {px(sp.space_2)} {px(sp.space_2)};
}}

.KanbanCard--a_comprar {{
    border-left: {px(3)} solid {s.error};
}}
.KanbanCard--em_estoque {{
    border-left: {px(3)} solid {s.success};
}}
.KanbanCard--em_uso {{
    border-left: {px(3)} solid {s.info};
}}
.KanbanCard--critico {{
    border-left: {px(3)} solid {s.warning};
}}

.KanbanCard__name {{
    font-weight: {typo.weight_semibold};
    font-size: {px(typo.text_base)};
    color: {s.text_primary};
}}
.KanbanCard__category {{
    font-size: {px(typo.text_xs)};
    color: {s.text_muted};
    text-transform: uppercase;
}}
.KanbanCard__quantity {{
    font-size: {px(typo.text_2xl)};
    font-weight: {typo.weight_bold};
    color: {s.text_primary};
}}
.KanbanCard__range {{
    font-size: {px(typo.text_xs)};
    color: {s.text_muted};
}}
"""


def generate_input_stylesheet(scheme: ColorScheme) -> str:
    """Estilos específicos para área de input/composer."""
    s = scheme
    sp = scheme.spacing
    rad = scheme.radius
    typo = scheme.typography

    return f"""
/* ============================================================
   INPUT / COMPOSER COMPONENTS
   ============================================================ */

.InputComposer {{
    background: {s.bg_secondary};
    border: {px(1)} solid {s.border_default};
    border-radius: {px(rad.radius_xl)};
    padding: {px(sp.space_2)} {px(sp.space_3)};
}}

.InputComposer:focus-within {{
    border-color: {s.border_focus};
    background: {s.bg_secondary};
}}

.InputComposer__textarea {{
    background: transparent;
    border: none;
    color: {s.text_primary};
    font-size: {px(typo.text_base)};
    font-family: '{typo.font_sans}', {typo.font_fallback_sans};
    line-height: {typo.leading_relaxed};
    min-height: {px(24)};
    max-height: {px(200)};
}}
.InputComposer__textarea:focus {{
    outline: none;
}}

.InputComposer__attachments {{
    background: {s.bg_tertiary};
    border-radius: {px(rad.radius_md)};
    padding: {px(sp.space_1)} {px(sp.space_2)};
    margin-top: {px(sp.space_2)};
}}

.InputComposer__attachment {{
    background: {s.bg_primary};
    border: {px(1)} solid {s.border_default};
    border-radius: {px(rad.radius_md)};
    padding: {px(sp.space_1)} {px(sp.space_2)};
    margin-right: {px(sp.space_1)};
}}

.InputComposer__actions {{
    padding-left: {px(sp.space_2)};
}}

.InputComposer__modelSelector {{
    min-width: {px(160)};
    max-width: {px(240)};
}}

.InputComposer__sendBtn {{
    background: {s.accent_primary};
    color: {s.text_on_accent};
    border-radius: {px(rad.radius_full)};
    padding: {px(sp.space_2)} {px(sp.space_4)};
    font-weight: {typo.weight_semibold};
}}
.InputComposer__sendBtn:hover {{
    background: {s.accent_hover};
}}
.InputComposer__sendBtn:disabled {{
    background: {s.text_muted};
    color: {s.text_inverse};
}}

.InputComposer__micBtn {{
    border-radius: {px(rad.radius_full)};
    padding: {px(sp.space_2)};
}}
.InputComposer__micBtn[recording="true"] {{
    background: {s.error};
    color: {s.error_text};
}}
"""


def generate_all_stylesheets(scheme: ColorScheme) -> str:
    """Gera o stylesheet completo combinando todos os módulos."""
    return "\n".join([
        generate_base_stylesheet(scheme),
        generate_chat_stylesheet(scheme),
        generate_sidebar_stylesheet(scheme),
        generate_inventory_stylesheet(scheme),
        generate_input_stylesheet(scheme),
    ])


def get_stylesheet(scheme: ColorScheme) -> str:
    """Função principal para obter o stylesheet completo."""
    return generate_all_stylesheets(scheme)