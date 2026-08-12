import io

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.business_records import BusinessRecordService, get_business_record_service
from core.memory import get_memory_service
from core.mobile_access import ensure_mobile_token
from core.module_schema import module_fields, module_primary_field, module_summary
from core.modules import get_module_definition, module_catalog, suggest_modules_for_company
from core.settings import Settings, get_settings
from core.suppliers import SupplierService, get_supplier_service
from core.tts import available_tts_profiles, resolve_tts_profile
from ui.theme.schemes import ColorScheme, get_scheme


class CaixaMemoriaDialog(QDialog):
    def __init__(self, memory_service=None, parent=None, scheme: ColorScheme | None = None):
        super().__init__(parent)
        self.memory_service = memory_service or get_memory_service()
        self._scheme = scheme or get_scheme()
        self.setWindowTitle("Adicionar MemÃ³ria")
        self.setFixedSize(450, 160)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            QDialog {{ background-color: {s.bg_secondary}; border: 1px solid {s.border_default}; border-radius: 8px; }}
            QLabel {{ color: {s.text_primary}; font-size: 14px; font-weight: 500; }}
            QLineEdit {{ background-color: {s.bg_primary}; border: 1px solid {s.border_default}; border-radius: 6px; color: {s.text_primary}; padding: 8px; font-size: 14px; }}
            QLineEdit:focus {{ border-color: {s.accent_primary}; }}
            QPushButton {{ background-color: {s.bg_tertiary}; color: {s.text_primary}; border: none; border-radius: 6px; font-weight: bold; min-width: 80px; padding: 6px 14px; }}
            QPushButton:hover {{ background-color: {s.bg_hover}; }}
            QPushButton#btn_salvar {{ background-color: {s.success}; color: {s.text_on_accent}; }}
            QPushButton#btn_salvar:hover {{ background-color: {s.success_text}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.label = QLabel("Escreva um fato importante para o Celsius lembrar:")
        self.input_texto = QLineEdit()
        self.input_texto.setPlaceholderText("Digite aqui...")

        layout_botoes = QHBoxLayout()
        self.btn_salvar = QPushButton("Salvar", objectName="btn_salvar")
        self.btn_cancelar = QPushButton("Cancelar")

        layout_botoes.addStretch()
        layout_botoes.addWidget(self.btn_cancelar)
        layout_botoes.addWidget(self.btn_salvar)

        layout.addWidget(self.label)
        layout.addWidget(self.input_texto)
        layout.addLayout(layout_botoes)

        self.btn_salvar.clicked.connect(self._salvar)
        self.btn_cancelar.clicked.connect(self.reject)

    def _salvar(self):
        texto = self.input_texto.text().strip()
        if texto:
            self.memory_service.add(texto)
        self.accept()

    def obter_texto(self):
        return self.input_texto.text().strip()


class FormatoRelatorioDialog(QDialog):
    def __init__(self, parent=None, scheme: ColorScheme | None = None):
        super().__init__(parent)
        self._scheme = scheme or get_scheme()
        self.setWindowTitle("Formato do Relatorio")
        self.setFixedSize(300, 120)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._formato = "pdf"
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            QDialog {{ background-color: {s.bg_secondary}; border: 1px solid {s.border_default}; border-radius: 8px; }}
            QLabel {{ color: {s.text_primary}; font-size: 14px; font-weight: 500; }}
            QPushButton {{ background-color: {s.bg_tertiary}; color: {s.text_primary}; border: none; border-radius: 6px; font-weight: bold; min-width: 100px; padding: 8px 16px; }}
            QPushButton:hover {{ background-color: {s.bg_hover}; }}
            QPushButton#btn_pdf {{ background-color: {s.error}; color: {s.text_on_accent}; }}
            QPushButton#btn_pdf:hover {{ background-color: {s.error_text}; }}
            QPushButton#btn_docx {{ background-color: {s.info}; color: {s.text_on_accent}; }}
            QPushButton#btn_docx:hover {{ background-color: {s.info_text}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)

        label = QLabel("Escolha o formato:")
        layout.addWidget(label)

        layout_botoes = QHBoxLayout()
        layout_botoes.setSpacing(10)

        self.btn_pdf = QPushButton("PDF", objectName="btn_pdf")
        self.btn_docx = QPushButton("DOCX", objectName="btn_docx")

        self.btn_pdf.clicked.connect(self._selecionar_pdf)
        self.btn_docx.clicked.connect(self._selecionar_docx)

        layout_botoes.addStretch()
        layout_botoes.addWidget(self.btn_pdf)
        layout_botoes.addWidget(self.btn_docx)
        layout_botoes.addStretch()

        layout.addLayout(layout_botoes)

    def _selecionar_pdf(self):
        self._formato = "pdf"
        self.accept()

    def _selecionar_docx(self):
        self._formato = "docx"
        self.accept()

    def obter_formato(self):
        return self._formato


