"""
Kanban Board - Controle de Estoque
Design inspirado em WMS profissionais (Stackwise, FlowDesk, Stockpile).
"""
from PySide6.QtCore import QEasingCurve, QMimeData, QPropertyAnimation, QTimer, QTimeLine, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsEllipseItem,
    QGraphicsOpacityEffect,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.inventory import ColunaKanban, ItemEstoque, Movimentacao
from ui.theme.schemes import ColorScheme, get_scheme
from ui.theme.tokens import SPACING, RADIUS, TYPOGRAPHY


CARD_WIDTH = 230
CARD_HEIGHT = 160
CARD_MARGIN = 8
COLUMN_WIDTH = 268
COLUMN_HEADER_HEIGHT = 52
COLUMN_SPACING = 12
BOARD_PADDING = 16


def _column_colors(scheme: ColorScheme | None = None) -> dict:
    """Cores das colunas adaptadas ao tema (inspirado WMS profissional)."""
    is_dark = scheme and scheme.bg_primary.startswith("#0")
    if is_dark:
        return {
            ColunaKanban.A_COMPRAR: {
                "header": "#DA3633", "header_text": "#FFFFFF",
                "bg": "#2D1215", "card_bg": "#3D1A1E", "border": "#5C2A2A",
                "dot": "#FF6B6B", "accent": "#FF6B6B", "badge_bg": "#4D1A1A",
                "badge_text": "#FF8A8A", "progress_track": "#4D2020",
                "empty_text": "#FF6B6B",
            },
            ColunaKanban.EM_ESTOQUE: {
                "header": "#1A7F4B", "header_text": "#FFFFFF",
                "bg": "#0D2818", "card_bg": "#163D2A", "border": "#2A5E3F",
                "dot": "#3FB68B", "accent": "#3FB68B", "badge_bg": "#1A3D2A",
                "badge_text": "#5CDB95", "progress_track": "#1A3D2A",
                "empty_text": "#3FB68B",
            },
            ColunaKanban.EM_USO: {
                "header": "#1F6FEB", "header_text": "#FFFFFF",
                "bg": "#0D1F3D", "card_bg": "#1A3A5C", "border": "#2A5A8C",
                "dot": "#58A6FF", "accent": "#58A6FF", "badge_bg": "#1A3050",
                "badge_text": "#79C0FF", "progress_track": "#1A3050",
                "empty_text": "#58A6FF",
            },
            ColunaKanban.CRITICO: {
                "header": "#CF222E", "header_text": "#FFFFFF",
                "bg": "#3D1215", "card_bg": "#4D1A1E", "border": "#6E2A2A",
                "dot": "#FF7B7B", "accent": "#FF7B7B", "badge_bg": "#4D1A1A",
                "badge_text": "#FFA0A0", "progress_track": "#4D2020",
                "empty_text": "#FF7B7B",
            },
        }
    return {
        ColunaKanban.A_COMPRAR: {
            "header": "#E85D5D", "header_text": "#FFFFFF",
            "bg": "#FFF5F5", "card_bg": "#FFFFFF", "border": "#F5C6C6",
            "dot": "#E85D5D", "accent": "#E85D5D", "badge_bg": "#FFF0F0",
            "badge_text": "#C62828", "progress_track": "#F0E0E0",
            "empty_text": "#E85D5D",
        },
        ColunaKanban.EM_ESTOQUE: {
            "header": "#2E9E5E", "header_text": "#FFFFFF",
            "bg": "#F0FBF5", "card_bg": "#FFFFFF", "border": "#C3E6CB",
            "dot": "#2E9E5E", "accent": "#2E9E5E", "badge_bg": "#EDF7ED",
            "badge_text": "#1B5E20", "progress_track": "#D4EDDA",
            "empty_text": "#2E9E5E",
        },
        ColunaKanban.EM_USO: {
            "header": "#3578D8", "header_text": "#FFFFFF",
            "bg": "#F0F7FF", "card_bg": "#FFFFFF", "border": "#B8D4F0",
            "dot": "#3578D8", "accent": "#3578D8", "badge_bg": "#EBF3FE",
            "badge_text": "#1565C0", "progress_track": "#D6EAF8",
            "empty_text": "#3578D8",
        },
        ColunaKanban.CRITICO: {
            "header": "#D32F2F", "header_text": "#FFFFFF",
            "bg": "#FFF5F5", "card_bg": "#FFFFFF", "border": "#F5C6C6",
            "dot": "#D32F2F", "accent": "#D32F2F", "badge_bg": "#FFF0F0",
            "badge_text": "#B71C1C", "progress_track": "#F5C6C6",
            "empty_text": "#D32F2F",
        },
    }


