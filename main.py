import sys
import traceback
import faulthandler
from PySide6.QtWidgets import QApplication, QMessageBox

from core.config import get_settings, get_model_by_id
from core.model_downloader import is_model_downloaded, download_model, download_mmproj
from ui.window import ModernChatWindow


def main():
    faulthandler.enable()
    settings = get_settings()
    model = get_model_by_id(settings.llm_model)

    # Create QApplication first (needed for dialogs)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Check if model is downloaded
    if model and not is_model_downloaded(settings.llm_model):
        reply = QMessageBox.question(
            None,
            "Modelo nao encontrado",
            f"O modelo '{model.name}' ({model.quant}) nao foi baixado ainda.\n"
            f"Tamanho: ~{model.size_gb}GB\n\n"
            f"Deseja baixar agora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            from PySide6.QtCore import QThread, Signal

            class DownloadThread(QThread):
                done = Signal(bool, str)

                def run(self):
                    try:
                        download_model(settings.llm_model)
                        if model.has_mmproj:
                            download_mmproj(settings.llm_model)
                        self.done.emit(True, "")
                    except Exception as e:
                        self.done.emit(False, str(e))

            # Show downloading message
            msg = QMessageBox()
            msg.setWindowTitle("Baixando modelo")
            msg.setText(f"Baixando {model.name}... Aguarde.")
            msg.setStandardButtons(QMessageBox.NoButton)
            msg.show()

            thread = DownloadThread()
            thread.done.connect(lambda ok, err: _on_download_done(app, msg, ok, err))
            thread.start()
            app.exec()
            return 0
        else:
            return 0

    # Start embedded Llama with GPU acceleration
    from core.llama_cpp import start_llama_server, stop_llama_server

    try:
        if not start_llama_server(n_gpu_layers=-1, n_ctx=8192, n_batch=1024):
            QMessageBox.critical(
                None,
                "Erro ao iniciar LLM local",
                "Nao foi possivel iniciar o modelo local (llama.cpp).\n"
                "Verifique se o arquivo GGUF existe na pasta resources/.",
            )
            return 1
    except FileNotFoundError as e:
        QMessageBox.critical(
            None,
            "Modelo nao encontrado",
            str(e),
        )
        return 1
    window = ModernChatWindow()
    window.show()

    # Ensure model stops on app exit
    app.aboutToQuit.connect(stop_llama_server)

    return app.exec()


def _on_download_done(app, msg, ok, error):
    msg.close()
    if ok:
        app.quit()
        # Restart
        import subprocess
        subprocess.Popen([sys.executable] + sys.argv)
    else:
        QMessageBox.critical(None, "Erro", f"Falha ao baixar modelo: {error}")
        app.quit()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