class FornecedoresDialog(QDialog):
    """Cadastro local de fornecedores."""

    def __init__(
        self,
        supplier_service: SupplierService | None = None,
        parent=None,
        scheme: ColorScheme | None = None,
    ):
        super().__init__(parent)
        self.supplier_service = supplier_service or get_supplier_service()
        self._scheme = scheme or get_scheme()
        self._supplier_ids: list[str] = []
        self.setWindowTitle("Fornecedores")
        self.setMinimumSize(760, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui()
        self._refresh_list()
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        self.title = QLabel("Cadastro de fornecedores")
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        self.subtitle = QLabel("Mantenha os contatos principais para compras, estoque e reposicao.")
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("subtitle")
        layout.addWidget(self.subtitle)

        content = QHBoxLayout()
        content.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Buscar fornecedor...")
        self.list_suppliers = QListWidget()
        self.list_suppliers.setMinimumWidth(260)
        left.addWidget(self.input_search)
        left.addWidget(self.list_suppliers, 1)
        content.addLayout(left, 1)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.input_nome = QLineEdit()
        self.input_contato = QLineEdit()
        self.input_telefone = QLineEdit()
        self.input_email = QLineEdit()
        self.input_categoria = QLineEdit()
        self.input_documento = QLineEdit()
        self.input_produtos = QLineEdit()
        self.input_prazo_pagamento = QLineEdit()
        self.input_lead_time = QLineEdit()
        self.combo_status = QComboBox()
        self.combo_status.setEditable(True)
        self.combo_status.addItems(["Ativo", "Preferencial", "Cotacao", "Inativo"])
        self.input_observacoes = QTextEdit()
        self.input_observacoes.setMinimumHeight(120)
        self.input_observacoes.setPlaceholderText(
            "Condicoes comerciais, prazo medio, produtos fornecidos..."
        )

        form.addRow("Nome:", self.input_nome)
        form.addRow("Contato:", self.input_contato)
        form.addRow("Telefone:", self.input_telefone)
        form.addRow("E-mail:", self.input_email)
        form.addRow("Categoria:", self.input_categoria)
        form.addRow("CNPJ/Documento:", self.input_documento)
        form.addRow("Produtos:", self.input_produtos)
        form.addRow("Prazo pagto.:", self.input_prazo_pagamento)
        form.addRow("Entrega dias:", self.input_lead_time)
        form.addRow("Status:", self.combo_status)
        form.addRow("Observacoes:", self.input_observacoes)
        content.addLayout(form, 2)

        layout.addLayout(content, 1)

        button_row = QHBoxLayout()
        self.btn_new = QPushButton("Novo")
        self.btn_delete = QPushButton("Excluir")
        self.btn_delete.setObjectName("btn_excluir")
        button_row.addWidget(self.btn_new)
        button_row.addWidget(self.btn_delete)
        button_row.addStretch()
        self.btn_close = QPushButton("Fechar")
        self.btn_save = QPushButton("Salvar")
        self.btn_save.setObjectName("btn_salvar")
        button_row.addWidget(self.btn_close)
        button_row.addWidget(self.btn_save)
        layout.addLayout(button_row)

        self.input_search.textChanged.connect(self._refresh_list)
        self.list_suppliers.itemSelectionChanged.connect(self._load_selected)
        self.btn_new.clicked.connect(self._clear_form)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_close.clicked.connect(self.accept)
        self.btn_save.clicked.connect(self._save_supplier)

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {s.bg_primary};
                color: {s.text_primary};
            }}
            QLabel {{
                color: {s.text_primary};
                font-size: 13px;
                background: transparent;
            }}
            QLabel#title {{
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#subtitle {{
                color: {s.text_secondary};
            }}
            QLineEdit, QTextEdit, QListWidget, QComboBox {{
                background-color: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: 6px;
                color: {s.text_primary};
                padding: 8px;
                font-size: 13px;
                selection-background-color: {s.accent_primary}40;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border-color: {s.accent_primary};
            }}
            QListWidget::item {{
                border-radius: 6px;
                padding: 8px;
                margin: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {s.bg_hover};
            }}
            QListWidget::item:selected {{
                background-color: {s.bg_active};
            }}
            QPushButton {{
                background-color: {s.bg_tertiary};
                color: {s.text_primary};
                border: 1px solid {s.border_default};
                border-radius: 6px;
                font-weight: 600;
                min-width: 90px;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                background-color: {s.bg_hover};
            }}
            QPushButton#btn_salvar {{
                background-color: {s.accent_primary};
                color: {s.text_on_accent};
                border-color: {s.accent_primary};
            }}
            QPushButton#btn_salvar:hover {{
                background-color: {s.accent_hover};
            }}
            QPushButton#btn_excluir {{
                color: {s.error_text};
                border-color: {s.error_text};
            }}
        """)

    def _current_supplier_id(self) -> str | None:
        current = self.list_suppliers.currentItem()
        if current is None:
            return None
        return current.data(Qt.UserRole)

    def _refresh_list(self, *_args, select_id: str | None = None):
        selected_id = select_id or self._current_supplier_id()
        self.list_suppliers.blockSignals(True)
        self.list_suppliers.clear()
        self._supplier_ids = []

        suppliers = self.supplier_service.search(self.input_search.text())
        for supplier in suppliers:
            item = QListWidgetItem()
            detail_parts = [
                value for value in (supplier.status, supplier.categoria, supplier.contato) if value
            ]
            details = " | ".join(detail_parts[:2]) or supplier.telefone or "Sem categoria"
            item.setText(f"{supplier.nome}\n{details}")
            item.setData(Qt.UserRole, supplier.id)
            self.list_suppliers.addItem(item)
            self._supplier_ids.append(supplier.id)
            if supplier.id == selected_id:
                self.list_suppliers.setCurrentItem(item)

        self.list_suppliers.blockSignals(False)
        if self.list_suppliers.currentItem() is None:
            self._clear_form()

    def _load_selected(self):
        supplier_id = self._current_supplier_id()
        supplier = self.supplier_service.get(supplier_id) if supplier_id else None
        if supplier is None:
            return

        self.input_nome.setText(supplier.nome)
        self.input_contato.setText(supplier.contato)
        self.input_telefone.setText(supplier.telefone)
        self.input_email.setText(supplier.email)
        self.input_categoria.setText(supplier.categoria)
        self.input_documento.setText(supplier.documento)
        self.input_produtos.setText(supplier.produtos)
        self.input_prazo_pagamento.setText(supplier.prazo_pagamento)
        self.input_lead_time.setText(supplier.lead_time_dias)
        status_index = self.combo_status.findText(supplier.status)
        if status_index >= 0:
            self.combo_status.setCurrentIndex(status_index)
        else:
            self.combo_status.setEditText(supplier.status)
        self.input_observacoes.setPlainText(supplier.observacoes)

    def _clear_form(self):
        self.list_suppliers.clearSelection()
        self.input_nome.clear()
        self.input_contato.clear()
        self.input_telefone.clear()
        self.input_email.clear()
        self.input_categoria.clear()
        self.input_documento.clear()
        self.input_produtos.clear()
        self.input_prazo_pagamento.clear()
        self.input_lead_time.clear()
        self.combo_status.setCurrentIndex(0)
        self.input_observacoes.clear()
        self.input_nome.setFocus()

    def _save_supplier(self):
        nome = self.input_nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Fornecedor", "Informe o nome do fornecedor.")
            return

        payload = {
            "nome": nome,
            "contato": self.input_contato.text(),
            "telefone": self.input_telefone.text(),
            "email": self.input_email.text(),
            "categoria": self.input_categoria.text(),
            "documento": self.input_documento.text(),
            "produtos": self.input_produtos.text(),
            "prazo_pagamento": self.input_prazo_pagamento.text(),
            "lead_time_dias": self.input_lead_time.text(),
            "status": self.combo_status.currentText(),
            "observacoes": self.input_observacoes.toPlainText(),
        }
        supplier_id = self._current_supplier_id()
        if supplier_id:
            supplier = self.supplier_service.update(supplier_id, **payload)
        else:
            supplier = self.supplier_service.add(**payload)

        if supplier is not None:
            self._refresh_list(select_id=supplier.id)

    def _delete_selected(self):
        supplier_id = self._current_supplier_id()
        if not supplier_id:
            return
        self.supplier_service.delete(supplier_id)
        self._refresh_list()


class ModuloRegistrosDialog(QDialog):
    """Generic local registry for ready business modules."""

    def __init__(
        self,
        module_id: str,
        record_service: BusinessRecordService | None = None,
        parent=None,
        scheme: ColorScheme | None = None,
    ):
        super().__init__(parent)
        self.module = get_module_definition(module_id)
        if self.module is None:
            raise ValueError(f"Modulo desconhecido: {module_id}")
        self.record_service = record_service or get_business_record_service()
        self._scheme = scheme or get_scheme()
        self.inputs: dict[str, QLineEdit | QTextEdit | QComboBox] = {}
        self.setWindowTitle(self.module.name)
        self.setMinimumSize(720, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui()
        self._refresh_list()
        self._apply_theme()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        self.title = QLabel(self.module.name)
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        self.subtitle = QLabel(self.module.description)
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("subtitle")
        layout.addWidget(self.subtitle)

        content = QHBoxLayout()
        content.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Buscar...")
        self.list_records = QListWidget()
        self.list_records.setMinimumWidth(260)
        left.addWidget(self.input_search)
        left.addWidget(self.list_records, 1)
        content.addLayout(left, 1)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        for field in module_fields(self.module.id):
            if field.kind == "textarea":
                input_widget = QTextEdit()
                input_widget.setMaximumHeight(110)
                if field.placeholder:
                    input_widget.setPlaceholderText(field.placeholder)
            elif field.kind == "select":
                input_widget = QComboBox()
                input_widget.setEditable(True)
                input_widget.addItems(field.options)
            else:
                input_widget = QLineEdit()
                if field.placeholder:
                    input_widget.setPlaceholderText(field.placeholder)
            self.inputs[field.key] = input_widget
            required_marker = " *" if field.required else ""
            form.addRow(f"{field.label}{required_marker}:", input_widget)
        content.addLayout(form, 2)
        layout.addLayout(content, 1)

        self.privacy_hint = QLabel(
            "Dados salvos localmente. Para areas sensiveis, a arquitetura esta preparada para auditoria, permissoes e separacao por empresa em proximas etapas."
        )
        self.privacy_hint.setWordWrap(True)
        self.privacy_hint.setObjectName("hint")
        layout.addWidget(self.privacy_hint)

        button_row = QHBoxLayout()
        self.btn_new = QPushButton("Novo")
        self.btn_delete = QPushButton("Excluir")
        self.btn_delete.setObjectName("btn_excluir")
        button_row.addWidget(self.btn_new)
        button_row.addWidget(self.btn_delete)
        button_row.addStretch()
        self.btn_close = QPushButton("Fechar")
        self.btn_save = QPushButton("Salvar")
        self.btn_save.setObjectName("btn_salvar")
        button_row.addWidget(self.btn_close)
        button_row.addWidget(self.btn_save)
        layout.addLayout(button_row)

        self.input_search.textChanged.connect(self._refresh_list)
        self.list_records.itemSelectionChanged.connect(self._load_selected)
        self.btn_new.clicked.connect(self._clear_form)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_close.clicked.connect(self.accept)
        self.btn_save.clicked.connect(self._save_record)

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {s.bg_primary};
                color: {s.text_primary};
            }}
            QLabel {{
                color: {s.text_primary};
                font-size: 13px;
                background: transparent;
            }}
            QLabel#title {{
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#subtitle, QLabel#hint {{
                color: {s.text_secondary};
            }}
            QLineEdit, QTextEdit, QListWidget, QComboBox {{
                background-color: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: 6px;
                color: {s.text_primary};
                padding: 8px;
                font-size: 13px;
            }}
            QListWidget::item {{
                border-radius: 6px;
                padding: 8px;
                margin: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {s.bg_hover};
            }}
            QListWidget::item:selected {{
                background-color: {s.bg_active};
            }}
            QPushButton {{
                background-color: {s.bg_tertiary};
                color: {s.text_primary};
                border: 1px solid {s.border_default};
                border-radius: 6px;
                font-weight: 600;
                min-width: 90px;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                background-color: {s.bg_hover};
            }}
            QPushButton#btn_salvar {{
                background-color: {s.accent_primary};
                color: {s.text_on_accent};
                border-color: {s.accent_primary};
            }}
            QPushButton#btn_excluir {{
                color: {s.error_text};
                border-color: {s.error_text};
            }}
        """)

    def _current_record_id(self) -> str | None:
        current = self.list_records.currentItem()
        if current is None:
            return None
        return current.data(Qt.UserRole)

    def _refresh_list(self, *_args, select_id: str | None = None):
        selected_id = select_id or self._current_record_id()
        self.list_records.blockSignals(True)
        self.list_records.clear()
        for record in self.record_service.search(self.module.id, self.input_search.text()):
            item = QListWidgetItem()
            detail = module_summary(record.fields, self.module.id)
            item.setText(f"{record.title}\n{detail}")
            item.setData(Qt.UserRole, record.id)
            self.list_records.addItem(item)
            if record.id == selected_id:
                self.list_records.setCurrentItem(item)
        self.list_records.blockSignals(False)
        if self.list_records.currentItem() is None:
            self._clear_form()

    def _load_selected(self):
        record_id = self._current_record_id()
        record = self.record_service.get(record_id) if record_id else None
        if record is None:
            return
        for key, widget in self.inputs.items():
            value = record.fields.get(key, "")
            if isinstance(widget, QTextEdit):
                widget.setPlainText(value)
            elif isinstance(widget, QComboBox):
                index = widget.findText(value)
                if index >= 0:
                    widget.setCurrentIndex(index)
                else:
                    widget.setEditText(value)
            else:
                widget.setText(value)

    def _clear_form(self):
        self.list_records.clearSelection()
        for widget in self.inputs.values():
            if isinstance(widget, QTextEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                if widget.count():
                    widget.setCurrentIndex(0)
                elif widget.isEditable():
                    widget.setEditText("")
            else:
                widget.clear()
        first = next(iter(self.inputs.values()), None)
        if first:
            first.setFocus()

    def _save_record(self):
        fields = {}
        for key, widget in self.inputs.items():
            if isinstance(widget, QTextEdit):
                fields[key] = widget.toPlainText()
            elif isinstance(widget, QComboBox):
                fields[key] = widget.currentText()
            else:
                fields[key] = widget.text()

        title = fields.get(module_primary_field(self.module.id), "")
        if not title.strip():
            QMessageBox.warning(self, self.module.name, "Preencha o campo principal.")
            return

        record = self.record_service.save_record(
            self.module.id,
            title=title,
            fields=fields,
            record_id=self._current_record_id() or "",
        )
        self._refresh_list(select_id=record.id)

    def _delete_selected(self):
        record_id = self._current_record_id()
        if not record_id:
            return
        self.record_service.delete(record_id)
        self._refresh_list()


class AssistentePrimeiraConfiguracaoDialog(QDialog):
    """Guided first setup for company profile and modules."""

    SEGMENTOS = (
        "Oficina mecanica",
        "Autopecas",
        "Comercio",
        "Padaria",
        "Escritorio de advocacia",
        "Dentista",
        "Clinica ou consultorio",
        "Prestador de servicos",
        "Outro",
    )

    def __init__(
        self,
        settings: Settings | None = None,
        parent=None,
        scheme: ColorScheme | None = None,
    ):
        super().__init__(parent)
        self.settings = settings or get_settings()
        self._scheme = scheme or get_scheme()
        self.module_checks: dict[str, QCheckBox] = {}
        self.setWindowTitle("Primeira configuracao do Celsius")
        self.setMinimumSize(720, 620)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui()
        self._apply_theme()
        self._apply_suggestions()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        self.title = QLabel("Configurar empresa")
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        self.subtitle = QLabel(
            "Escolha uma base inicial. Depois voce pode mudar tudo em Configuracoes."
        )
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("subtitle")
        layout.addWidget(self.subtitle)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.input_company_name = QLineEdit()
        self.combo_segment = QComboBox()
        self.combo_segment.addItems(self.SEGMENTOS)
        self.input_description = QTextEdit()
        self.input_description.setMaximumHeight(70)
        self.input_needs = QTextEdit()
        self.input_needs.setMaximumHeight(80)
        self.input_needs.setPlaceholderText(
            "Ex: estoque, fornecedores, clientes, agenda, documentos, financeiro..."
        )

        form.addRow("Empresa:", self.input_company_name)
        form.addRow("Segmento:", self.combo_segment)
        form.addRow("Descricao:", self.input_description)
        form.addRow("Areas:", self.input_needs)
        layout.addLayout(form)

        self.modules_title = QLabel("Modulos sugeridos")
        self.modules_title.setObjectName("section_title")
        layout.addWidget(self.modules_title)

        modules_grid = QGridLayout()
        modules_grid.setHorizontalSpacing(18)
        modules_grid.setVerticalSpacing(8)
        for module in module_catalog():
            label = module.name if module.is_ready else f"{module.name} (em preparacao)"
            check = QCheckBox(label)
            check.setToolTip(module.description)
            check.setEnabled(not module.mandatory)
            self.module_checks[module.id] = check
            index = len(self.module_checks) - 1
            modules_grid.addWidget(check, index // 2, index % 2)
        layout.addLayout(modules_grid)

        self.review_label = QLabel("")
        self.review_label.setWordWrap(True)
        self.review_label.setObjectName("hint")
        layout.addWidget(self.review_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.btn_cancel = QPushButton("Agora nao")
        self.btn_finish = QPushButton("Concluir")
        self.btn_finish.setObjectName("btn_salvar")
        button_row.addWidget(self.btn_cancel)
        button_row.addWidget(self.btn_finish)
        layout.addLayout(button_row)

        self.combo_segment.currentTextChanged.connect(self._apply_suggestions)
        self.input_needs.textChanged.connect(self._apply_suggestions)
        for check in self.module_checks.values():
            check.stateChanged.connect(self._update_review)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_finish.clicked.connect(self._finish)

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {s.bg_primary};
                color: {s.text_primary};
            }}
            QLabel {{
                color: {s.text_primary};
                font-size: 13px;
                background: transparent;
            }}
            QLabel#title {{
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#section_title {{
                font-size: 15px;
                font-weight: 700;
                margin-top: 8px;
            }}
            QLabel#subtitle, QLabel#hint {{
                color: {s.text_secondary};
            }}
            QLineEdit, QTextEdit, QComboBox {{
                background-color: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: 6px;
                color: {s.text_primary};
                padding: 8px;
                font-size: 13px;
            }}
            QCheckBox {{
                color: {s.text_primary};
                spacing: 8px;
                background: transparent;
            }}
            QPushButton {{
                background-color: {s.bg_tertiary};
                color: {s.text_primary};
                border: 1px solid {s.border_default};
                border-radius: 6px;
                font-weight: 600;
                min-width: 90px;
                padding: 8px 14px;
            }}
            QPushButton#btn_salvar {{
                background-color: {s.accent_primary};
                color: {s.text_on_accent};
                border-color: {s.accent_primary};
            }}
        """)

    def _apply_suggestions(self):
        suggested = set(
            suggest_modules_for_company(
                self.combo_segment.currentText(),
                self.input_needs.toPlainText(),
            )
        )
        for module_id, check in self.module_checks.items():
            check.blockSignals(True)
            if check.isEnabled():
                check.setChecked(module_id in suggested)
            else:
                check.setChecked(True)
            check.blockSignals(False)
        self._update_review()

    def _selected_modules(self) -> list[str]:
        return [
            module_id
            for module_id, check in self.module_checks.items()
            if check.isChecked() or not check.isEnabled()
        ]

    def _update_review(self):
        selected_names = [
            module.name for module in module_catalog() if module.id in set(self._selected_modules())
        ]
        self.review_label.setText("Selecionados: " + ", ".join(selected_names))

    def _finish(self):
        customer = self.settings.customer
        customer.company_name = self.input_company_name.text().strip()
        customer.company_sector = self.combo_segment.currentText().strip()
        customer.company_description = self.input_description.toPlainText().strip()
        customer.main_needs = self.input_needs.toPlainText().strip()
        if customer.company_sector.lower() in {
            "escritorio de advocacia",
            "dentista",
            "clinica ou consultorio",
        }:
            customer.local_offline_required = True
        self.settings.modules.set_enabled(self._selected_modules())
        self.settings.modules.first_setup_completed = True
        self.settings.save_customer_profile()
        self.accept()


class PareamentoCelularDialog(QDialog):
    """Mostra QR Code e link de pareamento para o celular."""

    def __init__(
        self,
        url: str,
        *,
        https_enabled: bool,
        scheme: ColorScheme | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.https_enabled = https_enabled
        self._scheme = scheme or get_scheme()
        self.setWindowTitle("Parear celular")
        self.setMinimumSize(460, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        self.title = QLabel("Parear celular")
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        self.subtitle = QLabel(
            "Aponte a camera do celular para o QR Code ou abra o link abaixo no navegador."
        )
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("subtitle")
        layout.addWidget(self.subtitle)

        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumHeight(280)
        pixmap = self._build_qr_pixmap(self.url)
        if pixmap is None:
            self.qr_label.setText(
                "QR Code indisponivel.\nInstale a dependencia qrcode ou use o link abaixo."
            )
        else:
            self.qr_label.setPixmap(pixmap.scaled(280, 280, Qt.KeepAspectRatio))
        layout.addWidget(self.qr_label)

        self.url_input = QLineEdit(self.url)
        self.url_input.setReadOnly(True)
        layout.addWidget(self.url_input)

        warning = (
            "Como o certificado e local, o celular pode pedir confirmacao de seguranca "
            "na primeira abertura. Isso e esperado no pareamento local."
            if self.https_enabled
            else "HTTPS esta desligado; alguns navegadores podem bloquear o microfone."
        )
        self.warning = QLabel(warning)
        self.warning.setWordWrap(True)
        self.warning.setObjectName("hint")
        layout.addWidget(self.warning)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.btn_close = QPushButton("Fechar")
        self.btn_close.clicked.connect(self.accept)
        button_row.addWidget(self.btn_close)
        layout.addLayout(button_row)

    def _build_qr_pixmap(self, url: str) -> QPixmap | None:
        try:
            import qrcode
        except ImportError:
            return None

        image = qrcode.make(url)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        pixmap = QPixmap()
        if not pixmap.loadFromData(buffer.getvalue(), "PNG"):
            return None
        return pixmap

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {s.bg_primary};
                color: {s.text_primary};
            }}
            QLabel {{
                color: {s.text_primary};
                font-size: 13px;
                background: transparent;
            }}
            QLabel#title {{
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#subtitle, QLabel#hint {{
                color: {s.text_secondary};
            }}
            QLabel#hint {{
                padding-top: 4px;
            }}
            QLineEdit {{
                background-color: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: 6px;
                color: {s.text_primary};
                padding: 8px;
                font-size: 13px;
                selection-background-color: {s.accent_primary}40;
            }}
            QPushButton {{
                background-color: {s.accent_primary};
                color: {s.text_on_accent};
                border: 1px solid {s.accent_primary};
                border-radius: 6px;
                font-weight: 600;
                min-width: 90px;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                background-color: {s.accent_hover};
            }}
        """)