def _stock_health_color(item: ItemEstoque, scheme=None) -> str:
    """Retorna cor da barra de saude do estoque."""
    if item.quantidade <= 0:
        return "#D32F2F"
    if item.quantidade <= item.estoque_min:
        return "#E85D5D"
    pct = item.quantidade / max(item.estoque_max, 1)
    if pct < 0.3:
        return "#F57C00"
    if pct < 0.7:
        return "#FBC02D"
    return "#2E9E5E"


class KanbanCard(QGraphicsRectItem):
    """Card profissional estilo WMS com badge de prioridade e indicador de saude."""

    card_clicked = Signal(object)

    def __init__(self, item: ItemEstoque, scheme=None, parent=None):
        super().__init__(0, 0, CARD_WIDTH, CARD_HEIGHT, parent)
        self.item = item
        self._scheme = scheme
        self._hovered = False
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptDrops(False)
        self.setCursor(Qt.PointingHandCursor)

        cores = _column_colors(self._scheme).get(item.coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])

        self.setBrush(QBrush(QColor(cores["card_bg"])))
        self.setPen(QPen(QColor(cores["border"]), 1.0))
        self.setZValue(1)
        self._cores = cores

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)

        self._build_content(item, cores)

    def _build_content(self, item: ItemEstoque, cores: dict):
        pad = 14
        inner_w = CARD_WIDTH - pad * 2

        # === TOP SECTION: Badge + dot ===
        badge_h = 20
        if item.precisa_repor:
            badge_text = "CRITICO"
            badge_bg = cores["badge_bg"]
            badge_fg = cores["badge_text"]
        elif item.quantidade <= 0:
            badge_text = "SEM ESTOQUE"
            badge_bg = cores["badge_bg"]
            badge_fg = cores["badge_text"]
        elif item.excedeu_max:
            badge_text = "EXCEDIDO"
            badge_bg = cores["badge_bg"]
            badge_fg = cores["badge_text"]
        else:
            badge_text = "OK"
            badge_bg = cores["badge_bg"]
            badge_fg = cores["badge_text"]

        # badge background
        badge_w = len(badge_text) * 7 + 16
        self._badge_bg = QGraphicsRectItem(pad, 10, badge_w, badge_h, self)
        self._badge_bg.setBrush(QBrush(QColor(badge_bg)))
        self._badge_bg.setPen(QPen(Qt.NoPen))
        self._badge_bg.setZValue(2)

        # badge text
        self._badge_text = QGraphicsTextItem(badge_text, self)
        self._badge_text.setPos(pad + 8, 11)
        self._badge_text.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._badge_text.setDefaultTextColor(QColor(badge_fg))
        self._badge_text.setZValue(3)

        # === NAME ===
        self._name_text = QGraphicsTextItem(item.nome, self)
        self._name_text.setPos(pad, 36)
        font_name = QFont("Segoe UI", 11, QFont.Weight.DemiBold)
        self._name_text.setFont(font_name)
        self._name_text.setDefaultTextColor(QColor(self._text_primary()))
        self._name_text.setTextWidth(inner_w)

        # === CATEGORY TAG ===
        self._cat_text = QGraphicsTextItem(item.categoria, self)
        self._cat_text.setPos(pad, 58)
        self._cat_text.setFont(QFont("Segoe UI", 8))
        self._cat_text.setDefaultTextColor(QColor(self._text_secondary()))

        # === QUANTITY (big number) ===
        health_color = _stock_health_color(item, self._scheme)
        self._qtd_text = QGraphicsTextItem(str(item.quantidade), self)
        self._qtd_text.setPos(pad, 80)
        self._qtd_text.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self._qtd_text.setDefaultTextColor(QColor(health_color))

        self._qtd_label = QGraphicsTextItem("un.", self)
        self._qtd_label.setPos(pad + self._qtd_text.boundingRect().width() + 4, 90)
        self._qtd_label.setFont(QFont("Segoe UI", 9))
        self._qtd_label.setDefaultTextColor(QColor(self._text_muted()))

        # === MIN / MAX range ===
        self._range_text = QGraphicsTextItem(
            f"min {item.estoque_min}  /  max {item.estoque_max}", self
        )
        self._range_text.setPos(pad, 110)
        self._range_text.setFont(QFont("Segoe UI", 8))
        self._range_text.setDefaultTextColor(QColor(self._text_muted()))

        # === PROGRESS BAR ===
        bar_y = 132
        bar_w = inner_w
        bar_h = 5

        self._bar_bg = QGraphicsRectItem(pad, bar_y, bar_w, bar_h, self)
        self._bar_bg.setBrush(QBrush(QColor(cores["progress_track"])))
        self._bar_bg.setPen(QPen(Qt.NoPen))

        pct = min(item.quantidade / max(item.estoque_max, 1), 1.0)
        fill_w = max(int(bar_w * pct), 3)
        self._bar_fill = QGraphicsRectItem(pad, bar_y, fill_w, bar_h, self)
        self._bar_fill.setBrush(QBrush(QColor(health_color)))
        self._bar_fill.setPen(QPen(Qt.NoPen))
        self._bar_fill.setZValue(1)

        # === THIN TOP ACCENT LINE ===
        self._accent_line = QGraphicsRectItem(0, 0, CARD_WIDTH, 3, self)
        self._accent_line.setBrush(QBrush(QColor(cores["accent"])))
        self._accent_line.setPen(QPen(Qt.NoPen))
        self._accent_line.setZValue(2)

    def _text_primary(self):
        return self._scheme.text_primary if self._scheme else "#1A1A2E"

    def _text_secondary(self):
        return self._scheme.text_secondary if self._scheme else "#8E8E93"

    def _text_muted(self):
        return self._scheme.text_muted if self._scheme else "#AEAEB2"

    def _border_default(self):
        return self._scheme.border_default if self._scheme else "#E5E5EA"

    def set_scheme(self, scheme):
        self._scheme = scheme
        cores = _column_colors(scheme).get(self.item.coluna, _column_colors(scheme)[ColunaKanban.EM_ESTOQUE])
        self._cores = cores
        self._name_text.setDefaultTextColor(QColor(self._text_primary()))
        self._cat_text.setDefaultTextColor(QColor(self._text_secondary()))
        self._range_text.setDefaultTextColor(QColor(self._text_muted()))
        self._qtd_label.setDefaultTextColor(QColor(self._text_muted()))
        self._bar_bg.setBrush(QBrush(QColor(cores["progress_track"])))
        health_color = _stock_health_color(self.item, scheme)
        self._bar_fill.setBrush(QBrush(QColor(health_color)))
        self._qtd_text.setDefaultTextColor(QColor(health_color))
        self.setBrush(QBrush(QColor(cores["card_bg"])))
        self.setPen(QPen(QColor(cores["border"]), 1.0))
        self._accent_line.setBrush(QBrush(QColor(cores["accent"])))

    def atualizar(self, item: ItemEstoque):
        self.item = item
        cores = _column_colors(self._scheme).get(item.coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])
        self._cores = cores
        self.setBrush(QBrush(QColor(cores["card_bg"])))
        self.setPen(QPen(QColor(cores["border"]), 1.0))
        self._name_text.setPlainText(item.nome)
        self._cat_text.setPlainText(item.categoria)
        self._qtd_text.setPlainText(str(item.quantidade))
        health_color = _stock_health_color(item, self._scheme)
        self._qtd_text.setDefaultTextColor(QColor(health_color))
        self._range_text.setPlainText(f"min {item.estoque_min}  /  max {item.estoque_max}")

        pct = min(item.quantidade / max(item.estoque_max, 1), 1.0)
        inner_w = CARD_WIDTH - 28
        fill_w = max(int(inner_w * pct), 3)
        self._bar_fill.setRect(14, 132, fill_w, 5)
        self._bar_fill.setBrush(QBrush(QColor(health_color)))

        # Update badge
        if item.precisa_repor:
            badge_text = "CRITICO"
        elif item.quantidade <= 0:
            badge_text = "SEM ESTOQUE"
        elif item.excedeu_max:
            badge_text = "EXCEDIDO"
        else:
            badge_text = "OK"
        self._badge_text.setPlainText(badge_text)
        badge_w = len(badge_text) * 7 + 16
        self._badge_bg.setRect(14, 10, badge_w, 20)
        self._accent_line.setBrush(QBrush(QColor(cores["accent"])))

    def animate_fade_in(self):
        self._timeline = QTimeLine(250)
        self._timeline.setFrameRange(0, 10)
        self._timeline.frameChanged.connect(self._on_fade_frame)
        self._timeline.start()

    def _on_fade_frame(self, frame):
        self.setOpacity(frame / 10.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.card_clicked.emit(self.item)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            drag = QDrag(event.widget())
            mime = QMimeData()
            mime.setData("application/x-kanban-item", self.item.id.encode())

            pixmap = QPixmap(CARD_WIDTH, CARD_HEIGHT)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            cores = self._cores
            painter.setBrush(QColor(cores["card_bg"]))
            painter.setPen(QPen(QColor(cores["border"]), 1.0))
            painter.drawRoundedRect(0, 0, CARD_WIDTH, CARD_HEIGHT, 10, 10)

            painter.setBrush(QColor(cores["accent"]))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, CARD_WIDTH, 3, 10, 10)

            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
            painter.setPen(QColor(self._text_primary()))
            painter.drawText(14, 56, self.item.nome[:28])

            painter.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
            painter.setPen(QColor(_stock_health_color(self.item, self._scheme)))
            painter.drawText(14, 106, str(self.item.quantidade))

            painter.end()
            drag.setMimeData(mime)
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos().toPoint())
            drag.exec(Qt.MoveAction)
        super().mouseMoveEvent(event)


