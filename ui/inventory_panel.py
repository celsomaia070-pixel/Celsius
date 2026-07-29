"""
InventoryPanel - Painel de estoque com design moderno inspirado em Sortly/Katana.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.inventory import ColunaKanban, ItemEstoque, Movimentacao, get_inventory_service
from ui.theme.schemes import get_scheme


def _stock_health_color(item: ItemEstoque, scheme=None) -> tuple[str, str]:
    coluna = item.coluna
    if scheme and scheme.bg_primary.startswith("#0"):
        if coluna == ColunaKanban.CRITICO:
            return scheme.error_bg, scheme.error_text
        if coluna == ColunaKanban.A_COMPRAR:
            return scheme.warning_bg, scheme.warning_text
        if coluna == ColunaKanban.EM_ESTOQUE:
            return scheme.success_bg, scheme.success_text
        if coluna == ColunaKanban.EM_USO:
            return scheme.info_bg, scheme.info_text
        return scheme.bg_tertiary, scheme.text_muted

    cores = {
        ColunaKanban.CRITICO: ("#FFF0F0", "#C62828"),
        ColunaKanban.A_COMPRAR: ("#FFF8E1", "#E65100"),
        ColunaKanban.EM_ESTOQUE: ("#E8F5E9", "#1B5E20"),
        ColunaKanban.EM_USO: ("#E3F2FD", "#1565C0"),
    }
    return cores.get(coluna, ("#F5F5F5", "#757575"))


def _stock_bar_color(item: ItemEstoque) -> str:
    if item.quantidade <= 0:
        return "#C62828"
    if item.quantidade <= item.estoque_min:
        return "#E85D5D"
    pct = item.quantidade / max(item.estoque_max, 1)
    if pct < 0.3:
        return "#F57C00"
    if pct < 0.7:
        return "#FBC02D"
    return "#2E9E5E"


class MovimentacaoItem(QWidget):
    """Item de historico com design limpo."""

    def __init__(self, mov: Movimentacao, scheme=None, parent=None):
        super().__init__(parent)
        s = scheme or get_scheme()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        is_entrada = mov.tipo == "entrada"
        sinal = "+" if is_entrada else "-"
        cor = s.success_text if is_entrada else s.error_text
        bg = s.success_bg if is_entrada else s.error_bg

        tag = QLabel(sinal)
        tag.setFixedSize(28, 28)
        tag.setAlignment(Qt.AlignCenter)
        tag.setStyleSheet(
            f"background: {bg}; color: {cor}; border-radius: 14px; "
            f"font-size: 14px; font-weight: 800; border: none;"
        )
        layout.addWidget(tag, 0, Qt.AlignCenter)

        info = QVBoxLayout()
        info.setSpacing(2)

        name = QLabel(mov.item_nome)
        name.setStyleSheet(
            f"color: {s.text_primary}; font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        info.addWidget(name)

        qty_text = f"{sinal}{mov.quantidade} un"
        if mov.quantidade_anterior != mov.quantidade_nova:
            qty_text += f"  ({mov.quantidade_anterior} → {mov.quantidade_nova})"
        qty = QLabel(qty_text)
        qty.setStyleSheet(
            f"color: {cor}; font-size: 11px; font-weight: 500; "
            f"background: transparent; border: none;"
        )
        info.addWidget(qty)
        layout.addLayout(info, 1)

        ts = mov.timestamp.split(" ")[1] if " " in mov.timestamp else mov.timestamp
        time_label = QLabel(ts)
        time_label.setStyleSheet(
            f"color: {s.text_muted}; font-size: 11px; background: transparent; border: none;"
        )
        layout.addWidget(time_label, 0, Qt.AlignRight | Qt.AlignCenter)


class CategoryHeader(QWidget):
    """Header de categoria expansivel."""

    def __init__(self, categoria: str, count: int, scheme=None, parent=None):
        super().__init__(parent)
        s = scheme or get_scheme()
        self.setFixedHeight(36)
        self.setStyleSheet(
            f"background: {s.bg_secondary}; border-bottom: 1px solid {s.border_default};"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        indicator = QLabel("▼")
        indicator.setFixedSize(12, 12)
        indicator.setStyleSheet(
            f"color: {s.text_muted}; font-size: 8px; background: transparent; border: none;"
        )
        layout.addWidget(indicator)

        label = QLabel(categoria)
        label.setStyleSheet(
            f"color: {s.text_primary}; font-size: 12px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(label)

        badge = QLabel(str(count))
        badge.setFixedSize(20, 20)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"color: {s.text_muted}; font-size: 10px; font-weight: 600; "
            f"background: {s.bg_primary}; border: 1px solid {s.border_default}; "
            f"border-radius: 10px; border: none;"
        )
        layout.addWidget(badge)
        layout.addStretch()


class StockHealthBar(QWidget):
    """Barra de saude do estoque."""

    def __init__(self, item: ItemEstoque, width: int = 80, scheme=None, parent=None):
        super().__init__(parent)
        s = scheme or get_scheme()
        self.setFixedSize(width, 16)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(0)

        bar_w = width - 35
        pct = min(item.quantidade / max(item.estoque_max, 1), 1.0)
        fill_w = max(int(bar_w * pct), 2)
        color = _stock_bar_color(item)

        bg_bar = QLabel()
        bg_bar.setFixedSize(bar_w, 4)
        bg_bar.setStyleSheet(f"background: {s.border_default}; border-radius: 2px; border: none;")
        layout.addWidget(bg_bar)

        fill_bar = QLabel()
        fill_bar.setFixedSize(fill_w, 4)
        fill_bar.setStyleSheet(f"background: {color}; border-radius: 2px; border: none;")
        layout.addWidget(fill_bar)

        layout.addSpacing(4)

        pct_label = QLabel(f"{int(pct * 100)}%")
        pct_label.setStyleSheet(
            f"color: {s.text_muted}; font-size: 9px; background: transparent; border: none;"
        )
        layout.addWidget(pct_label, 0, Qt.AlignCenter)


class ItemDialog(QDialog):
    """Dialog moderno para adicionar/editar item."""

    def __init__(self, scheme=None, parent=None, item: ItemEstoque | None = None):
        super().__init__(parent)
        s = scheme or get_scheme()
        self._item = item
        self._result_data = None

        self.setWindowTitle("Editar Item" if item else "Novo Item")
        self.setMinimumWidth(380)
        self.setStyleSheet(f"""
            QDialog {{ background: {s.bg_primary}; }}
            QLabel {{ color: {s.text_primary}; font-size: 13px; background: transparent; border: none; }}
            QLineEdit, QSpinBox, QComboBox {{
                background: {s.bg_secondary}; border: 1px solid {s.border_default};
                border-radius: 8px; padding: 8px 12px; font-size: 13px; color: {s.text_primary};
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border-color: {s.accent_primary};
            }}
            QPushButton {{
                border-radius: 8px; font-size: 13px; font-weight: 600; padding: 8px 20px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Editar Item" if item else "Adicionar Novo Item")
        title.setStyleSheet(
            f"color: {s.text_primary}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none; margin-bottom: 8px;"
        )
        layout.addWidget(title)

        for label_text, attr, placeholder in [
            ("Nome", "nome", "Ex: Parafuso M8"),
            ("Categoria", "categoria", "Ex: Pecas, Ferramentas"),
        ]:
            lbl = QLabel(label_text)
            layout.addWidget(lbl)
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            if item and attr == "nome":
                inp.setText(item.nome)
            elif item and attr == "categoria":
                inp.setText(item.categoria)
            setattr(self, f"_{attr}", inp)
            layout.addWidget(inp)

        qty_row = QHBoxLayout()
        qty_row.setSpacing(12)
        for label_text, attr, default in [
            ("Quantidade", "qtd", item.quantidade if item else 0),
            ("Minimo", "min", item.estoque_min if item else 0),
            ("Maximo", "max", item.estoque_max if item else 100),
        ]:
            col = QVBoxLayout()
            col.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {s.text_secondary}; font-size: 11px; background: transparent; border: none;"
            )
            col.addWidget(lbl)
            spin = QSpinBox()
            spin.setRange(0, 99999)
            spin.setValue(default)
            setattr(self, f"_{attr}", spin)
            col.addWidget(spin)
            qty_row.addLayout(col)
        layout.addLayout(qty_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel = QPushButton("Cancelar")
        cancel.setStyleSheet(
            f"background: {s.bg_secondary}; color: {s.text_primary}; border: 1px solid {s.border_default};"
        )
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        save = QPushButton("Salvar")
        save.setStyleSheet(f"background: {s.accent_primary}; color: #FFFFFF; border: none;")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._on_save)
        btn_row.addWidget(save)

        layout.addLayout(btn_row)

    def _on_save(self):
        nome = self._nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Erro", "Nome e obrigatorio.")
            return
        self._result_data = {
            "nome": nome,
            "categoria": self._categoria.text().strip() or "Geral",
            "quantidade": self._qtd.value(),
            "estoque_min": self._min.value(),
            "estoque_max": self._max.value(),
        }
        self.accept()

    def get_data(self) -> dict | None:
        return self._result_data


class InventoryPanel(QWidget):
    """Painel de estoque com design moderno."""

    entrada_solicitada = Signal(str)
    saida_solicitada = Signal(str)
    item_selecionado = Signal(str)

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or get_scheme()
        self._service = get_inventory_service()
        self._selected_item_id = None
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        s = self._scheme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QWidget()
        self._header.setFixedHeight(48)
        self._header.setStyleSheet(
            f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};"
        )
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        self._title_label = QLabel("Estoque")
        self._title_label.setStyleSheet(
            f"color: {s.text_primary}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._btn_add = QPushButton("+ Novo Item")
        self._btn_add.setFixedHeight(32)
        self._btn_add.setCursor(Qt.PointingHandCursor)
        self._btn_add.setStyleSheet(f"""
            QPushButton {{
                background: {s.accent_primary}; color: #FFFFFF; border: none;
                border-radius: 8px; font-size: 12px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        self._btn_add.clicked.connect(self._show_add_dialog)
        header_layout.addWidget(self._btn_add)

        layout.addWidget(self._header)

        self._search_container = QWidget()
        self._search_container.setStyleSheet(
            f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};"
        )
        search_layout = QHBoxLayout(self._search_container)
        search_layout.setContentsMargins(16, 8, 16, 8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar itens...")
        self.search_input.setFixedHeight(34)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {s.bg_secondary}; border: 1px solid {s.border_default};
                border-radius: 8px; padding: 0 12px; font-size: 13px; color: {s.text_primary};
            }}
            QLineEdit:focus {{ border-color: {s.accent_primary}; }}
        """)
        self.search_input.textChanged.connect(self._filter_items)
        search_layout.addWidget(self.search_input)

        self.filter_combo = QComboBox()
        self.filter_combo.setFixedHeight(34)
        self.filter_combo.setFixedWidth(140)
        self.filter_combo.addItems(["Todos", "Criticos", "Estoque", "Em Uso", "A Comprar"])
        self.filter_combo.setStyleSheet(f"""
            QComboBox {{
                background: {s.bg_secondary}; border: 1px solid {s.border_default};
                border-radius: 8px; padding: 0 12px; font-size: 12px; color: {s.text_primary};
            }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid {s.text_muted}; }}
        """)
        self.filter_combo.currentTextChanged.connect(self._filter_items)
        search_layout.addWidget(self.filter_combo)

        layout.addWidget(self._search_container)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background: transparent; border: none; padding: 10px 20px;
                font-size: 13px; font-weight: 600; color: {s.text_muted};
            }}
            QTabBar::tab:selected {{
                color: {s.text_primary}; border-bottom: 2px solid {s.accent_primary};
            }}
        """)

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(7)
        self.items_table.setHorizontalHeaderLabels(
            ["Item", "Qtd", "Min", "Max", "Status", "Saude", ""]
        )
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setShowGrid(False)
        self.items_table.setFrameShape(QFrame.Shape.NoFrame)
        self.items_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.items_table.setSelectionMode(QTableWidget.NoSelection)
        self.items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.items_table.setAlternatingRowColors(False)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 7):
            self.items_table.horizontalHeader().setSectionResizeMode(
                i, QHeaderView.ResizeToContents
            )
        self.items_table.setColumnWidth(5, 100)
        self.items_table.setColumnWidth(6, 70)
        self.items_table.verticalHeader().setDefaultSectionSize(44)
        self.items_table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent; border: none; outline: none;
                gridline-color: transparent;
            }}
            QTableWidget::item {{
                background: transparent; border: none; padding: 2px 8px;
            }}
            QHeaderView::section {{
                background: transparent; border: none;
                color: {s.text_muted}; font-size: 11px; font-weight: 600;
                padding: 8px; text-align: left;
                border-bottom: 1px solid {s.border_default};
            }}
        """)
        self.tabs.addTab(self.items_table, "Itens")

        self.history_list = QListWidget()
        self.history_list.setFrameShape(QFrame.Shape.NoFrame)
        self.history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.history_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; padding: 4px 8px; } "
            "QListWidget::item { background: transparent; border: none; padding: 0; margin: 0; } "
            "QListWidget::item:selected { background: transparent; }"
        )
        self.tabs.addTab(self.history_list, "Historico")

        layout.addWidget(self.tabs, 1)

        self._stats_bar = QWidget()
        self._stats_bar.setFixedHeight(40)
        self._stats_bar.setStyleSheet(
            f"background: {s.bg_primary}; border-top: 1px solid {s.border_default};"
        )
        stats_layout = QHBoxLayout(self._stats_bar)
        stats_layout.setContentsMargins(16, 0, 16, 0)

        self._stats_label = QLabel("0 itens")
        self._stats_label.setStyleSheet(
            f"color: {s.text_muted}; font-size: 12px; background: transparent; border: none;"
        )
        stats_layout.addWidget(self._stats_label)
        stats_layout.addStretch()

        self._alertas_btn = QPushButton("Alertas")
        self._alertas_btn.setFixedHeight(26)
        self._alertas_btn.setCursor(Qt.PointingHandCursor)
        self._alertas_btn.setStyleSheet(f"""
            QPushButton {{
                background: {s.error_bg}; color: {s.error_text}; border: 1px solid {s.border_error};
                border-radius: 6px; font-size: 11px; font-weight: 600; padding: 0 12px;
            }}
            QPushButton:hover {{ background: {s.bg_hover}; }}
        """)
        self._alertas_btn.clicked.connect(self._show_alertas)
        stats_layout.addWidget(self._alertas_btn)

        layout.addWidget(self._stats_bar)

    def _apply_static_styles(self):
        s = self._scheme
        self.setStyleSheet(f"background: {s.bg_primary};")
        self._header.setStyleSheet(
            f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};"
        )
        self._title_label.setStyleSheet(
            f"color: {s.text_primary}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        self._btn_add.setStyleSheet(f"""
            QPushButton {{
                background: {s.accent_primary}; color: #FFFFFF; border: none;
                border-radius: 8px; font-size: 12px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        self._search_container.setStyleSheet(
            f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};"
        )
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {s.bg_secondary}; border: 1px solid {s.border_default};
                border-radius: 8px; padding: 0 12px; font-size: 13px; color: {s.text_primary};
            }}
            QLineEdit:focus {{ border-color: {s.accent_primary}; }}
        """)
        self.filter_combo.setStyleSheet(f"""
            QComboBox {{
                background: {s.bg_secondary}; border: 1px solid {s.border_default};
                border-radius: 8px; padding: 0 12px; font-size: 12px; color: {s.text_primary};
            }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid {s.text_muted}; }}
        """)
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background: transparent; border: none; padding: 10px 20px;
                font-size: 13px; font-weight: 600; color: {s.text_muted};
            }}
            QTabBar::tab:selected {{
                color: {s.text_primary}; border-bottom: 2px solid {s.accent_primary};
            }}
        """)
        self.items_table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent; border: none; outline: none;
                gridline-color: transparent;
            }}
            QTableWidget::item {{
                background: transparent; border: none; padding: 2px 8px;
            }}
            QHeaderView::section {{
                background: transparent; border: none;
                color: {s.text_muted}; font-size: 11px; font-weight: 600;
                padding: 8px; text-align: left;
                border-bottom: 1px solid {s.border_default};
            }}
        """)
        self.history_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; padding: 4px 8px; } "
            "QListWidget::item { background: transparent; border: none; padding: 0; margin: 0; } "
            "QListWidget::item:selected { background: transparent; }"
        )
        self._stats_bar.setStyleSheet(
            f"background: {s.bg_primary}; border-top: 1px solid {s.border_default};"
        )
        self._stats_label.setStyleSheet(
            f"color: {s.text_muted}; font-size: 12px; background: transparent; border: none;"
        )
        self._alertas_btn.setStyleSheet(f"""
            QPushButton {{
                background: {s.error_bg}; color: {s.error_text}; border: 1px solid {s.border_error};
                border-radius: 6px; font-size: 11px; font-weight: 600; padding: 0 12px;
            }}
            QPushButton:hover {{ background: {s.bg_hover}; }}
        """)

    def _show_add_dialog(self):
        dialog = ItemDialog(scheme=self._scheme, parent=self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if data:
                self._service.adicionar_item(**data)
                self.refresh()

    def _filter_items(self, text=None):
        search = self.search_input.text().lower()
        filter_text = self.filter_combo.currentText()

        for row in range(self.items_table.rowCount()):
            item_widget = self.items_table.cellWidget(row, 0)
            if not item_widget:
                continue

            nome_label = item_widget.findChild(QLabel)
            if not nome_label:
                continue

            visible = search in nome_label.text().lower()

            if filter_text != "Todos":
                status_label = self.items_table.cellWidget(row, 4)
                if status_label:
                    status_text = status_label.text().lower()
                    filter_map = {
                        "criticos": "critico" in status_text or "sem estoque" in status_text,
                        "estoque": "estoque" in status_text and "critico" not in status_text,
                        "em uso": "em uso" in status_text,
                        "a comprar": "a comprar" in status_text,
                    }
                    visible = visible and filter_map.get(filter_text.lower(), True)

            self.items_table.setRowHidden(row, not visible)

    def refresh(self):
        self.items_table.setRowCount(0)
        self.history_list.clear()

        items = self._service.get_all_items()

        categories = {}
        for item in items:
            cat = item.categoria or "Geral"
            categories.setdefault(cat, []).append(item)

        for cat_name in sorted(categories.keys()):
            cat_items = sorted(categories[cat_name], key=lambda i: i.nome)

            header_row = self.items_table.rowCount()
            self.items_table.insertRow(header_row)
            header_widget = CategoryHeader(cat_name, len(cat_items), scheme=self._scheme)
            self.items_table.setRowHeight(header_row, 36)
            self.items_table.setCellWidget(header_row, 0, header_widget)
            self.items_table.setSpan(header_row, 0, 1, 7)

            for item in cat_items:
                row = self.items_table.rowCount()
                self.items_table.insertRow(row)
                self.items_table.setRowHeight(row, 44)
                self._populate_row(row, item)

        movs = self._service.get_movimentacoes()
        for mov in reversed(movs[-50:]):
            widget = MovimentacaoItem(mov, scheme=self._scheme)
            list_item = QListWidgetItem()
            list_item.setSizeHint(widget.sizeHint())
            self.history_list.addItem(list_item)
            self.history_list.setItemWidget(list_item, widget)

        total = len(items)
        criticos = sum(1 for i in items if i.precisa_repor)
        self._stats_label.setText(
            f"{total} itens" + (f"  |  {criticos} em alerta" if criticos else "")
        )
        self._filter_items()

    def _populate_row(self, row: int, item: ItemEstoque):
        s = self._scheme
        bg, fg = _stock_health_color(item, s)

        name_widget = QWidget()
        name_layout = QHBoxLayout(name_widget)
        name_layout.setContentsMargins(8, 0, 4, 0)
        name_layout.setSpacing(8)

        dot = QLabel()
        dot_color = _stock_bar_color(item)
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {dot_color}; border-radius: 4px; border: none;")
        name_layout.addWidget(dot, 0, Qt.AlignCenter)

        nome = QLabel(item.nome)
        nome.setStyleSheet(
            f"color: {s.text_primary}; font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        nome.setToolTip(item.nome)
        name_layout.addWidget(nome, 1)

        self.items_table.setCellWidget(row, 0, name_widget)

        qtd_item = QTableWidgetItem(str(item.quantidade))
        qtd_item.setTextAlignment(Qt.AlignCenter)
        color = _stock_bar_color(item)
        qtd_item.setForeground(QColor(color))
        font = qtd_item.font()
        font.setBold(True)
        qtd_item.setFont(font)
        self.items_table.setItem(row, 1, qtd_item)

        for col, val in [(2, item.estoque_min), (3, item.estoque_max)]:
            cell = QTableWidgetItem(str(val))
            cell.setTextAlignment(Qt.AlignCenter)
            self.items_table.setItem(row, col, cell)

        status_label = QLabel(item.coluna.value.replace("_", " ").title())
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 10px; padding: 4px 12px; "
            f"font-size: 11px; font-weight: 600; border: none;"
        )
        self.items_table.setCellWidget(row, 4, status_label)

        health_bar = StockHealthBar(item, width=90, scheme=self._scheme)
        self.items_table.setCellWidget(row, 5, health_bar)

        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(2, 0, 2, 0)
        btn_layout.setSpacing(4)

        btn_in = QPushButton("+")
        btn_in.setFixedSize(28, 24)
        btn_in.setCursor(Qt.PointingHandCursor)
        btn_in.setToolTip("Entrada")
        btn_in.setStyleSheet(f"""
            QPushButton {{ background: {s.success_bg}; color: {s.success_text}; border: 1px solid {s.success}; border-radius: 6px; font-size: 12px; font-weight: bold; }}
            QPushButton:hover {{ background: {s.bg_hover}; }}
        """)
        btn_in.clicked.connect(lambda _, iid=item.id: self._on_entrada(iid))
        btn_layout.addWidget(btn_in)

        btn_out = QPushButton("-")
        btn_out.setFixedSize(28, 24)
        btn_out.setCursor(Qt.PointingHandCursor)
        btn_out.setToolTip("Saida")
        btn_out.setStyleSheet(f"""
            QPushButton {{ background: {s.error_bg}; color: {s.error_text}; border: 1px solid {s.border_error}; border-radius: 6px; font-size: 12px; font-weight: bold; }}
            QPushButton:hover {{ background: {s.bg_hover}; }}
        """)
        btn_out.clicked.connect(lambda _, iid=item.id: self._on_saida(iid))
        btn_layout.addWidget(btn_out)

        self.items_table.setCellWidget(row, 6, btn_widget)

    def _on_entrada(self, item_id: str):
        item = self._service.get_item(item_id)
        if not item:
            return
        from PySide6.QtWidgets import QInputDialog

        qtd, ok = QInputDialog.getInt(self, f"Entrada - {item.nome}", "Quantidade:", 1, 0, 9999)
        if ok and qtd > 0:
            self._service.entrada(item_id, qtd)
            self.refresh()
            self.entrada_solicitada.emit(item_id)

    def _on_saida(self, item_id: str):
        item = self._service.get_item(item_id)
        if not item:
            return
        from PySide6.QtWidgets import QInputDialog

        qtd, ok = QInputDialog.getInt(
            self, f"Saida - {item.nome}", "Quantidade:", 1, 0, item.quantidade
        )
        if ok and 0 < qtd <= item.quantidade:
            self._service.saida(item_id, qtd)
            self.refresh()
            self.saida_solicitada.emit(item_id)
        elif ok and qtd > item.quantidade:
            QMessageBox.warning(self, "Erro", "Quantidade maior que o estoque disponivel.")

    def _show_alertas(self):
        itens = self._service.itens_estoque_baixo()
        if not itens:
            QMessageBox.information(self, "Alertas", "Nenhum item com estoque baixo!")
            return
        texto = "Itens com estoque abaixo do minimo:\n\n"
        for item in itens:
            texto += f"  - {item.nome}: {item.quantidade}/{item.estoque_min} un.\n"
        QMessageBox.warning(self, f"Alertas ({len(itens)})", texto)

    def set_scheme(self, scheme):
        self._scheme = scheme
        if self._scheme:
            self._apply_static_styles()
            self.refresh()
