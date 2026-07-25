"""Modulo de icones SVG para o Celsius."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

_S = {
    "copy": (
        '<rect x="9" y="9" width="11" height="11" rx="1.5" fill="none" stroke="{c}" stroke-width="1.8"/>'
        '<path d="M5 15H3.5A1.5 1.5 0 0 1 2 13.5v-10A1.5 1.5 0 0 1 3.5 2h10A1.5 1.5 0 0 1 15 3.5V5" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "paperclip": (
        '<path d="M21.44 11.05l-9.19 9.19a5.64 5.64 0 0 1-7.98-7.98l9.19-9.19a3.76 3.76 0 0 1 5.32 5.32L9.64 17.6'
        'a1.88 1.88 0 0 1-2.66-2.66l8.38-8.38" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "microphone": (
        '<rect x="9" y="2" width="6" height="12" rx="3" fill="none" stroke="{c}" stroke-width="1.8"/>'
        '<path d="M5 10a7 7 0 0 0 14 0" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="12" y1="17" x2="12" y2="21" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="8" y1="21" x2="16" y2="21" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "microphone-off": (
        '<line x1="1" y1="1" x2="23" y2="23" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<path d="M9 9v3a3 3 0 0 0 5.12 2.88M15 9.34V4a3 3 0 0 0-5.94-.6" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M17 16.95A7 7 0 0 1 5 12a7 7 0 0 1 11.84-6" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="12" y1="19" x2="12" y2="23" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "volume-up": (
        '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<path d="M15.54 8.46a5 5 0 0 1 0 7.07" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<path d="M19.07 4.93a10 10 0 0 1 0 14.14" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "paper-plane": (
        '<path d="M22 2L11 13" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M22 2L15 22l-4-9-9-4 20-7z" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "bars": (
        '<line x1="3" y1="6" x2="21" y2="6" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="3" y1="12" x2="21" y2="12" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="3" y1="18" x2="21" y2="18" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "save": (
        '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<polyline points="17 21 17 13 7 13 7 21" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<polyline points="7 3 7 8 15 8" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
    ),
    "trash": (
        '<polyline points="3 6 5 6 21 6" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<path d="M10 11v6" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<path d="M14 11v6" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
    ),
    "plus": (
        '<line x1="12" y1="5" x2="12" y2="19" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="5" y1="12" x2="19" y2="12" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "plus-circle": (
        '<circle cx="12" cy="12" r="9" fill="none" stroke="{c}" stroke-width="1.8"/>'
        '<line x1="12" y1="8" x2="12" y2="16" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="8" y1="12" x2="16" y2="12" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "search": (
        '<circle cx="11" cy="11" r="7" fill="none" stroke="{c}" stroke-width="1.8"/>'
        '<line x1="16.5" y1="16.5" x2="21" y2="21" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "brain": (
        '<path d="M12 2a5 5 0 0 0-4.78 3.5A4.5 4.5 0 0 0 4 9.5a4.5 4.5 0 0 0 2 3.74V18a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-4.76A4.5 4.5 0 0 0 20 9.5a4.5 4.5 0 0 0-3.22-4A5 5 0 0 0 12 2z" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<path d="M12 2v4M8 7l-2-1M16 7l2-1M9 22v-4M15 22v-4" fill="none" stroke="{c}" stroke-width="1.4" stroke-linecap="round"/>'
    ),
    "cog": (
        '<circle cx="12" cy="12" r="3" fill="none" stroke="{c}" stroke-width="1.8"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
    ),
    "edit": (
        '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
    ),
    "sidebar": (
        '<rect x="3" y="3" width="18" height="18" rx="2" fill="none" stroke="{c}" stroke-width="1.8"/>'
        '<line x1="9" y1="3" x2="9" y2="21" stroke="{c}" stroke-width="1.8"/>'
    ),
    "moon": (
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
    ),
    "sun": (
        '<circle cx="12" cy="12" r="4" fill="none" stroke="{c}" stroke-width="1.8"/>'
        '<line x1="12" y1="2" x2="12" y2="5" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="12" y1="19" x2="12" y2="22" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="4.93" y1="4.93" x2="7.05" y2="7.05" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="16.95" y1="16.95" x2="19.07" y2="19.07" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="2" y1="12" x2="5" y2="12" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="19" y1="12" x2="22" y2="12" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="4.93" y1="19.07" x2="7.05" y2="16.95" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="16.95" y1="7.05" x2="19.07" y2="4.93" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "file-export": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<polyline points="14 2 14 8 20 8" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<line x1="8" y1="13" x2="16" y2="13" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="8" y1="17" x2="12" y2="17" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "file-import": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<polyline points="14 2 14 8 20 8" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<line x1="12" y1="12" x2="12" y2="18" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<polyline points="9 15 12 18 15 15" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "cube": (
        '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<polyline points="3.27 6.96 12 12.01 20.73 6.96" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<line x1="12" y1="22.08" x2="12" y2="12" stroke="{c}" stroke-width="1.8"/>'
    ),
    "file-alt": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<polyline points="14 2 14 8 20 8" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
        '<line x1="8" y1="13" x2="16" y2="13" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="8" y1="17" x2="16" y2="17" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "code": (
        '<polyline points="16 18 22 12 16 6" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<polyline points="8 6 2 12 8 18" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "database": (
        '<ellipse cx="12" cy="5" rx="9" ry="3" fill="none" stroke="{c}" stroke-width="1.8"/>'
        '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" fill="none" stroke="{c}" stroke-width="1.8"/>'
        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" fill="none" stroke="{c}" stroke-width="1.8"/>'
    ),
    "list": (
        '<line x1="8" y1="6" x2="21" y2="6" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="8" y1="12" x2="21" y2="12" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="8" y1="18" x2="21" y2="18" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<line x1="3" y1="6" x2="3.01" y2="6" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/>'
        '<line x1="3" y1="12" x2="3.01" y2="12" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/>'
        '<line x1="3" y1="18" x2="3.01" y2="18" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/>'
    ),
    "print": (
        '<polyline points="6 9 6 2 18 2 18 9" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<rect x="6" y="14" width="12" height="8" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
    ),
    "refresh": (
        '<polyline points="23 4 23 10 17 10" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<polyline points="1 20 1 14 7 14" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" '
        'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
}


def icon(name: str, color: str = "#FFFFFF") -> QIcon:
    """Retorna um QIcon renderizado a partir de SVG com a cor especificada."""
    key = name.removeprefix("fa5s.")
    svg_template = _S.get(key)
    if svg_template is None:
        raise ValueError(f"Icone desconhecido: {name}")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'{svg_template.format(c=color)}</svg>'
    )
    pixmap = QPixmap(QSize(24, 24))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    from PySide6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(bytearray(svg.encode()))
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