class KanbanColumn(QGraphicsRectItem):
    """Coluna com header profissional, contador, subtotal e empty state."""

    def __init__(self, coluna: ColunaKanban, x: float, height: float, scheme=None, parent=None):
        super().__init__(x, 0, COLUMN_WIDTH, height, parent)
        self.coluna = coluna
        self._scheme = scheme
        self._cards: list[KanbanCard] = []
        self._height = height
        self._drag_highlight = False

        cores = _column_colors(self._scheme).get(coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])

        self.setBrush(QBrush(QColor(cores["bg"])))
        self.setPen(QPen(QColor(cores["border"]), 1))
        self.setZValue(0)

        # === HEADER ===
        self._header = QGraphicsRectItem(x, 0, COLUMN_WIDTH, COLUMN_HEADER_HEIGHT, parent)
        self._header.setBrush(QBrush(QColor(cores["header"])))
        self._header.setPen(QPen(Qt.NoPen))
        self._header.setZValue(2)

        # Column title
        self._title = QGraphicsTextItem(coluna.label, parent)
        self._title.setPos(x + 14, 14)
        self._title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._title.setDefaultTextColor(QColor(cores["header_text"]))
        self._title.setZValue(3)

        # Count badge (circle)
        badge_size = 22
        badge_x = x + COLUMN_WIDTH - 36
        self._count_badge = QGraphicsRectItem(badge_x, 15, badge_size, badge_size, parent)
        self._count_badge.setBrush(QBrush(QColor(255, 255, 255, 60)))
        self._count_badge.setPen(QPen(Qt.NoPen))
        self._count_badge.setZValue(3)
        self._count_badge_radius = badge_size

        self._count_text = QGraphicsTextItem("0", parent)
        self._count_text.setPos(badge_x + 5, 16)
        self._count_text.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._count_text.setDefaultTextColor(QColor("#FFFFFF"))
        self._count_text.setZValue(4)

        # === SUBTOTAL ===
        self._subtotal_text = QGraphicsTextItem("", parent)
        self._subtotal_text.setPos(x + 14, COLUMN_HEADER_HEIGHT + 6)
        self._subtotal_text.setFont(QFont("Segoe UI", 8))
        self._subtotal_text.setZValue(2)
        self._update_subtotal_color()

        # === EMPTY STATE ===
        self._empty_label = QGraphicsTextItem("Nenhum item", parent)
        self._empty_label.setPos(x + 14, height / 2 - 10)
        self._empty_label.setFont(QFont("Segoe UI", 9))
        self._empty_label.setDefaultTextColor(QColor(cores["empty_text"]))
        self._empty_label.setZValue(2)
        self._empty_label.setVisible(True)

        # Separator line below header
        self._sep = QGraphicsRectItem(x, COLUMN_HEADER_HEIGHT, COLUMN_WIDTH, 1, parent)
        self._sep.setBrush(QBrush(QColor(cores["border"])))
        self._sep.setPen(QPen(Qt.NoPen))
        self._sep.setZValue(2)

        self._update_count()

    def _update_subtotal_color(self):
        cores = _column_colors(self._scheme).get(self.coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])
        self._subtotal_text.setDefaultTextColor(QColor(cores["accent"]))

    def set_scheme(self, scheme):
        self._scheme = scheme
        cores = _column_colors(scheme).get(self.coluna, _column_colors(scheme)[ColunaKanban.EM_ESTOQUE])

        self.setBrush(QBrush(QColor(cores["bg"])))
        self.setPen(QPen(QColor(cores["border"]), 1))
        self._header.setBrush(QBrush(QColor(cores["header"])))
        self._title.setDefaultTextColor(QColor(cores["header_text"]))
        self._empty_label.setDefaultTextColor(QColor(cores["empty_text"]))
        self._sep.setBrush(QBrush(QColor(cores["border"])))
        self._update_subtotal_color()

        for card in self._cards:
            card.set_scheme(scheme)

    def _update_count(self):
        n = len(self._cards)
        self._count_text.setPlainText(str(n))
        self._empty_label.setVisible(n == 0)

        # Update subtotal
        total = sum(c.item.quantidade for c in self._cards)
        if n > 0:
            self._subtotal_text.setPlainText(f"{total} un. total")
        else:
            self._subtotal_text.setPlainText("")

    def add_card(self, card: KanbanCard):
        self._cards.append(card)
        idx = self._cards.index(card)
        y = COLUMN_HEADER_HEIGHT + 24 + idx * (CARD_HEIGHT + CARD_MARGIN)
        card.setParentItem(self)
        card.setPos(10, y)
        self._update_count()

    def remove_card(self, card: KanbanCard):
        if card in self._cards:
            self._cards.remove(card)
            self._update_count()
            self._reflow()

    def _reflow(self):
        for i, card in enumerate(self._cards):
            y = COLUMN_HEADER_HEIGHT + 24 + i * (CARD_HEIGHT + CARD_MARGIN)
            card.setPos(10, y)
        self._update_count()

    def get_card_at(self, y: float) -> int:
        for i, card in enumerate(self._cards):
            card_y = COLUMN_HEADER_HEIGHT + 24 + i * (CARD_HEIGHT + CARD_MARGIN)
            if card_y <= y <= card_y + CARD_HEIGHT:
                return i
        return len(self._cards)

    def resize_height(self, h: float):
        self._height = h
        self.setRect(self.x(), 0, COLUMN_WIDTH, h)
        self._header.setRect(self.x(), 0, COLUMN_WIDTH, COLUMN_HEADER_HEIGHT)
        self._empty_label.setPos(self.x() + 14, h / 2 - 10)

    def cards(self) -> list[KanbanCard]:
        return self._cards

    def set_drag_highlight(self, active: bool):
        self._drag_highlight = active
        cores = _column_colors(self._scheme).get(self.coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])
        if active:
            highlight = QColor(cores["accent"])
            highlight.setAlpha(30)
            self.setBrush(QBrush(highlight))
        else:
            self.setBrush(QBrush(QColor(cores["bg"])))


