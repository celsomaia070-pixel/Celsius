from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from ui.theme.schemes import ColorScheme, get_scheme
from core.memory import get_memory_service


class CaixaMemoriaDialog(QDialog):
    def __init__(self, memory_service=None, parent=None, scheme: ColorScheme | None = None):
        super().__init__(parent)
        self.memory_service = memory_service or get_memory_service()
        self._scheme = scheme or get_scheme()
        self.setWindowTitle("Adicionar Memória")
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
