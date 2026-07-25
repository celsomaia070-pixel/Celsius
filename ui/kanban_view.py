from PySide6.QtCore import QEasingCurve, QMimeData, QTimer, QTimeLine, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsEllipseItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.inventory import ColunaKanban, ItemEstoque, Movimentacao
from ui.theme.schemes import ColorScheme, get_scheme
from ui.theme.tokens import SPACING, RADIUS, TYPOGRAPHY


CARD_WIDTH = 220
CARD_HEIGHT = 140
CARD_MARGIN = 10
COLUMN_WIDTH = 260
COLUMN_HEADER_HEIGHT = 44
COLUMN_SPACING = 16


def _column_colors(scheme: ColorScheme | None = None) -> dict:
    """Retorna cores das colunas adaptadas ao tema atual."""
    is_dark = scheme and scheme.bg_primary.startswith("#0")
    if is_dark:
        return {
            ColunaKanban.A_COMPRAR: {
                "header": "#DA3633", "bg": "#3D1A1A", "border": "#DA3633", "dot": "#FF6B6B",
            },
            ColunaKanban.EM_ESTOQUE: {
                "header": "#2EA043", "bg": "#163D2A", "border": "#2EA043", "dot": "#4ECDC4",
            },
            ColunaKanban.EM_USO: {
                "header": "#1F6FEB", "bg": "#1A3A5C", "border": "#1F6FEB", "dot": "#45B7D1",
            },
            ColunaKanban.CRITICO: {
                "header": "#F85149", "bg": "#4D1A1A", "border": "#F85149", "dot": "#E74C3C",
            },
        }
    return {
        ColunaKanban.A_COMPRAR: {
            "header": "#FF6B6B", "bg": "#FFF5F5", "border": "#FF6B6B", "dot": "#FF6B6B",
        },
        ColunaKanban.EM_ESTOQUE: {
            "header": "#4ECDC4", "bg": "#F0FFFE", "border": "#4ECDC4", "dot": "#4ECDC4",
        },
        ColunaKanban.EM_USO: {
            "header": "#45B7D1", "bg": "#F0F9FF", "border": "#45B7D1", "dot": "#45B7D1",
        },
        ColunaKanban.CRITICO: {
            "header": "#E74C3C", "bg": "#FFF0F0", "border": "#E74C3C", "dot": "#E74C3C",
        },
    }