class KanbanScene(QGraphicsScene):
    item_dropped = Signal(str, str)
    card_double_clicked = Signal(object)

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        self._columns: dict[ColunaKanban, KanbanColumn] = {}
        self._setup_columns()

    def _setup_columns(self):
        total_w = COLUMN_WIDTH * 4 + COLUMN_SPACING * 3 + BOARD_PADDING * 2
        colunas = [
            ColunaKanban.A_COMPRAR,
            ColunaKanban.EM_ESTOQUE,
            ColunaKanban.EM_USO,
            ColunaKanban.CRITICO,
        ]
        for i, coluna in enumerate(colunas):
            x = BOARD_PADDING + i * (COLUMN_WIDTH + COLUMN_SPACING)
            col = KanbanColumn(coluna, x, 700, scheme=self._scheme)
            self._columns[coluna] = col
            self.addItem(col)
            self.addItem(col._header)
            self.addItem(col._title)
            self.addItem(col._count_badge)
            self.addItem(col._count_text)
            self.addItem(col._subtotal_text)
            self.addItem(col._empty_label)
            self.addItem(col._sep)

        self.setSceneRect(0, 0, total_w, 800)

    def update_all(self, items_by_coluna: dict[ColunaKanban, list[ItemEstoque]]):
        for coluna, column in self._columns.items():
            items = items_by_coluna.get(coluna, [])
            for card in column.cards():
                self.removeItem(card)
            column._cards.clear()
            for idx, item in enumerate(items):
                card = KanbanCard(item, scheme=self._scheme)
                self.addItem(card)
                column.add_card(card)
                QTimer.singleShot(idx * 40, card.animate_fade_in)
            column._update_count()

    def get_column_for_x(self, x: float) -> ColunaKanban:
        for coluna, column in self._columns.items():
            if column.x() <= x <= column.x() + COLUMN_WIDTH:
                return coluna
        return ColunaKanban.EM_ESTOQUE

    def columns(self):
        return self._columns

    def update_theme(self, scheme):
        self._scheme = scheme
        for column in self._columns.values():
            column.set_scheme(scheme)


