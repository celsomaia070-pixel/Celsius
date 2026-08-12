"""
Kanban Board - Controle de Estoque
Design moderno inspirado em WMS profissionais (Sortly, Katana, ERPNext).
"""

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag, QDragEnterEvent, QDragLeaveEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.inventory import ColunaKanban, ItemEstoque
from ui.theme.schemes import ColorScheme, get_scheme

CARD_WIDTH = 220
CARD_HEIGHT = 180
CARD_MARGIN = 10
COLUMN_WIDTH = 250
COLUMN_HEADER_HEIGHT = 48
COLUMN_SPACING = 14
BOARD_PADDING = 16


def _is_dark_color(color: str) -> bool:
    """Detect dark backgrounds without depending on a specific palette value."""
    value = color.lstrip("#")
    if len(value) != 6:
        return False
    try:
        red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return False
    luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
    return luminance < 128


def _column_config(scheme: ColorScheme | None = None) -> dict:
    """Configuracao visual das colunas usando a identidade Celsius."""
    is_dark = bool(scheme and _is_dark_color(scheme.bg_primary))
    if is_dark:
        return {
            ColunaKanban.A_COMPRAR: {
                "header": "#E8B759",
                "header_text": "#101715",
                "bg": "#2C271A",
                "card_bg": "#18211F",
                "border": "#594A28",
                "accent": "#E8B759",
                "badge_bg": "#453819",
                "badge_text": "#F2CC80",
                "empty": "#8E7748",
                "icon": "!",
            },
            ColunaKanban.EM_ESTOQUE: {
                "header": "#69C58D",
                "header_text": "#101715",
                "bg": "#17281E",
                "card_bg": "#18211F",
                "border": "#315942",
                "accent": "#69C58D",
                "badge_bg": "#1D3D2A",
                "badge_text": "#8DDBAA",
                "empty": "#4E8061",
                "icon": "v",
            },
            ColunaKanban.EM_USO: {
                "header": "#73B8E3",
                "header_text": "#101715",
                "bg": "#17252D",
                "card_bg": "#18211F",
                "border": "#315468",
                "accent": "#73B8E3",
                "badge_bg": "#1D3545",
                "badge_text": "#9BCFEE",
                "empty": "#52798F",
                "icon": "~",
            },
            ColunaKanban.CRITICO: {
                "header": "#FF8178",
                "header_text": "#101715",
                "bg": "#2D1D1B",
                "card_bg": "#18211F",
                "border": "#653834",
                "accent": "#FF8178",
                "badge_bg": "#4A2623",
                "badge_text": "#FFAAA4",
                "empty": "#9B5A54",
                "icon": "!",
            },
        }
    return {
        ColunaKanban.A_COMPRAR: {
            "header": "#9A6B13",
            "header_text": "#FFFFFF",
            "bg": "#F7EDD7",
            "card_bg": "#FFFFFF",
            "border": "#E1C993",
            "accent": "#9A6B13",
            "badge_bg": "#F4E6C7",
            "badge_text": "#76500D",
            "empty": "#B59B6A",
            "icon": "!",
        },
        ColunaKanban.EM_ESTOQUE: {
            "header": "#237B4B",
            "header_text": "#FFFFFF",
            "bg": "#E2F1E8",
            "card_bg": "#FFFFFF",
            "border": "#B8D9C5",
            "accent": "#237B4B",
            "badge_bg": "#D5EADB",
            "badge_text": "#185E39",
            "empty": "#82AE92",
            "icon": "v",
        },
        ColunaKanban.EM_USO: {
            "header": "#286FA1",
            "header_text": "#FFFFFF",
            "bg": "#E0ECF4",
            "card_bg": "#FFFFFF",
            "border": "#B5D0E1",
            "accent": "#286FA1",
            "badge_bg": "#D5E5EF",
            "badge_text": "#1F587F",
            "empty": "#83A9C1",
            "icon": "~",
        },
        ColunaKanban.CRITICO: {
            "header": "#C9463C",
            "header_text": "#FFFFFF",
            "bg": "#F8E3E1",
            "card_bg": "#FFFFFF",
            "border": "#E8B6B2",
            "accent": "#C9463C",
            "badge_bg": "#F2D3D0",
            "badge_text": "#94332C",
            "empty": "#C58A85",
            "icon": "!",
        },
    }


def _stock_color(item: ItemEstoque, scheme: ColorScheme | None = None) -> str:
    s = scheme or get_scheme()
    if item.quantidade <= 0:
        return s.error
    if item.quantidade <= item.estoque_min:
        return s.error
    pct = item.quantidade / max(item.estoque_max, 1)
    if pct < 0.3:
        return s.warning
    if pct < 0.7:
        return s.info
    return s.success


