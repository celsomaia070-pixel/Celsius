"""
InventoryPanel - Painel lateral de estoque com design WMS profissional.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.inventory import ColunaKanban, ItemEstoque, Movimentacao, get_inventory_service
from ui.components.base import Card, IconButton, SearchInput, TextButton
from ui.theme.schemes import get_scheme
from ui.theme.tokens import SPACING, RADIUS, TYPOGRAPHY


def _stock_health_color(item: ItemEstoque) -> tuple[str, str]:
    """Retorna (bg, fg) para a badge de status."""
    cores = {
        ColunaKanban.CRITICO: ("#FFF0F0", "#C62828"),
        ColunaKanban.A_COMPRAR: ("#FFF8E1", "#E65100"),
        ColunaKanban.EM_ESTOQUE: ("#E8F5E9", "#1B5E20"),
        ColunaKanban.EM_USO: ("#E3F2FD", "#1565C0"),
    }
    return cores.get(item.coluna, ("#F5F5F5", "#757575"))


def _stock_bar_color(item: ItemEstoque) -> str:
    """Cor da barra de progresso baseada na saude do estoque."""
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
    """Item de historico de movimentacao com visual profissional."""

    def __init__(self, mov: Movimentacao, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or get_scheme()
        s = self._scheme
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2)
        layout.setSpacing(SPACING.space_2)

        tipo = mov.tipo
        sinal = "+" if tipo == "entrada" else "-"
        cor = "#1B5E20" if tipo == "entrada" else "#C62828"
        bg = "#E8F5E9" if tipo == "entrada" else "#FFF0F0"

        tag = QLabel(f" {sinal} ")
        tag.setFixedSize(22, 22)
        tag.setAlignment(Qt.AlignCenter)
        tag.setStyleSheet(
            f"background: {bg}; color: {cor}; border-radius: 11px; "
            f"font-size: {TYPOGRAPHY.text_xs}px; font-weight: bold; border: none;"
        )
        layout.addWidget(tag, 0, Qt.AlignCenter)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        item_name = QLabel(mov.item_nome)
        item_name.setStyleSheet(
            f"color: {s.text_primary}; font-size: {TYPOGRAPHY.text_sm}px; "
            f"font-weight: {TYPOGRAPHY.weight_semibold}; background: transparent; border: none;"
        )
        info_col.addWidget(item_name)

        qty_text = f"{sinal}{mov.quantidade} un"
        if mov.quantidade_anterior != mov.quantidade_nova:
            qty_text += f"  ({mov.quantidade_anterior} -> {mov.quantidade_nova})"
        qty_label = QLabel(qty_text)
        qty_label.setStyleSheet(
            f"color: {cor}; font-size: {TYPOGRAPHY.text_xs}px; "
            f"font-weight: {TYPOGRAPHY.weight_medium}; background: transparent; border: none;"
        )
        info_col.addWidget(qty_label)

        layout.addLayout(info_col, 1)

        timestamp = mov.timestamp.split(" ")[1] if " " in mov.timestamp else mov.timestamp
        date_label = QLabel(timestamp)
        date_label.setStyleSheet(
            f"color: {s.text_muted}; font-size: {TYPOGRAPHY.text_xs}px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(date_label, 0, Qt.AlignRight | Qt.AlignCenter)


class CategoryHeader(QWidget):
    """Header de categoria com indicator e contagem."""

    def __init__(self, categoria: str, count: int, scheme=None, parent=None):
        super().__init__(parent)
        s = scheme or get_scheme()
        self.setFixedHeight(34)
        self.setStyleSheet(f"background: {s.bg_secondary}; border: none; border-bottom: 1px solid {s.border_default};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING.space_4, 0, SPACING.space_4, 0)
        layout.setSpacing(SPACING.space_2)

        indicator = QLabel(">")
        indicator.setFixedSize(14, 14)
        indicator.setAlignment(Qt.AlignCenter)
        indicator.setStyleSheet(
            f"color: {s.accent_primary}; font-size: {TYPOGRAPHY.text_xs}px; "
            f"font-weight: bold; background: transparent; border: none;"
        )
        layout.addWidget(indicator)

        label = QLabel(categoria)
        label.setStyleSheet(
            f"color: {s.text_primary}; font-size: {TYPOGRAPHY.text_sm}px; "
            f"font-weight: {TYPOGRAPHY.weight_bold}; background: transparent; border: none;"
        )
        layout.addWidget(label)

        count_badge = QLabel(f" {count} ")
        count_badge.setStyleSheet(
            f"color: {s.text_muted}; font-size: {TYPOGRAPHY.text_xs}px; "
            f"background: {s.bg_primary}; border: 1px solid {s.border_default}; "
            f"border-radius: 8px; padding: 1px 6px; border: none;"
        )
        layout.addWidget(count_badge)
        layout.addStretch()


class StockHealthBar(QWidget):
    """Mini barra de saude do estoque."""

    def __init__(self, item: ItemEstoque, width: int = 80, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme or get_scheme()
        s = self._scheme
        self.setFixedSize(width, 16)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(0)

        bar_w = width - 30
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


class InventoryPanel(QWidget):
    """Painel lateral de gerenciamento de estoque com design WMS."""

    entrada_solicitada = Signal(str)
    saida_solicitada = Signal(str)
    item_selecionado = Signal(str)

    def __init__(self, scheme=None, parent=None):
        super().__init__(parent)
        self._scheme = scheme
        self._service = get_inventory_service()
        self._selected_item_id = None
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        s = self._scheme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(SPACING.space_4, 0, SPACING.space_4, 0)
        title = QLabel("Estoque")
        title.setStyleSheet(
            f"color: {s.text_primary}; "
            f"font-size: {TYPOGRAPHY.text_xl}px; font-weight: {TYPOGRAPHY.weight_bold}; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()

        btn_add = IconButton(icon_name="plus", tooltip="Adicionar item", size=30)
        btn_add.clicked.connect(self._show_add_form)
        header_layout.addWidget(btn_add)

        layout.addWidget(header)

        self.search_input = SearchInput(placeholder="Buscar itens...", icon_name="search")
        self.search_input.setContentsMargins(SPACING.space_3, SPACING.space_2, SPACING.space_3, SPACING.space_2)
        self.search_input.textChanged.connect(self._filter_items)
        layout.addWidget(self.search_input)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; }} "
            f"QTabBar::tab {{ background: transparent; border: none; "
            f"padding: 10px 20px; font-size: 13px; font-weight: 600; "
            f"color: {s.text_muted}; }} "
            f"QTabBar::tab:selected {{ color: {s.text_primary}; border-bottom: 2px solid {s.accent_primary}; }}"
        )

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(6)
        self.items_table.setHorizontalHeaderLabels(["Item", "Qtd", "Min", "Max", "Status", ""])
        self.items_table.horizontalHeader().setVisible(True)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setShowGrid(False)
        self.items_table.setFrameShape(QFrame.Shape.NoFrame)
        self.items_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.items_table.setSelectionMode(QTableWidget.NoSelection)
        self.items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.items_table.setAlternatingRowColors(False)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.items_table.setColumnWidth(5, 64)
        self.items_table.verticalHeader().setDefaultSectionSize(42)
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
                color: {s.text_muted}; font-size: {TYPOGRAPHY.text_xs}px;
                font-weight: {TYPOGRAPHY.weight_semibold};
                padding: 6px 8px; text-align: left;
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

        self._add_form = self._build_add_form()
        self._add_form.hide()
        layout.addWidget(self._add_form)

        self._stats_bar = QWidget()
        self._stats_bar.setFixedHeight(40)
        stats_layout = QHBoxLayout(self._stats_bar)
        stats_layout.setContentsMargins(SPACING.space_4, 0, SPACING.space_4, 0)
        self._stats_label = QLabel("0 itens")
        self._stats_label.setStyleSheet(
            f"color: {s.text_muted}; font-size: {TYPOGRAPHY.text_sm}px; "
            f"background: transparent; border: none;"
        )
        stats_layout.addWidget(self._stats_label)
        stats_layout.addStretch()
        alertas_btn = TextButton(text="Alertas", variant="danger")
        alertas_btn.setFixedHeight(26)
        alertas_btn.clicked.connect(self._show_alertas)
        stats_layout.addWidget(alertas_btn)
        layout.addWidget(self._stats_bar)

    def _build_add_form(self) -> QWidget:
        s = self._scheme
        form = Card()
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(SPACING.space_4, SPACING.space_4, SPACING.space_4, SPACING.space_4)
        form_layout.setSpacing(SPACING.space_3)

        form_title = QLabel("Novo Item")
        form_title.setStyleSheet(
            f"color: {s.text_primary}; "
            f"font-size: {TYPOGRAPHY.text_base}px; font-weight: {TYPOGRAPHY.weight_bold}; "
            f"background: transparent; border: none;"
        )
        form_layout.addWidget(form_title)

        self._input_nome = QLineEdit()
        self._input_nome.setPlaceholderText("Nome do item")
        self._input_nome.setFixedHeight(36)
        self._input_nome.setStyleSheet(
            f"QLineEdit {{ background: {s.bg_secondary}; border: 1px solid {s.border_default}; "
            f"border-radius: {RADIUS.radius_md}px; padding: 0 {SPACING.space_3}px; "
            f"font-size: {TYPOGRAPHY.text_base}px; color: {s.text_primary}; }}"
            f"QLineEdit:focus {{ border-color: {s.accent_primary}; }}"
        )
        form_layout.addWidget(self._input_nome)

        self._input_categoria = QLineEdit()
        self._input_categoria.setPlaceholderText("Categoria (ex: Alimentos, Limpeza)")
        self._input_categoria.setFixedHeight(36)
        self._input_categoria.setStyleSheet(self._input_nome.styleSheet())
        form_layout.addWidget(self._input_categoria)

        nums_row = QHBoxLayout()
        nums_row.setSpacing(8)

        for label_text, attr in [("Qtd:", "_input_qtd"), ("Min:", "_input_min"), ("Max:", "_input_max")]:
            col = QVBoxLayout()
            col.setSpacing(3)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {s.text_secondary}; font-size: {TYPOGRAPHY.text_sm}px; "
                f"background: transparent; border: none;"
            )
            col.addWidget(lbl)

            spin = QSpinBox()
            spin.setRange(0, 99999)
            spin.setFixedHeight(36)
            spin.setStyleSheet(
                f"QSpinBox {{ background: {s.bg_secondary}; border: 1px solid {s.border_default}; "
                f"border-radius: {RADIUS.radius_md}px; padding: 0 {SPACING.space_2}px; "
                f"font-size: {TYPOGRAPHY.text_base}px; color: {s.text_primary}; }}"
                f"QSpinBox:focus {{ border-color: {s.accent_primary}; }}"
            )
            setattr(self, attr, spin)
            col.addWidget(spin)
            nums_row.addLayout(col)

        form_layout.addLayout(nums_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACING.space_2)

        btn_cancel = TextButton(text="Cancelar", variant="default")
        btn_cancel.setFixedHeight(34)
        btn_cancel.clicked.connect(self._hide_add_form)
        btn_row.addWidget(btn_cancel)

        btn_save = TextButton(text="Salvar", variant="primary")
        btn_save.setFixedHeight(34)
        btn_save.clicked.connect(self._save_new_item)
        btn_row.addWidget(btn_save)

        form_layout.addLayout(btn_row)

        return form

    def _show_add_form(self):
        self._input_nome.clear()
        self._input_categoria.clear()
        self._input_qtd.setValue(0)
        self._input_min.setValue(0)
        self._input_max.setValue(100)
        self._add_form.show()

    def _hide_add_form(self):
        self._add_form.hide()

    def _save_new_item(self):
        nome = self._input_nome.text().strip()
        cat = self._input_categoria.text().strip()
        if not nome:
            QMessageBox.warning(self, "Erro", "Nome do item e obrigatorio.")
            return
        if not cat:
            cat = "Geral"
        self._service.adicionar_item(
            nome=nome,
            categoria=cat,
            quantidade=self._input_qtd.value(),
            estoque_min=self._input_min.value(),
            estoque_max=self._input_max.value(),
        )
        self._hide_add_form()
        self.refresh()

    def _filter_items(self, text: str):
        text_lower = text.lower()
        for row in range(self.items_table.rowCount()):
            item_widget = self.items_table.cellWidget(row, 0)
            if item_widget:
                nome_label = item_widget.findChild(QLabel)
                if nome_label:
                    visible = text_lower in nome_label.text().lower()
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
            self.items_table.setRowHeight(header_row, 34)
            self.items_table.setCellWidget(header_row, 0, header_widget)
            self.items_table.setSpan(header_row, 0, 1, 6)

            for item in cat_items:
                row = self.items_table.rowCount()
                self.items_table.insertRow(row)
                self.items_table.setRowHeight(row, 42)
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
        self._stats_label.setText(f"{total} itens" + (f" | {criticos} em alerta" if criticos else ""))

    def _populate_row(self, row: int, item: ItemEstoque):
        s = self._scheme
        bg, fg = _stock_health_color(item)

        # Col 0: Nome com dot de saude
        name_widget = QWidget()
        name_layout = QHBoxLayout(name_widget)
        name_layout.setContentsMargins(8, 0, 4, 0)
        name_layout.setSpacing(6)

        dot = QLabel()
        dot_color = _stock_bar_color(item)
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {dot_color}; border-radius: 4px; border: none;")
        name_layout.addWidget(dot, 0, Qt.AlignCenter)

        nome = QLabel(item.nome)
        nome.setStyleSheet(
            f"color: {s.text_primary}; font-size: {TYPOGRAPHY.text_sm}px; "
            f"font-weight: {TYPOGRAPHY.weight_semibold}; background: transparent; border: none;"
        )
        nome.setToolTip(item.nome)
        name_layout.addWidget(nome, 1)

        self.items_table.setCellWidget(row, 0, name_widget)

        # Col 1: Quantidade
        qtd_item = QTableWidgetItem(str(item.quantidade))
        qtd_item.setTextAlignment(Qt.AlignCenter)
        color = _stock_bar_color(item)
        qtd_item.setForeground(QColor(color))
        font = qtd_item.font()
        font.setBold(True)
        qtd_item.setFont(font)
        self.items_table.setItem(row, 1, qtd_item)

        # Col 2: Min
        min_item = QTableWidgetItem(str(item.estoque_min))
        min_item.setTextAlignment(Qt.AlignCenter)
        self.items_table.setItem(row, 2, min_item)

        # Col 3: Max
        max_item = QTableWidgetItem(str(item.estoque_max))
        max_item.setTextAlignment(Qt.AlignCenter)
        self.items_table.setItem(row, 3, max_item)

        # Col 4: Status badge
        status_label = QLabel(item.coluna.value.replace("_", " ").title())
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 8px; padding: 3px 10px; "
            f"font-size: {TYPOGRAPHY.text_xs}px; font-weight: {TYPOGRAPHY.weight_semibold}; border: none;"
        )
        self.items_table.setCellWidget(row, 4, status_label)

        # Col 5: Botoes +/- com visual profissional
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(2, 0, 2, 0)
        btn_layout.setSpacing(3)

        btn_in = QPushButton("+")
        btn_in.setFixedSize(26, 22)
        btn_in.setCursor(Qt.PointingHandCursor)
        btn_in.setToolTip("Entrada")
        btn_in.setStyleSheet(f"""
            QPushButton {{
                background: #E8F5E9; color: #1B5E20; border: 1px solid #C8E6C9;
                border-radius: 4px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #C8E6C9; }}
        """)
        btn_in.clicked.connect(lambda _, iid=item.id: self._on_entrada(iid))
        btn_layout.addWidget(btn_in)

        btn_out = QPushButton("-")
        btn_out.setFixedSize(26, 22)
        btn_out.setCursor(Qt.PointingHandCursor)
        btn_out.setToolTip("Saida")
        btn_out.setStyleSheet(f"""
            QPushButton {{
                background: #FFF0F0; color: #C62828; border: 1px solid #FFCDD2;
                border-radius: 4px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #FFCDD2; }}
        """)
        btn_out.clicked.connect(lambda _, iid=item.id: self._on_saida(iid))
        btn_layout.addWidget(btn_out)

        self.items_table.setCellWidget(row, 5, btn_widget)

    def _on_entrada(self, item_id: str):
        item = self._service.get_item(item_id)
        if not item:
            return
        qtd, ok = self._get_quantity(f"Entrada - {item.nome}", "Quantidade a entrar:")
        if ok and qtd > 0:
            self._service.entrada(item_id, qtd)
            self.refresh()
            self.entrada_solicitada.emit(item_id)

    def _on_saida(self, item_id: str):
        item = self._service.get_item(item_id)
        if not item:
            return
        qtd, ok = self._get_quantity(f"Saida - {item.nome}", "Quantidade a saida:")
        if ok and 0 < qtd <= item.quantidade:
            self._service.saida(item_id, qtd)
            self.refresh()
            self.saida_solicitada.emit(item_id)
        elif ok and qtd > item.quantidade:
            QMessageBox.warning(self, "Erro", "Quantidade maior que o estoque disponivel.")

    def _get_quantity(self, title: str, label: str):
        from PySide6.QtWidgets import QInputDialog
        qtd, ok = QInputDialog.getInt(self, title, label, 1, 0, 9999)
        return qtd, ok

    def _show_alertas(self):
        itens = self._service.itens_estoque_baixo()
        if not itens:
            QMessageBox.information(self, "Alertas", "Nenhum item com estoque baixo.")
            return
        texto = "Itens com estoque abaixo do minimo:\n\n"
        for item in itens:
            texto += f"  - {item.nome}: {item.quantidade}/{item.estoque_min} un.\n"
        QMessageBox.warning(self, f"Alertas ({len(itens)})", texto)

    def set_scheme(self, scheme):
        self._scheme = scheme
        s = scheme
        if s:
            self.setStyleSheet(f"background: {s.bg_primary};")
            header = self.findChild(QWidget)
            if header:
                header.setStyleSheet(f"background: {s.bg_primary}; border-bottom: 1px solid {s.border_default};")
            if hasattr(self, 'search_input') and hasattr(self.search_input, 'set_scheme'):
                self.search_input.set_scheme(s)
            self.tabs.setStyleSheet(
                f"QTabWidget::pane {{ border: none; }} "
                f"QTabBar::tab {{ background: transparent; border: none; "
                f"padding: 10px 20px; font-size: 13px; font-weight: 600; "
                f"color: {s.text_muted}; }} "
                f"QTabBar::tab:selected {{ color: {s.text_primary}; border-bottom: 2px solid {s.accent_primary}; }}"
            )
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
                    color: {s.text_muted}; font-size: {TYPOGRAPHY.text_xs}px;
                    font-weight: {TYPOGRAPHY.weight_semibold};
                    padding: 6px 8px; text-align: left;
                    border-bottom: 1px solid {s.border_default};
                }}
            """)
            self.refresh()