class KanbanCard(QGraphicsRectItem):
    """Arrastavel."""

    card_clicked = Signal(object)
    entrada_clicked = Signal(object)
    saida_clicked = Signal(object)

    def __init__(self, item: ItemEstoque, scheme=None, parent=None):
        super().__init__(0, 0, CARD_WIDTH, CARD_HEIGHT, parent)
        self.item = item
        self._scheme = scheme
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptDrops(False)
        self.setCursor(Qt.PointingHandCursor)

        coluna = item.coluna
        cores = _column_colors(self._scheme).get(coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])

        self.setBrush(QBrush(QColor(cores["bg"])))
        self.setPen(QPen(QColor(cores["border"]), 1.5))
        self.setZValue(1)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(2, 2)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

        self._build_content(item, cores)

    def _build_content(self, item: ItemEstoque, cores: dict):
        # dot de status
        self._dot = QGraphicsEllipseItem(12, 12, 10, 10, self)
        self._dot.setBrush(QBrush(QColor(cores["dot"])))
        self._dot.setPen(QPen(Qt.NoPen))

        # nome
        self._name_text = QGraphicsTextItem(item.nome, self)
        self._name_text.setPos(28, 8)
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        self._name_text.setFont(font)
        self._name_text.setDefaultTextColor(QColor(self._text_primary()))

        # categoria
        self._cat_text = QGraphicsTextItem(item.categoria, self)
        self._cat_text.setPos(28, 28)
        font_cat = QFont("Segoe UI", 9)
        self._cat_text.setFont(font_cat)
        self._cat_text.setDefaultTextColor(QColor(self._text_secondary()))

        # quantidade
        qtd_color = cores["dot"]
        self._qtd_text = QGraphicsTextItem(f"{item.quantidade} un.", self)
        self._qtd_text.setPos(12, 56)
        font_qtd = QFont("Segoe UI", 16, QFont.Weight.Bold)
        self._qtd_text.setFont(font_qtd)
        self._qtd_text.setDefaultTextColor(QColor(qtd_color))

        # min / max
        self._range_text = QGraphicsTextItem(f"min: {item.estoque_min}  max: {item.estoque_max}", self)
        self._range_text.setPos(12, 92)
        font_range = QFont("Segoe UI", 8)
        self._range_text.setFont(font_range)
        self._range_text.setDefaultTextColor(QColor(self._text_muted()))

        # barra de progresso
        bar_y = 115
        bar_w = CARD_WIDTH - 24
        bar_h = 6
        self._bar_bg = QGraphicsRectItem(12, bar_y, bar_w, bar_h, self)
        self._bar_bg.setBrush(QBrush(QColor(self._border_default())))
        self._bar_bg.setPen(QPen(Qt.NoPen))

        pct = min(item.quantidade / max(item.estoque_max, 1), 1.0)
        fill_w = max(int(bar_w * pct), 2)
        self._bar_fill = QGraphicsRectItem(12, bar_y, fill_w, bar_h, self)
        self._bar_fill.setBrush(QBrush(QColor(cores["dot"])))
        self._bar_fill.setPen(QPen(Qt.NoPen))

    def _text_primary(self):
        return self._scheme.text_primary if self._scheme else "#1A1A1B"

    def _text_secondary(self):
        return self._scheme.text_secondary if self._scheme else "#8E8E93"

    def _text_muted(self):
        return self._scheme.text_muted if self._scheme else "#AEAEB2"

    def _border_default(self):
        return self._scheme.border_default if self._scheme else "#E5E5EA"

    def set_scheme(self, scheme):
        self._scheme = scheme
        self._name_text.setDefaultTextColor(QColor(self._text_primary()))
        self._cat_text.setDefaultTextColor(QColor(self._text_secondary()))
        self._range_text.setDefaultTextColor(QColor(self._text_muted()))
        self._bar_bg.setBrush(QBrush(QColor(self._border_default())))

    def atualizar(self, item: ItemEstoque):
        self.item = item
        coluna = item.coluna
        cores = _column_colors(self._scheme).get(coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])
        self.setBrush(QBrush(QColor(cores["bg"])))
        self.setPen(QPen(QColor(cores["border"]), 1.5))
        self._dot.setBrush(QBrush(QColor(cores["dot"])))
        self._name_text.setPlainText(item.nome)
        self._cat_text.setPlainText(item.categoria)
        self._qtd_text.setPlainText(f"{item.quantidade} un.")
        self._qtd_text.setDefaultTextColor(QColor(cores["dot"]))
        self._range_text.setPlainText(f"min: {item.estoque_min}  max: {item.estoque_max}")

        pct = min(item.quantidade / max(item.estoque_max, 1), 1.0)
        bar_w = CARD_WIDTH - 24
        fill_w = max(int(bar_w * pct), 2)
        self._bar_fill.setRect(12, 115, fill_w, 6)
        self._bar_fill.setBrush(QBrush(QColor(cores["dot"])))

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def animate_fade_in(self):
        self._timeline = QTimeLine(300)
        self._timeline.setFrameRange(0, 10)
        self._timeline.frameChanged.connect(self._on_fade_frame)
        self._timeline.start()

    def _on_fade_frame(self, frame):
        self.setOpacity(frame / 10.0)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            drag = QDrag(event.widget())
            mime = QMimeData()
            mime.setData("application/x-kanban-item", self.item.id.encode())
            pixmap = QPixmap(CARD_WIDTH, CARD_HEIGHT)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            coluna = self.item.coluna
            cores = _column_colors(self._scheme).get(coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])
            painter.setBrush(QColor(cores["bg"]))
            painter.setPen(QPen(QColor(cores["border"]), 1.5))
            painter.drawRoundedRect(0, 0, CARD_WIDTH, CARD_HEIGHT, 8, 8)
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.setPen(QColor(self._text_primary()))
            painter.drawText(28, 26, self.item.nome)
            painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            painter.setPen(QColor(cores["dot"]))
            painter.drawText(12, 76, f"{self.item.quantidade} un.")
            painter.end()
            drag.setMimeData(mime)
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos().toPoint())
            drag.exec(Qt.MoveAction)
        super().mouseMoveEvent(event)


