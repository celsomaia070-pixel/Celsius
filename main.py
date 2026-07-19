import sys
from PySide6.QtWidgets import QApplication, QMessageBox

from core.llama_server import start_llama_server, stop_llama_server
from ui.window import ModernChatWindow


def main():
    # Start embedded llama-server
    if not start_llama_server(wait_ready=True):
        QMessageBox.critical(
            None,
            "Erro ao iniciar LLM local",
            "Nao foi possivel iniciar o servidor de modelo local (llama-server).\n"
            "Verifique se os arquivos 'resources/llama-server' e 'resources/model.gguf' existem.",
        )
        return 1

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ModernChatWindow()
    window.show()

    # Ensure server stops on app exit
    app.aboutToQuit.connect(stop_llama_server)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