class KanbanView(QGraphicsView):
    """View principal do Kanban com drag-and-drop e visual profissional."""

    item_movido = Signal(str, str)

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setAcceptDrops(True)
        self._apply_scheme()

        self._scene = KanbanScene(scheme=scheme)
        self.setScene(self._scene)

        total_w = COLUMN_WIDTH * 4 + COLUMN_SPACING * 3 + BOARD_PADDING * 2
        self.setMinimumWidth(total_w)

    def _apply_scheme(self):
        if self._scheme:
            self.setStyleSheet(
                f"QGraphicsView {{ background: {self._scheme.bg_secondary}; border: none; }}"
            )
        else:
            self.setStyleSheet("QGraphicsView { background: #F5F5F7; border: none; }")

    def set_scheme(self, scheme):
        self._scheme = scheme
        self._apply_scheme()
        if hasattr(self, "_scene"):
            self._scene.update_theme(scheme)

    def update_board(self, items: list[ItemEstoque]):
        by_coluna: dict[ColunaKanban, list[ItemEstoque]] = {
            ColunaKanban.A_COMPRAR: [],
            ColunaKanban.EM_ESTOQUE: [],
            ColunaKanban.EM_USO: [],
            ColunaKanban.CRITICO: [],
        }
        for item in items:
            coluna = item.coluna
            if coluna in by_coluna:
                by_coluna[coluna].append(item)
            else:
                by_coluna[ColunaKanban.EM_ESTOQUE].append(item)
        self._scene.update_all(by_coluna)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-kanban-item"):
            event.acceptProposedAction()
            self._highlight_columns(True)
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasFormat("application/x-kanban-item"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._highlight_columns(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._highlight_columns(False)
        if event.mimeData().hasFormat("application/x-kanban-item"):
            item_id = event.mimeData().data("application/x-kanban-item").data().decode()
            pos = event.scenePos()
            nova_coluna = self._scene.get_column_for_x(pos.x())
            self.item_movido.emit(item_id, nova_coluna.value)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def _highlight_columns(self, active: bool):
        for col in self._scene.columns().values():
            col.set_drag_highlight(active)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.viewport().height()
        for col in self._scene.columns().values():
            col.resize_height(h)
        self._scene.setSceneRect(
            0, 0, self._scene.sceneRect().width(), max(h, 700)
        )


class KPIBar(QWidget):
    """Barra de KPIs inspirada em dashboards WMS profissionais."""

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        self.setFixedHeight(72)
        self._setup_ui()

    def _setup_ui(self):
        s = self._scheme or get_scheme()
        self.setStyleSheet(f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(32)

        self._kpis: list[tuple[QLabel, QLabel]] = []

        kpi_defs = [
            ("total_items", "Total Itens", "0"),
            ("em_estoque", "Em Estoque", "0"),
            ("criticos", "Criticos", "0"),
            ("a_comprar", "A Comprar", "0"),
            ("total_unidades", "Total Unidades", "0"),
        ]

        for key, label, default in kpi_defs:
            kpi_widget = QWidget()
            kpi_widget.setStyleSheet("background: transparent; border: none;")
            kpi_layout = QVBoxLayout(kpi_widget)
            kpi_layout.setContentsMargins(0, 0, 0, 0)
            kpi_layout.setSpacing(2)

            value_label = QLabel(default)
            value_label.setStyleSheet(
                f"font-size: {TYPOGRAPHY.text_2xl}px; font-weight: {TYPOGRAPHY.weight_bold}; "
                f"color: {s.text_primary}; background: transparent; border: none;"
            )
            kpi_layout.addWidget(value_label)

            name_label = QLabel(label)
            name_label.setStyleSheet(
                f"font-size: {TYPOGRAPHY.text_xs}px; font-weight: {TYPOGRAPHY.weight_medium}; "
                f"color: {s.text_muted}; background: transparent; border: none;"
            )
            kpi_layout.addWidget(name_label)

            self._kpis.append((value_label, name_label))
            layout.addWidget(kpi_widget)

        layout.addStretch()

    def update_kpis(self, items: list[ItemEstoque]):
        total = len(items)
        em_estoque = sum(1 for i in items if i.coluna == ColunaKanban.EM_ESTOQUE)
        criticos = sum(1 for i in items if i.coluna == ColunaKanban.CRITICO)
        a_comprar = sum(1 for i in items if i.coluna == ColunaKanban.A_COMPRAR)
        total_un = sum(i.quantidade for i in items)

        values = [str(total), str(em_estoque), str(criticos), str(a_comprar), str(total_un)]
        accents = [None, "#2E9E5E", "#D32F2F", "#E85D5D", "#3578D8"]

        s = self._scheme or get_scheme()
        for (val_label, _), value, accent in zip(self._kpis, values, accents):
            val_label.setText(value)
            color = accent or s.text_primary
            val_label.setStyleSheet(
                f"font-size: {TYPOGRAPHY.text_2xl}px; font-weight: {TYPOGRAPHY.weight_bold}; "
                f"color: {color}; background: transparent; border: none;"
            )

    def set_scheme(self, scheme):
        self._scheme = scheme
        s = scheme or get_scheme()
        self.setStyleSheet(f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};")
        for val_label, name_label in self._kpis:
            val_label.setStyleSheet(
                f"font-size: {TYPOGRAPHY.text_2xl}px; font-weight: {TYPOGRAPHY.weight_bold}; "
                f"color: {s.text_primary}; background: transparent; border: none;"
            )
            name_label.setStyleSheet(
                f"font-size: {TYPOGRAPHY.text_xs}px; font-weight: {TYPOGRAPHY.weight_medium}; "
                f"color: {s.text_muted}; background: transparent; border: none;"
            )


class KanbanContainer(QWidget):
    """Wrapper com KPI bar + header + kanban view."""

    item_movido = Signal(str, str)
    card_clicado = Signal(object)
    card_duplo_clicado = Signal(object)

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # KPI bar
        self.kpi_bar = KPIBar(scheme=scheme)
        layout.addWidget(self.kpi_bar)

        # Header
        self.header = QWidget()
        self.header.setFixedHeight(48)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        self.title = QLabel("Kanban - Controle de Estoque")
        header_layout.addWidget(self.title)
        header_layout.addStretch()

        self._apply_header_scheme()
        layout.addWidget(self.header)

        # Kanban view
        self.kanban_view = KanbanView(scheme=scheme)
        self.kanban_view.item_movido.connect(self.item_movido.emit)
        layout.addWidget(self.kanban_view, 1)

    def _apply_header_scheme(self):
        s = self._scheme
        if s:
            self.header.setStyleSheet(
                f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};"
            )
            self.title.setStyleSheet(
                f"font-size: {TYPOGRAPHY.text_xl}px; font-weight: {TYPOGRAPHY.weight_bold}; "
                f"color: {s.text_primary}; background: transparent; border: none;"
            )
        else:
            self.header.setStyleSheet("background: #F5F5F7; border-bottom: 1px solid #E5E5EA;")
            self.title.setStyleSheet(
                f"font-size: {TYPOGRAPHY.text_xl}px; font-weight: {TYPOGRAPHY.weight_bold}; "
                f"color: #1A1A2E; background: transparent; border: none;"
            )

    def set_scheme(self, scheme):
        self._scheme = scheme
        self._apply_header_scheme()
        self.kpi_bar.set_scheme(scheme)
        self.kanban_view.set_scheme(scheme)

    def update_board(self, items: list[ItemEstoque]):
        self.kpi_bar.update_kpis(items)
        self.kanban_view.update_board(items)

    def refresh(self):
        """Recarrega todos os itens do servico de estoque."""
        from core.inventory import get_inventory_service
        items = get_inventory_service().get_all_items()
        self.update_board(items)