class KanbanColumn(QGraphicsRectItem):
    """Coluna do Kanban com header + area de drop."""

    item_dropped = Signal(str, str)  # item_id, nova_coluna

    def __init__(self, coluna: ColunaKanban, x: float, height: float, scheme=None, parent=None):
        super().__init__(x, 0, COLUMN_WIDTH, height, parent)
        self.coluna = coluna
        self._scheme = scheme
        self._cards: list[KanbanCard] = []
        self._height = height

        self._apply_column_colors()

        # header
        self._header = QGraphicsRectItem(x, 0, COLUMN_WIDTH, COLUMN_HEADER_HEIGHT, parent)
        self._header.setBrush(QBrush(QColor(self._header_color())))
        self._header.setPen(QPen(Qt.NoPen))
        self._header.setZValue(2)

        self._title = QGraphicsTextItem(coluna.label, parent)
        self._title.setPos(x + 12, 10)
        font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        self._title.setFont(font)
        header_text = "#FFFFFF"
        if scheme and not scheme.bg_primary.startswith("#0"):
            header_text = "#FFFFFF"
        self._title.setDefaultTextColor(QColor(header_text))
        self._title.setZValue(3)

        self._count_text = QGraphicsTextItem("0", parent)
        self._count_text.setPos(x + COLUMN_WIDTH - 30, 10)
        self._count_text.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._count_text.setDefaultTextColor(QColor(header_text))
        self._count_text.setZValue(3)

        self._update_count()

    def _apply_column_colors(self):
        cores = _column_colors(self._scheme).get(self.coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])
        self.setBrush(QBrush(QColor(cores["bg"])))
        self.setPen(QPen(QColor(cores["border"]), 1))

    def _header_color(self):
        cores = _column_colors(self._scheme).get(self.coluna, _column_colors(self._scheme)[ColunaKanban.EM_ESTOQUE])
        return cores["header"]

    def set_scheme(self, scheme):
        self._scheme = scheme
        self._apply_column_colors()
        self._header.setBrush(QBrush(QColor(self._header_color())))
        for card in self._cards:
            card.set_scheme(scheme)

    def _update_count(self):
        self._count_text.setPlainText(str(len(self._cards)))

    def add_card(self, card: KanbanCard):
        self._cards.append(card)
        idx = self._cards.index(card)
        y = COLUMN_HEADER_HEIGHT + 10 + idx * (CARD_HEIGHT + CARD_MARGIN)
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
            y = COLUMN_HEADER_HEIGHT + 10 + i * (CARD_HEIGHT + CARD_MARGIN)
            card.setPos(10, y)

    def get_card_at(self, y: float) -> int:
        for i, card in enumerate(self._cards):
            card_y = COLUMN_HEADER_HEIGHT + 10 + i * (CARD_HEIGHT + CARD_MARGIN)
            if card_y <= y <= card_y + CARD_HEIGHT:
                return i
        return len(self._cards)

    def resize_height(self, h: float):
        self._height = h
        self.setRect(self.x(), 0, COLUMN_WIDTH, h)
        self._header.setRect(self.x(), 0, COLUMN_WIDTH, COLUMN_HEADER_HEIGHT)

    def cards(self) -> list[KanbanCard]:
        return self._cards

    def update_cards(self, items: list[ItemEstoque]):
        for card in self._cards:
            card.scene().removeItem(card)
        self._cards.clear()
        for item in items:
            card = KanbanCard(item, scheme=self._scheme)
            self.add_card(card)


