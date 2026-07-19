import sys
from PySide6.QtWidgets import QApplication, QMessageBox

from core.llama_cpp import start_llama_server, stop_llama_server
from ui.window import ModernChatWindow


def main():
    # Start embedded Llama with GPU acceleration (Vulkan for AMD RX 7600)
    # n_gpu_layers=-1 = offload all possible layers to GPU
    if not start_llama_server(n_gpu_layers=-1, n_ctx=8192, n_batch=512):
        QMessageBox.critical(
            None,
            "Erro ao iniciar LLM local",
            "Nao foi possivel iniciar o modelo local (llama.cpp).\n"
            "Verifique se o arquivo 'resources/model.gguf' existe.",
        )
        return 1

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ModernChatWindow()
    window.show()

    # Ensure model stops on app exit
    app.aboutToQuit.connect(stop_llama_server)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
