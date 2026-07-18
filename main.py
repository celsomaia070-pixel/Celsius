import sys

from PySide6.QtWidgets import QApplication

from ui.window import ModernChatWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ModernChatWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