class KanbanScene(QGraphicsScene):
    item_dropped = Signal(str, str)
    card_double_clicked = Signal(object)

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        self._columns: dict[ColunaKanban, KanbanColumn] = {}
        self._drag_coluna = None
        self._setup_columns()

    def _setup_columns(self):
        total_w = COLUMN_WIDTH * 4 + COLUMN_SPACING * 3 + 40
        colunas = [
            ColunaKanban.A_COMPRAR,
            ColunaKanban.EM_ESTOQUE,
            ColunaKanban.EM_USO,
            ColunaKanban.CRITICO,
        ]
        for i, coluna in enumerate(colunas):
            x = 20 + i * (COLUMN_WIDTH + COLUMN_SPACING)
            col = KanbanColumn(coluna, x, 700, scheme=self._scheme)
            self._columns[coluna] = col
            self.addItem(col)
            self.addItem(col._header)
            self.addItem(col._title)
            self.addItem(col._count_text)

        total_h = 800
        self.setSceneRect(0, 0, total_w, total_h)

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
                QTimer.singleShot(idx * 50, card.animate_fade_in)

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
    """View principal do Kanban."""

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

        total_w = COLUMN_WIDTH * 4 + COLUMN_SPACING * 3 + 80
        self.setMinimumWidth(total_w)

    def _apply_scheme(self):
        if self._scheme:
            self.setStyleSheet(f"QGraphicsView {{ background: {self._scheme.bg_secondary}; border: none; }}")
        else:
            self.setStyleSheet("QGraphicsView { background: #F5F5F7; border: none; }")

    def set_scheme(self, scheme):
        self._scheme = scheme
        self._apply_scheme()
        if hasattr(self, '_scene'):
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
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasFormat("application/x-kanban-item"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-kanban-item"):
            item_id = event.mimeData().data("application/x-kanban-item").data().decode()
            pos = event.scenePos()
            nova_coluna = self._scene.get_column_for_x(pos.x())
            self.item_movido.emit(item_id, nova_coluna.value)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.viewport().height()
        for col in self._scene.columns().values():
            col.resize_height(h)
        self._scene.setSceneRect(0, 0, self._scene.sceneRect().width(), max(h, 700))


class KanbanContainer(QWidget):
    """Wrapper widget com scroll horizontal."""

    item_movido = Signal(str, str)
    card_clicado = Signal(object)
    card_duplo_clicado = Signal(object)

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # header com titulo
        self.header = QWidget()
        self.header.setFixedHeight(48)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 0, 20, 0)
        self.title = QLabel("Kanban - Controle de Estoque")
        self.title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #1A1A1B; "
            "background: transparent; border: none;"
        )
        header_layout.addWidget(self.title)
        header_layout.addStretch()

        self._apply_header_scheme()

        layout.addWidget(self.header)

        # view
        self.kanban_view = KanbanView(scheme=scheme)
        self.kanban_view.item_movido.connect(self.item_movido.emit)
        layout.addWidget(self.kanban_view, 1)

    def _apply_header_scheme(self):
        if self._scheme:
            s = self._scheme
            self.header.setStyleSheet(f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};")
            self.title.setStyleSheet(f"font-size: {TYPOGRAPHY.text_2xl}px; font-weight: {TYPOGRAPHY.weight_bold}; color: {s.text_primary}; background: transparent; border: none;")
        else:
            self.header.setStyleSheet(f"background: #F5F5F7; border-bottom: 1px solid #E5E5EA;")
            self.title.setStyleSheet(f"font-size: {TYPOGRAPHY.text_2xl}px; font-weight: {TYPOGRAPHY.weight_bold}; color: #1A1A1B; background: transparent; border: none;")

    def set_scheme(self, scheme):
        self._scheme = scheme
        self._apply_header_scheme()
        self.kanban_view.set_scheme(scheme)

    def update_board(self, items: list[ItemEstoque]):
        self.kanban_view.update_board(items)