class KanbanCard(QWidget):
    """Card moderno estilo Sortly/Katana com acoes rapidas."""

    card_clicked = Signal(str)
    entrada_clicked = Signal(str)
    saida_clicked = Signal(str)

    def __init__(self, item: ItemEstoque, scheme=None, parent=None):
        super().__init__(parent)
        self.item = item
        self._scheme = scheme
        self._drag_start_pos = None
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self):
        s = self._scheme or get_scheme()
        cores = _column_config(s).get(self.item.coluna, _column_config(s)[ColunaKanban.EM_ESTOQUE])

        self.setStyleSheet(f"""
            KanbanCard {{
                background: {cores["card_bg"]};
                border: 1px solid {cores["border"]};
                border-radius: 7px;
            }}
            KanbanCard:hover {{
                border: 2px solid {cores["accent"]};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        status = self._get_status()
        badge_bg = cores["badge_bg"]
        badge_fg = cores["badge_text"]
        badge = QLabel(status)
        badge.setFixedHeight(20)
        badge.setStyleSheet(
            f"background: {badge_bg}; color: {badge_fg}; border-radius: 10px; "
            f"padding: 2px 10px; font-size: 10px; font-weight: 700; border: none;"
        )
        top_row.addWidget(badge)
        top_row.addStretch()

        cat_label = QLabel(self.item.categoria)
        cat_label.setStyleSheet(
            f"color: {s.text_muted}; font-size: 10px; background: transparent; border: none;"
        )
        top_row.addWidget(cat_label)
        layout.addLayout(top_row)

        name = QLabel(self.item.nome)
        name.setWordWrap(True)
        name.setStyleSheet(
            f"color: {s.text_primary}; font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none; line-height: 1.2;"
        )
        layout.addWidget(name)

        layout.addSpacing(2)

        qty_row = QHBoxLayout()
        qty_row.setSpacing(4)
        health = _stock_color(self.item, s)
        qty = QLabel(str(self.item.quantidade))
        qty.setStyleSheet(
            f"color: {health}; font-size: 28px; font-weight: 800; "
            f"background: transparent; border: none;"
        )
        qty_row.addWidget(qty)

        unit = QLabel("un")
        unit.setStyleSheet(
            f"color: {s.text_muted}; font-size: 11px; font-weight: 500; "
            f"background: transparent; border: none; margin-top: 10px;"
        )
        qty_row.addWidget(unit, 0, Qt.AlignBottom)
        qty_row.addStretch()
        layout.addLayout(qty_row)

        range_label = QLabel(f"min {self.item.estoque_min}  /  max {self.item.estoque_max}")
        range_label.setStyleSheet(
            f"color: {s.text_muted}; font-size: 10px; background: transparent; border: none;"
        )
        layout.addWidget(range_label)

        bar_container = QWidget()
        bar_container.setFixedHeight(6)
        bar_container.setStyleSheet("background: transparent; border: none;")
        bar_layout = QHBoxLayout(bar_container)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(0)

        pct = min(self.item.quantidade / max(self.item.estoque_max, 1), 1.0)
        bar_bg = QLabel()
        bar_bg.setStyleSheet(f"background: {s.border_default}; border-radius: 3px; border: none;")
        bar_layout.addWidget(bar_bg, 1)

        bar_fill = QLabel()
        bar_fill.setStyleSheet(f"background: {health}; border-radius: 3px; border: none;")
        bar_layout.addWidget(bar_fill, max(int(pct * 100), 1))

        layout.addWidget(bar_container)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        btn_in = QPushButton("+ Entrada")
        btn_in.setFixedHeight(26)
        btn_in.setCursor(Qt.PointingHandCursor)
        btn_in.setStyleSheet(f"""
            QPushButton {{
                background: {s.success_bg}; color: {s.success_text}; border: 1px solid {s.success};
                border-radius: 6px; font-size: 10px; font-weight: 600; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {s.bg_hover}; }}
        """)
        btn_in.clicked.connect(lambda: self.entrada_clicked.emit(self.item.id))
        actions_row.addWidget(btn_in)

        btn_out = QPushButton("- Saida")
        btn_out.setFixedHeight(26)
        btn_out.setCursor(Qt.PointingHandCursor)
        btn_out.setStyleSheet(f"""
            QPushButton {{
                background: {s.error_bg}; color: {s.error_text}; border: 1px solid {s.border_error};
                border-radius: 6px; font-size: 10px; font-weight: 600; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {s.bg_hover}; }}
        """)
        btn_out.clicked.connect(lambda: self.saida_clicked.emit(self.item.id))
        actions_row.addWidget(btn_out)

        layout.addLayout(actions_row)

    def _get_status(self) -> str:
        if self.item.quantidade <= 0:
            return "SEM ESTOQUE"
        if self.item.precisa_repor:
            return "CRITICO"
        if self.item.excedeu_max:
            return "EXCEDIDO"
        return "OK"

    def atualizar(self, item: ItemEstoque):
        self.item = item
        self._rebuild()

    def _rebuild(self):
        layout = self.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    self._clear_layout(child.layout())
        self._build_ui()

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is None:
            return
        if (
            event.pos() - self._drag_start_pos
        ).manhattanLength() > QApplication.startDragDistance():
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData("application/x-kanban-item", self.item.id.encode())

            pixmap = QPixmap(self.size())
            self.render(pixmap)

            drag.setMimeData(mime)
            drag.setPixmap(pixmap)
            drag.setHotSpot(self._drag_start_pos)
            drag.exec(Qt.MoveAction)
            self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        if event.button() == Qt.LeftButton:
            self.card_clicked.emit(self.item.id)
        super().mouseReleaseEvent(event)


class KanbanColumnWidget(QWidget):
    """Coluna moderna com header, contador e cards."""

    def __init__(self, coluna: ColunaKanban, scheme=None, parent=None):
        super().__init__(parent)
        self.coluna = coluna
        self._scheme = scheme
        self._cards: list[KanbanCard] = []
        self._drag_active = False
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self):
        s = self._scheme or get_scheme()
        cores = _column_config(s).get(self.coluna, _column_config(s)[ColunaKanban.EM_ESTOQUE])

        self.setStyleSheet(f"""
            KanbanColumnWidget {{
                background: {cores["bg"]};
                border: 1px solid {cores["border"]};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QWidget()
        self._header.setFixedHeight(COLUMN_HEADER_HEIGHT)
        self._header.setStyleSheet(f"""
            background: {cores["header"]};
            border-top-left-radius: 7px; border-top-right-radius: 7px;
            border: none;
        """)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(14, 0, 14, 0)

        self._icon_label = QLabel(cores["icon"])
        self._icon_label.setStyleSheet(
            f"color: {cores['header_text']}; font-size: 16px; font-weight: 900; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(self._icon_label)

        self._column_title = QLabel(self.coluna.label)
        self._column_title.setStyleSheet(
            f"color: {cores['header_text']}; font-size: 13px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(self._column_title)

        header_layout.addStretch()

        self._count_badge = QLabel("0")
        self._count_badge.setFixedSize(24, 24)
        self._count_badge.setAlignment(Qt.AlignCenter)
        self._count_badge.setStyleSheet(
            "background: rgba(255,255,255,0.25); color: #FFFFFF; border-radius: 12px; "
            "font-size: 11px; font-weight: 700; border: none;"
        )
        header_layout.addWidget(self._count_badge)

        layout.addWidget(self._header)

        self._cards_area = QWidget()
        self._cards_area.setStyleSheet("background: transparent; border: none;")
        self._cards_layout = QVBoxLayout(self._cards_area)
        self._cards_layout.setContentsMargins(8, 10, 8, 10)
        self._cards_layout.setSpacing(CARD_MARGIN)
        self._cards_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._cards_area)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(128,128,128,0.3); border-radius: 3px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: rgba(128,128,128,0.5); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        layout.addWidget(scroll, 1)

        self._empty_label = QLabel(f"Nenhum item\nna coluna {self.coluna.label.lower()}")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {cores['empty']}; font-size: 12px; padding: 40px 20px; "
            f"background: transparent; border: none;"
        )
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, self._empty_label)

    def add_card(self, card: KanbanCard, animate=True):
        self._cards.append(card)
        card.entrada_clicked.connect(self._on_card_entrada)
        card.saida_clicked.connect(self._on_card_saida)
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
        self._update_count()

    def remove_card(self, card: KanbanCard):
        if card in self._cards:
            self._cards.remove(card)
            self._cards_layout.removeWidget(card)
            card.deleteLater()
            self._update_count()

    def _update_count(self):
        n = len(self._cards)
        self._count_badge.setText(str(n))
        self._empty_label.setVisible(n == 0)

    def cards(self) -> list[KanbanCard]:
        return self._cards

    def set_drag_highlight(self, active: bool):
        self._drag_active = active
        s = self._scheme or get_scheme()
        cores = _column_config(s).get(self.coluna, _column_config(s)[ColunaKanban.EM_ESTOQUE])
        if active:
            self.setStyleSheet(f"""
                KanbanColumnWidget {{
                    background: {cores["bg"]};
                    border: 2px dashed {cores["accent"]};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                KanbanColumnWidget {{
                    background: {cores["bg"]};
                    border: 1px solid {cores["border"]};
                    border-radius: 8px;
                }}
            """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-kanban-item"):
            event.acceptProposedAction()
            self.set_drag_highlight(True)

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self.set_drag_highlight(False)

    def dropEvent(self, event):
        self.set_drag_highlight(False)
        if event.mimeData().hasFormat("application/x-kanban-item"):
            item_id = event.mimeData().data("application/x-kanban-item").data().decode()
            parent_view = self.parent()
            while parent_view and not isinstance(parent_view, KanbanView):
                parent_view = parent_view.parent()
            if parent_view:
                parent_view.item_movido.emit(item_id, self.coluna.value)
            event.acceptProposedAction()

    def _on_card_entrada(self, item_id: str):
        parent_view = self.parent()
        while parent_view and not isinstance(parent_view, KanbanView):
            parent_view = parent_view.parent()
        if parent_view and hasattr(parent_view, "entrada_solicitada"):
            parent_view.entrada_solicitada.emit(item_id)

    def _on_card_saida(self, item_id: str):
        parent_view = self.parent()
        while parent_view and not isinstance(parent_view, KanbanView):
            parent_view = parent_view.parent()
        if parent_view and hasattr(parent_view, "saida_solicitada"):
            parent_view.saida_solicitada.emit(item_id)

    def set_scheme(self, scheme):
        self._scheme = scheme
        s = scheme or get_scheme()
        cores = _column_config(s).get(self.coluna, _column_config(s)[ColunaKanban.EM_ESTOQUE])
        self.setStyleSheet(f"""
            KanbanColumnWidget {{
                background: {cores["bg"]};
                border: 1px solid {cores["border"]};
                border-radius: 8px;
            }}
        """)
        self._header.setStyleSheet(f"""
            background: {cores["header"]};
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
            border: none;
        """)
        self._icon_label.setText(cores["icon"])
        self._icon_label.setStyleSheet(
            f"color: {cores['header_text']}; font-size: 16px; font-weight: 900; "
            "background: transparent; border: none;"
        )
        self._column_title.setStyleSheet(
            f"color: {cores['header_text']}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        self._empty_label.setStyleSheet(
            f"color: {cores['empty']}; font-size: 12px; padding: 40px 20px; "
            "background: transparent; border: none;"
        )
        for card in self._cards:
            card._scheme = scheme
            card._rebuild()


class KanbanView(QWidget):
    """View principal do Kanban com drag-and-drop."""

    item_movido = Signal(str, str)
    entrada_solicitada = Signal(str)
    saida_solicitada = Signal(str)
    card_clicado = Signal(str)

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        self._columns: dict[ColunaKanban, KanbanColumnWidget] = {}
        self._setup_ui()

    def _setup_ui(self):
        s = self._scheme or get_scheme()
        self.setStyleSheet(f"background: {s.bg_primary}; border: none;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(BOARD_PADDING, BOARD_PADDING, BOARD_PADDING, BOARD_PADDING)
        layout.setSpacing(COLUMN_SPACING)

        for coluna in [
            ColunaKanban.CRITICO,
            ColunaKanban.A_COMPRAR,
            ColunaKanban.EM_ESTOQUE,
            ColunaKanban.EM_USO,
        ]:
            col = KanbanColumnWidget(coluna, scheme=self._scheme)
            col.setMinimumWidth(COLUMN_WIDTH)
            col.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._columns[coluna] = col
            layout.addWidget(col)

    def update_board(self, items: list[ItemEstoque]):
        by_coluna: dict[ColunaKanban, list[ItemEstoque]] = {
            ColunaKanban.CRITICO: [],
            ColunaKanban.A_COMPRAR: [],
            ColunaKanban.EM_ESTOQUE: [],
            ColunaKanban.EM_USO: [],
        }
        for item in items:
            coluna = item.coluna
            if coluna in by_coluna:
                by_coluna[coluna].append(item)
            else:
                by_coluna[ColunaKanban.EM_ESTOQUE].append(item)

        for coluna, column in self._columns.items():
            for card in column.cards():
                column.remove_card(card)
            for item in by_coluna[coluna]:
                card = KanbanCard(item, scheme=self._scheme)
                card.card_clicked.connect(self.card_clicado.emit)
                card.entrada_clicked.connect(self.entrada_solicitada.emit)
                card.saida_clicked.connect(self.saida_solicitada.emit)
                column.add_card(card, animate=False)

    def set_scheme(self, scheme):
        self._scheme = scheme
        s = scheme or get_scheme()
        self.setStyleSheet(f"background: {s.bg_primary}; border: none;")
        for col in self._columns.values():
            col.set_scheme(scheme)


class KPIBar(QWidget):
    """Barra de KPIs moderna com cards."""

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        self.setFixedHeight(80)
        self._setup_ui()

    def _setup_ui(self):
        s = self._scheme or get_scheme()
        self.setStyleSheet(
            f"background: {s.bg_secondary}; border-bottom: 1px solid {s.border_default};"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)

        self._kpis: list[dict] = []

        kpi_defs = [
            ("total", "Total de itens", "info"),
            ("em_estoque", "Em estoque", "success"),
            ("criticos", "Criticos", "error"),
            ("a_comprar", "A comprar", "warning"),
            ("total_un", "Total de unidades", "accent_primary"),
        ]

        for key, label, color_role in kpi_defs:
            color = getattr(s, color_role)
            card = QWidget()
            card.setStyleSheet(f"""
                background: {s.bg_secondary}; border: 1px solid {s.border_default};
                border-radius: 8px; padding: 8px 16px;
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(2)

            val = QLabel("0")
            val.setStyleSheet(
                f"color: {color}; font-size: 22px; font-weight: 800; "
                f"background: transparent; border: none;"
            )
            card_layout.addWidget(val)

            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color: {s.text_muted}; font-size: 11px; font-weight: 500; "
                f"background: transparent; border: none;"
            )
            card_layout.addWidget(lbl)

            self._kpis.append(
                {
                    "key": key,
                    "value": val,
                    "label": lbl,
                    "card": card,
                    "color_role": color_role,
                }
            )
            layout.addWidget(card)

        layout.addStretch()

    def update_kpis(self, items: list[ItemEstoque]):
        total = len(items)
        em_estoque = sum(1 for i in items if i.coluna == ColunaKanban.EM_ESTOQUE)
        criticos = sum(
            1 for i in items if i.coluna in (ColunaKanban.CRITICO, ColunaKanban.A_COMPRAR)
        )
        a_comprar = sum(1 for i in items if i.coluna == ColunaKanban.A_COMPRAR)
        total_un = sum(i.quantidade for i in items)

        values = {
            "total": total,
            "em_estoque": em_estoque,
            "criticos": criticos,
            "a_comprar": a_comprar,
            "total_un": total_un,
        }
        for kpi in self._kpis:
            kpi["value"].setText(str(values.get(kpi["key"], 0)))

    def set_scheme(self, scheme):
        self._scheme = scheme
        s = scheme or get_scheme()
        self.setStyleSheet(
            f"background: {s.bg_secondary}; border-bottom: 1px solid {s.border_default};"
        )
        for kpi in self._kpis:
            color = getattr(s, kpi["color_role"])
            kpi["card"].setStyleSheet(f"""
                background: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: 8px;
                padding: 8px 16px;
            """)
            kpi["value"].setStyleSheet(
                f"color: {color}; font-size: 22px; font-weight: 800; "
                "background: transparent; border: none;"
            )
            kpi["label"].setStyleSheet(
                f"color: {s.text_muted}; font-size: 11px; font-weight: 500; "
                "background: transparent; border: none;"
            )


class KanbanContainer(QWidget):
    """Wrapper com KPI bar + kanban view."""

    item_movido = Signal(str, str)
    entrada_solicitada = Signal(str)
    saida_solicitada = Signal(str)
    card_clicado = Signal(str)

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.kpi_bar = KPIBar(scheme=scheme)
        layout.addWidget(self.kpi_bar)

        self.kanban_view = KanbanView(scheme=scheme)
        self.kanban_view.item_movido.connect(self.item_movido.emit)
        self.kanban_view.entrada_solicitada.connect(self.entrada_solicitada.emit)
        self.kanban_view.saida_solicitada.connect(self.saida_solicitada.emit)
        self.kanban_view.card_clicado.connect(self.card_clicado.emit)
        layout.addWidget(self.kanban_view, 1)

    def set_scheme(self, scheme):
        self._scheme = scheme
        self.kpi_bar.set_scheme(scheme)
        self.kanban_view.set_scheme(scheme)

    def update_board(self, items: list[ItemEstoque]):
        self.kpi_bar.update_kpis(items)
        self.kanban_view.update_board(items)

    def refresh(self):
        from core.inventory import get_inventory_service

        items = get_inventory_service().get_all_items()
        self.update_board(items)