class ConfiguracoesDialog(QDialog):
    """Dialog for customer/company profile settings."""

    def __init__(
        self,
        settings: Settings | None = None,
        parent=None,
        scheme: ColorScheme | None = None,
    ):
        super().__init__(parent)
        self.settings = settings or get_settings()
        self._scheme = scheme or get_scheme()
        self.mobile_action: str | None = None
        self.setWindowTitle("Configuracoes do Celsius")
        self.setMinimumSize(620, 560)
        self.resize(700, 640)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui()
        self._load_values()
        self._apply_theme()

    def set_scheme(self, scheme: ColorScheme):
        self._scheme = scheme
        self._apply_theme()

    def _setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(18, 16, 18, 16)
        outer_layout.setSpacing(12)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_content = QWidget()
        layout = QVBoxLayout(self.scroll_content)
        layout.setContentsMargins(6, 6, 12, 6)
        layout.setSpacing(14)

        self.title = QLabel("Perfil do cliente/empresa")
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        self.subtitle = QLabel(
            "Essas informacoes ajudam o Celsius a entender para quem esta trabalhando."
        )
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("subtitle")
        layout.addWidget(self.subtitle)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.input_user_name = QLineEdit()
        self.input_company_name = QLineEdit()
        self.input_company_sector = QLineEdit()
        self.input_company_size = QLineEdit()
        self.input_company_description = QTextEdit()
        self.input_company_description.setMaximumHeight(58)
        self.input_user_role = QLineEdit()
        self.input_preferred_tone = QLineEdit()
        self.input_timezone = QLineEdit()
        self.combo_response_mode = QComboBox()
        self.combo_response_mode.addItems(["natural", "tecnico", "relatorio"])
        self.combo_response_detail = QComboBox()
        self.combo_response_detail.addItems(["conciso", "equilibrado", "detalhado"])
        self.input_response_temperature = QLineEdit()
        self.input_response_top_p = QLineEdit()
        self.check_voice_enabled = QCheckBox(
            "Ativar saida por voz quando o modo voz estiver ligado"
        )
        self.combo_voice_profile = QComboBox()
        self._voice_profiles = available_tts_profiles("edge-tts")
        for profile in self._voice_profiles:
            label = f"{profile.name} - {profile.description}"
            self.combo_voice_profile.addItem(label, profile.id)
        self.combo_voice = QComboBox()
        self.combo_voice.addItems(
            [
                "pt-BR-AntonioNeural",
                "pt-BR-FranciscaNeural",
                "pt-BR-BrendaNeural",
                "pt-BR-DonatoNeural",
            ]
        )
        self.input_voice_rate = QLineEdit()
        self.input_voice_pitch = QLineEdit()
        self.input_voice_volume = QLineEdit()
        self.combo_voice_profile.currentIndexChanged.connect(self._apply_selected_voice_profile)
        self.check_mobile_enabled = QCheckBox("Ativar acesso local pelo celular")
        self.check_mobile_lan = QCheckBox("Permitir acesso pela mesma rede Wi-Fi")
        self.check_mobile_voice = QCheckBox("Permitir comandos de voz pelo celular")
        self.check_mobile_https = QCheckBox("Usar HTTPS local para melhorar suporte ao microfone")
        self.input_mobile_port = QLineEdit()
        self.input_mobile_token = QLineEdit()
        self.check_notifications_enabled = QCheckBox("Ativar Canais e Notificacoes")
        self.check_notifications_external = QCheckBox(
            "Permitir envio por internet e servico externo"
        )
        self.check_notifications_confirmation = QCheckBox(
            "Exigir confirmacao antes de enviar mensagens"
        )
        self.combo_notification_channel = QComboBox()
        self.combo_notification_channel.addItems(["whatsapp", "email", "sms"])
        self.input_whatsapp_provider = QLineEdit()
        self.input_whatsapp_phone_id = QLineEdit()
        self.input_whatsapp_token_env = QLineEdit()
        self.input_email_provider = QLineEdit()
        self.input_email_from = QLineEdit()
        self.input_sms_provider = QLineEdit()
        self.input_sms_sender = QLineEdit()
        self.input_business_context = QTextEdit()
        self.input_business_context.setMaximumHeight(82)
        self.input_business_context.setPlaceholderText(
            "Ex: estoque minimo padrao, principais fornecedores, tipo de venda, prioridades financeiras..."
        )
        self.input_main_needs = QTextEdit()
        self.input_main_needs.setMaximumHeight(70)
        self.input_main_needs.setPlaceholderText(
            "Ex: organizar estoque, cadastrar clientes, controlar prazos, gerar relatorios..."
        )
        self.check_offline = QCheckBox("Priorizar operacao local/offline e privacidade")

        form.addRow("Seu nome:", self.input_user_name)
        form.addRow("Empresa:", self.input_company_name)
        form.addRow("Setor:", self.input_company_sector)
        form.addRow("Porte:", self.input_company_size)
        form.addRow("Descricao:", self.input_company_description)
        form.addRow("Seu papel:", self.input_user_role)
        form.addRow("Tom preferido:", self.input_preferred_tone)
        form.addRow("Fuso horario:", self.input_timezone)
        form.addRow("Contexto:", self.input_business_context)
        form.addRow("Necessidades:", self.input_main_needs)
        form.addRow("", self.check_offline)
        form.addRow("Modo resposta:", self.combo_response_mode)
        form.addRow("Nivel de detalhe:", self.combo_response_detail)
        form.addRow("Criatividade:", self.input_response_temperature)
        form.addRow("Top-p:", self.input_response_top_p)
        form.addRow("", self.check_voice_enabled)
        form.addRow("Perfil de voz:", self.combo_voice_profile)
        form.addRow("Voz:", self.combo_voice)
        form.addRow("Velocidade:", self.input_voice_rate)
        form.addRow("Tom da voz:", self.input_voice_pitch)
        form.addRow("Volume:", self.input_voice_volume)
        form.addRow("", self.check_mobile_enabled)
        form.addRow("", self.check_mobile_lan)
        form.addRow("", self.check_mobile_voice)
        form.addRow("", self.check_mobile_https)
        form.addRow("Porta celular:", self.input_mobile_port)
        form.addRow("Token celular:", self.input_mobile_token)
        layout.addLayout(form)

        self.mobile_actions_title = QLabel("Celular")
        self.mobile_actions_title.setObjectName("section_title")
        layout.addWidget(self.mobile_actions_title)

        self.mobile_status_hint = QLabel("")
        self.mobile_status_hint.setWordWrap(True)
        self.mobile_status_hint.setObjectName("hint")
        layout.addWidget(self.mobile_status_hint)

        mobile_button_row = QHBoxLayout()
        mobile_button_row.setSpacing(8)
        self.btn_pair_mobile = QPushButton("Parear celular")
        self.btn_pair_mobile.setObjectName("btn_mobile_primary")
        self.btn_restart_mobile = QPushButton("Reiniciar acesso")
        self.btn_regenerate_mobile_token = QPushButton("Regenerar token")
        mobile_button_row.addWidget(self.btn_pair_mobile)
        mobile_button_row.addWidget(self.btn_restart_mobile)
        mobile_button_row.addWidget(self.btn_regenerate_mobile_token)
        mobile_button_row.addStretch()
        layout.addLayout(mobile_button_row)

        self.notifications_title = QLabel("Canais e Notificacoes")
        self.notifications_title.setObjectName("section_title")
        layout.addWidget(self.notifications_title)

        self.notifications_hint = QLabel(
            "WhatsApp, e-mail e SMS dependem de internet e servico externo. Tokens sensiveis "
            "devem ficar em variaveis de ambiente, nao no arquivo local de preferencias."
        )
        self.notifications_hint.setWordWrap(True)
        self.notifications_hint.setObjectName("hint")
        layout.addWidget(self.notifications_hint)

        notifications_form = QFormLayout()
        notifications_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        notifications_form.setFormAlignment(Qt.AlignTop)
        notifications_form.setHorizontalSpacing(14)
        notifications_form.setVerticalSpacing(10)
        notifications_form.addRow("", self.check_notifications_enabled)
        notifications_form.addRow("", self.check_notifications_external)
        notifications_form.addRow("", self.check_notifications_confirmation)
        notifications_form.addRow("Canal padrao:", self.combo_notification_channel)
        notifications_form.addRow("WhatsApp provedor:", self.input_whatsapp_provider)
        notifications_form.addRow("WhatsApp phone ID:", self.input_whatsapp_phone_id)
        notifications_form.addRow("Token env var:", self.input_whatsapp_token_env)
        notifications_form.addRow("E-mail provedor:", self.input_email_provider)
        notifications_form.addRow("E-mail remetente:", self.input_email_from)
        notifications_form.addRow("SMS provedor:", self.input_sms_provider)
        notifications_form.addRow("SMS remetente:", self.input_sms_sender)
        layout.addLayout(notifications_form)

        self.modules_title = QLabel("Modulos da empresa")
        self.modules_title.setObjectName("section_title")
        layout.addWidget(self.modules_title)

        self.modules_hint = QLabel(
            "Ative apenas o que faz sentido para esta empresa. Chat e Configuracoes ficam sempre visiveis."
        )
        self.modules_hint.setWordWrap(True)
        self.modules_hint.setObjectName("hint")
        layout.addWidget(self.modules_hint)

        self.module_checks: dict[str, QCheckBox] = {}
        modules_grid = QGridLayout()
        modules_grid.setHorizontalSpacing(18)
        modules_grid.setVerticalSpacing(8)
        for module in module_catalog():
            label = module.name
            if not module.is_ready:
                label = f"{label} (em preparacao)"
            check = QCheckBox(label)
            check.setToolTip(module.description)
            check.setEnabled(not module.mandatory)
            self.module_checks[module.id] = check
            index = len(self.module_checks) - 1
            modules_grid.addWidget(check, index // 2, index % 2)
        layout.addLayout(modules_grid)

        self.btn_suggest_modules = QPushButton("Sugerir modulos pelo segmento")
        layout.addWidget(self.btn_suggest_modules)

        self.storage_hint = QLabel("")
        self.storage_hint.setWordWrap(True)
        self.storage_hint.setObjectName("hint")
        layout.addWidget(self.storage_hint)

        self.scroll_area.setWidget(self.scroll_content)
        outer_layout.addWidget(self.scroll_area, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_save = QPushButton("Salvar")
        self.btn_save.setObjectName("btn_salvar")
        button_row.addWidget(self.btn_cancel)
        button_row.addWidget(self.btn_save)
        outer_layout.addLayout(button_row)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(lambda: self._save())
        self.btn_suggest_modules.clicked.connect(self._suggest_modules)
        self.btn_pair_mobile.clicked.connect(lambda: self._save_with_mobile_action("pair"))
        self.btn_restart_mobile.clicked.connect(lambda: self._save_with_mobile_action("restart"))
        self.btn_regenerate_mobile_token.clicked.connect(
            lambda: self._save_with_mobile_action("regenerate")
        )

    def _apply_selected_voice_profile(self):
        profile = resolve_tts_profile(self.combo_voice_profile.currentData())
        if profile is None or profile.experimental:
            return
        self.combo_voice.setCurrentText(profile.voice)
        self.input_voice_rate.setText(profile.rate)
        self.input_voice_pitch.setText(profile.pitch)
        self.input_voice_volume.setText(profile.volume)

    def _load_values(self):
        customer = self.settings.customer
        self.input_user_name.setText(customer.user_name)
        self.input_company_name.setText(customer.company_name)
        self.input_company_sector.setText(customer.company_sector)
        self.input_company_size.setText(customer.company_size)
        self.input_company_description.setPlainText(customer.company_description)
        self.input_user_role.setText(customer.user_role)
        self.input_preferred_tone.setText(customer.preferred_tone)
        self.input_timezone.setText(customer.timezone)
        self.input_business_context.setPlainText(customer.business_context)
        self.input_main_needs.setPlainText(customer.main_needs)
        self.check_offline.setChecked(customer.local_offline_required)
        enabled_modules = set(self.settings.modules.enabled)
        for module in module_catalog():
            self.module_checks[module.id].setChecked(module.id in enabled_modules)
        response = self.settings.response
        self.combo_response_mode.setCurrentText(response.mode)
        self.combo_response_detail.setCurrentText(response.detail_level)
        self.input_response_temperature.setText(str(response.temperature))
        self.input_response_top_p.setText(str(response.top_p))
        voice = self.settings.voice
        self.check_voice_enabled.setChecked(voice.enabled)
        profile_index = self.combo_voice_profile.findData(voice.profile)
        if profile_index >= 0:
            self.combo_voice_profile.blockSignals(True)
            self.combo_voice_profile.setCurrentIndex(profile_index)
            self.combo_voice_profile.blockSignals(False)
        self.combo_voice.setCurrentText(voice.voice)
        self.input_voice_rate.setText(voice.rate)
        self.input_voice_pitch.setText(voice.pitch)
        self.input_voice_volume.setText(voice.volume)
        mobile = self.settings.mobile
        if not mobile.pairing_token:
            mobile.pairing_token = ensure_mobile_token()
        self.check_mobile_enabled.setChecked(mobile.enabled)
        self.check_mobile_lan.setChecked(mobile.allow_lan)
        self.check_mobile_voice.setChecked(mobile.voice_commands_enabled)
        self.check_mobile_https.setChecked(mobile.use_https)
        self.input_mobile_port.setText(str(mobile.port))
        self.input_mobile_token.setText(mobile.pairing_token)
        notifications = self.settings.notifications
        self.check_notifications_enabled.setChecked(notifications.enabled)
        self.check_notifications_external.setChecked(notifications.external_services_allowed)
        self.check_notifications_confirmation.setChecked(notifications.require_confirmation)
        self.combo_notification_channel.setCurrentText(notifications.default_channel)
        self.input_whatsapp_provider.setText(notifications.whatsapp_provider)
        self.input_whatsapp_phone_id.setText(notifications.whatsapp_phone_number_id)
        self.input_whatsapp_token_env.setText(notifications.whatsapp_token_env_var)
        self.input_email_provider.setText(notifications.email_provider)
        self.input_email_from.setText(notifications.email_from)
        self.input_sms_provider.setText(notifications.sms_provider)
        self.input_sms_sender.setText(notifications.sms_sender_id)
        self._update_mobile_status_hint()
        self.storage_hint.setText(
            f"Perfil: {self.settings.customer_profile_file}\n"
            f"Preferencias: {self.settings.local_preferences_file}"
        )

    def _apply_theme(self):
        s = self._scheme
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {s.bg_primary};
                color: {s.text_primary};
            }}
            QLabel {{
                color: {s.text_primary};
                font-size: 13px;
                background: transparent;
            }}
            QLabel#title {{
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#section_title {{
                font-size: 15px;
                font-weight: 700;
                margin-top: 8px;
            }}
            QLabel#subtitle, QLabel#hint {{
                color: {s.text_secondary};
            }}
            QLineEdit, QTextEdit, QComboBox {{
                background-color: {s.bg_secondary};
                border: 1px solid {s.border_default};
                border-radius: 6px;
                color: {s.text_primary};
                padding: 8px;
                font-size: 13px;
                selection-background-color: {s.accent_primary}40;
            }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
                border-color: {s.accent_primary};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QCheckBox {{
                color: {s.text_primary};
                spacing: 8px;
                background: transparent;
            }}
            QPushButton {{
                background-color: {s.bg_tertiary};
                color: {s.text_primary};
                border: 1px solid {s.border_default};
                border-radius: 6px;
                font-weight: 600;
                min-width: 90px;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                background-color: {s.bg_hover};
            }}
            QPushButton#btn_salvar {{
                background-color: {s.accent_primary};
                color: {s.text_on_accent};
                border-color: {s.accent_primary};
            }}
            QPushButton#btn_salvar:hover {{
                background-color: {s.accent_hover};
            }}
            QPushButton#btn_mobile_primary {{
                background-color: {s.accent_primary};
                color: {s.text_on_accent};
                border-color: {s.accent_primary};
            }}
            QPushButton#btn_mobile_primary:hover {{
                background-color: {s.accent_hover};
            }}
        """)

    def _save(self, mobile_action: str | None = None):
        self.mobile_action = mobile_action
        self._apply_form_values(regenerate_token=mobile_action == "regenerate")
        self.settings.save_customer_profile()
        self.accept()

    def _save_with_mobile_action(self, action: str):
        if action in {"pair", "restart", "regenerate"}:
            self.check_mobile_enabled.setChecked(True)
            self.check_mobile_lan.setChecked(True)
        self._save(action)

    def _apply_form_values(self, *, regenerate_token: bool = False):
        def _float_from_input(value: str, default: float) -> float:
            try:
                return float(value.strip().replace(",", "."))
            except ValueError:
                return default

        customer = self.settings.customer
        customer.user_name = self.input_user_name.text().strip()
        customer.company_name = self.input_company_name.text().strip()
        customer.company_sector = self.input_company_sector.text().strip()
        customer.company_size = self.input_company_size.text().strip()
        customer.company_description = self.input_company_description.toPlainText().strip()
        customer.user_role = self.input_user_role.text().strip()
        customer.preferred_tone = self.input_preferred_tone.text().strip()
        customer.timezone = self.input_timezone.text().strip()
        customer.business_context = self.input_business_context.toPlainText().strip()
        customer.main_needs = self.input_main_needs.toPlainText().strip()
        customer.local_offline_required = self.check_offline.isChecked()
        self.settings.modules.set_enabled(
            module_id
            for module_id, check in self.module_checks.items()
            if check.isChecked() or not check.isEnabled()
        )
        response = self.settings.response
        response.mode = self.combo_response_mode.currentText()
        response.detail_level = self.combo_response_detail.currentText()
        response.temperature = _float_from_input(self.input_response_temperature.text(), 0.45)
        response.top_p = _float_from_input(self.input_response_top_p.text(), 0.9)
        voice = self.settings.voice
        voice.enabled = self.check_voice_enabled.isChecked()
        voice.provider = "edge-tts"
        voice.profile = self.combo_voice_profile.currentData() or "natural_male_br"
        voice.voice = self.combo_voice.currentText()
        voice.rate = self.input_voice_rate.text().strip() or "+5%"
        voice.pitch = self.input_voice_pitch.text().strip() or "-2Hz"
        voice.volume = self.input_voice_volume.text().strip() or "+0%"
        mobile = self.settings.mobile
        mobile.enabled = self.check_mobile_enabled.isChecked()
        mobile.allow_lan = self.check_mobile_lan.isChecked()
        mobile.voice_commands_enabled = self.check_mobile_voice.isChecked()
        mobile.use_https = self.check_mobile_https.isChecked()
        mobile.host = "0.0.0.0"
        try:
            mobile.port = max(1024, min(65535, int(self.input_mobile_port.text().strip())))
        except ValueError:
            mobile.port = 8787
        token_source = "" if regenerate_token else self.input_mobile_token.text()
        mobile.pairing_token = ensure_mobile_token(token_source)
        notifications = self.settings.notifications
        notifications.enabled = self.check_notifications_enabled.isChecked()
        notifications.external_services_allowed = self.check_notifications_external.isChecked()
        notifications.require_confirmation = self.check_notifications_confirmation.isChecked()
        notifications.default_channel = self.combo_notification_channel.currentText()
        notifications.whatsapp_provider = self.input_whatsapp_provider.text().strip()
        notifications.whatsapp_phone_number_id = self.input_whatsapp_phone_id.text().strip()
        notifications.whatsapp_token_env_var = (
            self.input_whatsapp_token_env.text().strip() or "CELSIUS_WHATSAPP_TOKEN"
        )
        notifications.email_provider = self.input_email_provider.text().strip()
        notifications.email_from = self.input_email_from.text().strip()
        notifications.sms_provider = self.input_sms_provider.text().strip()
        notifications.sms_sender_id = self.input_sms_sender.text().strip()

    def _update_mobile_status_hint(self):
        mobile = self.settings.mobile
        status = "Ativo" if mobile.enabled else "Desativado"
        alcance = "rede Wi-Fi" if mobile.allow_lan else "somente este PC"
        protocolo = "HTTPS" if mobile.use_https else "HTTP"
        self.mobile_status_hint.setText(
            f"Status atual: {status} | Alcance: {alcance} | Protocolo preferido: {protocolo}. "
            "Use Parear celular para abrir o QR Code sem depender do botao Salvar."
        )

    def _suggest_modules(self):
        suggested = set(
            suggest_modules_for_company(
                self.input_company_sector.text(),
                self.input_main_needs.toPlainText(),
            )
        )
        for module_id, check in self.module_checks.items():
            if check.isEnabled():
                check.setChecked(module_id in suggested)
