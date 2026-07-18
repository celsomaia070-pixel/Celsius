from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout


class CaixaMemoriaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Memoria")
        self.setFixedSize(450, 160)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog { background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; }
            QLabel { color: #e6edf3; font-size: 14px; font-weight: 500; }
            QLineEdit { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; color: #e6edf3; padding: 8px; font-size: 14px; }
            QLineEdit:focus { border-color: #58a6ff; }
            QPushButton { background-color: #21262d; color: #e6edf3; border: none; border-radius: 6px; font-weight: bold; min-width: 80px; padding: 6px 14px; }
            QPushButton:hover { background-color: #30363d; }
            QPushButton#btn_salvar { background-color: #238636; color: #ffffff; }
            QPushButton#btn_salvar:hover { background-color: #2ea043; }
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

        self.btn_salvar.clicked.connect(self.accept)
        self.btn_cancelar.clicked.connect(self.reject)

    def obter_texto(self):
        return self.input_texto.text().strip()


class FormatoRelatorioDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Formato do Relatorio")
        self.setFixedSize(300, 120)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._formato = "pdf"

        self.setStyleSheet("""
            QDialog { background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; }
            QLabel { color: #e6edf3; font-size: 14px; font-weight: 500; }
            QPushButton { background-color: #21262d; color: #e6edf3; border: none; border-radius: 6px; font-weight: bold; min-width: 100px; padding: 8px 16px; }
            QPushButton:hover { background-color: #30363d; }
            QPushButton#btn_pdf { background-color: #da3633; color: #ffffff; }
            QPushButton#btn_pdf:hover { background-color: #f85149; }
            QPushButton#btn_docx { background-color: #1f6feb; color: #ffffff; }
            QPushButton#btn_docx:hover { background-color: #388bfd; }
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
