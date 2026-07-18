CSS_BASE = """
QMainWindow {
    background-color: #0d1117;
}

QWidget {
    font-family: 'Segoe UI', 'Segoe UI Variable', sans-serif;
    font-size: 15px;
    color: #e6edf3;
}

QLabel#titulo {
    font-size: 20px;
    font-weight: 600;
    color: #58a6ff;
    padding: 8px 0px 4px 0px;
    letter-spacing: 1px;
}

QLabel#subtitulo {
    font-size: 11px;
    color: #8b949e;
    padding-bottom: 6px;
}

QTextEdit#chat_area {
    background-color: #0d1117;
    border: none;
    font-size: 14px;
    line-height: 1.65;
    padding: 10px 16px;
    selection-background-color: #1f6feb44;
}

QWidget#input_container {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 24px;
    padding: 6px 14px;
}

QLineEdit#chat_input {
    background-color: transparent;
    border: none;
    color: #e6edf3;
    padding: 6px 0px;
    font-size: 15px;
}

QLineEdit#chat_input::placeholder {
    color: #484f58;
}

QPushButton {
    background-color: #21262d;
    border: none;
    border-radius: 16px;
    color: #e6edf3;
    padding: 8px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #30363d;
}

QPushButton:disabled {
    background-color: #161b22;
    color: #484f58;
}

QPushButton#btn_enviar {
    background-color: #238636;
    color: #ffffff;
    border-radius: 18px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    padding: 0px;
    font-size: 16px;
    font-weight: bold;
}

QPushButton#btn_enviar:hover {
    background-color: #2ea043;
}

QPushButton#btn_enviar:disabled {
    background-color: #1a7f37;
    color: #ffffff80;
}

QPushButton#btn_mic, QPushButton#btn_anexo {
    background-color: transparent;
    color: #8b949e;
    border-radius: 18px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    font-size: 18px;
}

QPushButton#btn_mic:hover, QPushButton#btn_anexo:hover {
    background-color: #21262d;
    color: #e6edf3;
}

QPushButton#btn_mic[gravando="true"] {
    background-color: #da3633;
    color: #ffffff;
    animation: pulse 1s infinite;
}

QPushButton#btn_util {
    background-color: transparent;
    border: 1px solid #30363d;
    color: #8b949e;
    font-size: 11px;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: 500;
}

QPushButton#btn_util:hover {
    background-color: #21262d;
    color: #e6edf3;
    border-color: #484f58;
}

QPushButton#btn_util:disabled {
    color: #484f58;
    border-color: #21262d;
}

QWidget#container_anexo {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 6px 12px;
}

QComboBox#combo_modelo {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    color: #8b949e;
    font-size: 11px;
    padding: 4px 10px;
    min-width: 180px;
}

QComboBox#combo_modelo:hover {
    background-color: #21262d;
    color: #e6edf3;
    border-color: #484f58;
}

QComboBox#combo_modelo::drop-down {
    border: none;
    width: 20px;
}

QComboBox#combo_modelo QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    color: #e6edf3;
    selection-background-color: #21262d;
    outline: none;
}

QScrollBar:vertical {
    background-color: #0d1117;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #30363d;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #484f58;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QToolTip {
    background-color: #1c2128;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}
"""

CSS_CHATGPT = CSS_BASE
