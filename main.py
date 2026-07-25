import contextlib
import faulthandler
import os
import signal
import subprocess
import sys
import threading
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from core.config import get_model_by_id, get_settings
from core.llama_cpp import get_llama_manager, stop_llama_server
from core.model_downloader import download_mmproj, download_model, is_model_downloaded
from ui.window import ModernChatWindow


def _start_health_check(app: QApplication, model_id: str) -> QTimer:
    """Start periodic health check for the LLM model."""
    manager = get_llama_manager()

    def check_health():
        if not manager.is_healthy():
            print("[HealthCheck] Model unhealthy, attempting recovery...")
            try:
                manager.stop()
                if not manager.start(model_id=model_id, n_gpu_layers=-1, n_ctx=16384, n_batch=1024):
                    print("[HealthCheck] Failed to recover model")
            except Exception as e:
                print(f"[HealthCheck] Recovery failed: {e}")

    timer = QTimer()
    timer.timeout.connect(check_health)
    timer.start(300000)  # Check every 5 minutes
    return timer


def main():
    faulthandler.enable()

    try:
        import edge_tts
    except ImportError:
        pass

    try:
        import sentence_transformers
    except ImportError:
        pass

    try:
        import transformers
    except ImportError:
        pass

    # Pre-load embedding model on main thread (avoids GC crash in worker threads on Python 3.14)
    try:
        from ai.agents import preload_embedding_model
        preload_embedding_model()
    except Exception:
        pass

    # Pre-load Whisper model in background (evita delay na primeira uso)
    _whisper_preloader = None
    try:
        from PySide6.QtCore import QThread
        class WhisperPreloader(QThread):
            def run(self):
                try:
                    from workers.mic_worker import preload_whisper_model
                    preload_whisper_model()
                except Exception:
                    pass
        _whisper_preloader = WhisperPreloader()
        _whisper_preloader.start()
    except Exception:
        pass

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
    from core.llama_cpp import start_llama_server

    try:
        if not start_llama_server(n_gpu_layers=-1, n_ctx=16384, n_batch=1024):
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
    def _safe_shutdown():
        with contextlib.suppress(Exception):
            stop_llama_server()

    app.aboutToQuit.connect(_safe_shutdown)

    # Start periodic health check
    _start_health_check(app, settings.llm_model)

    # Override default ctrl+c to avoid crash from interrupted threads
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    result = app.exec()

    # Force cleanup of remaining threads
    for thread in threading.enumerate():
        if thread is not threading.main_thread() and thread.is_alive():
            thread.join(timeout=1.0)

    return result


def _on_download_done(app, msg, ok, error):
    msg.close()
    if ok:
        app.quit()
        # Restart with guard to avoid infinite restart loops
        env = os.environ.copy()
        env["CELSIUS_RESTARTED"] = "1"
        subprocess.Popen([sys.executable] + sys.argv, env=env)
    else:
        QMessageBox.critical(None, "Erro", f"Falha ao baixar modelo: {error}")
        app.quit()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        pass
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    finally:
        os._exit(0)
