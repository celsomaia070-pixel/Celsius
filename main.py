import contextlib
import faulthandler
import logging
import signal
import sys
import threading
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from core.container import get_container, reset_container
from core.llama_cpp import get_llama_manager, stop_llama_server
from core.logging_config import setup_logging
from core.settings import get_feature_flags, get_settings
from core.telemetry import init_telemetry, shutdown_telemetry
from ui.window import ModernChatWindow

VERSION = "1.0.0"
logger = logging.getLogger(__name__)

BANNER = r"""
   _____ _                            _
  / ____| |                          | |
 | |    | |__   ___  _ __   ___  _ __| |_ ___ _ __
 | |    | '_ \ / _ \| '_ \ / _ \| '__| __/ _ \ '__|
 | |____| | | | (_) | | | | (_) | |  | ||  __/ |
  \_____|_| |_|\___/|_| |_|\___/|_|   \__\___|_|
                                        v{version}
"""


def _print_banner():
    print(BANNER.format(version=VERSION))


def _start_health_check(app: QApplication, model_id: str, settings) -> QTimer:
    """Start periodic health check for the LLM model."""
    manager = get_llama_manager()

    def check_health():
        if not manager.is_healthy():
            logger.warning("Model unhealthy, attempting recovery")
            try:
                manager.stop()
                if not manager.start(
                    model_id=model_id,
                    n_gpu_layers=settings.model.n_gpu_layers,
                    n_ctx=settings.model.num_ctx,
                    n_batch=settings.model.n_batch,
                    n_threads=settings.model.n_threads,
                ):
                    logger.error("Failed to recover model")
            except Exception as e:
                logger.exception("Model recovery failed: %s", e)

    timer = QTimer(app)
    timer.timeout.connect(check_health)
    timer.start(300000)
    return timer


def _import_optional(name: str):
    try:
        return __import__(name)
    except ImportError:
        return None


def _ensure_model_available(settings) -> None:
    model_id = settings.model.llm_model
    model_path = settings.get_model_path(model_id)
    if model_path.exists():
        return

    logger.info("Modelo ausente: %s. Tentando download sob demanda", model_path.name)
    from core.model_downloader import download_mmproj, download_model

    downloaded = download_model(model_id, fn_status=lambda msg: logger.info("[Model] %s", msg))
    if downloaded is None:
        raise FileNotFoundError(
            f"Modelo '{model_id}' nao encontrado e download automatico falhou.\n"
            f"Coloque o arquivo GGUF em {settings.resources_dir} ou escolha outro modelo."
        )
    download_mmproj(model_id, fn_status=lambda msg: logger.info("[Model] %s", msg))


def main():
    faulthandler.enable()
    _print_banner()

    _import_optional("edge_tts")
    _import_optional("sentence_transformers")
    _import_optional("transformers")

    settings = get_settings()
    setup_logging(
        level=settings.telemetry.log_level.value,
        log_file=str(settings.logs_dir / "celsius.log"),
    )
    telemetry_settings = settings.telemetry
    if telemetry_settings.enabled:
        init_telemetry(
            service_name=telemetry_settings.service_name,
            service_version=VERSION,
            otlp_endpoint=telemetry_settings.otlp_endpoint,
            sample_rate=telemetry_settings.sample_rate,
            log_level=telemetry_settings.log_level.value,
        )

    get_container()
    features = get_feature_flags()

    # Log hardware observations (informational only — never overrides user model)
    if settings.hardware.auto_detect:
        try:
            from core.hardware import detect_hardware
            from core.model_selector import select_optimal_model

            profile = detect_hardware()
            recommendation = select_optimal_model(profile)
            logger.info("Hardware detected: %s", recommendation.profile.summary)
            logger.info("Modelo recomendado: %s", recommendation.main_model_id)
            logger.info("Modelo ativo: %s", settings.model.llm_model)
        except Exception as e:
            logger.warning("Deteccao de hardware falhou: %s", e)

    # Pre-load embedding model on main thread (avoids GC crash in worker threads on Python 3.14)
    if features.multi_agent:
        try:
            from ai.agents import preload_embedding_model

            preload_embedding_model()
        except Exception:
            pass

    # Pre-load Whisper model in background
    _whisper_preloader = None
    if features.voice_input:
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

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from core.llama_cpp import start_llama_server

    try:
        _ensure_model_available(settings)
        if not start_llama_server(
            n_gpu_layers=settings.model.n_gpu_layers,
            n_ctx=settings.model.num_ctx,
            n_batch=settings.model.n_batch,
            n_threads=settings.model.n_threads,
        ):
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

    def _safe_shutdown():
        with contextlib.suppress(Exception):
            stop_llama_server()
        with contextlib.suppress(Exception):
            shutdown_telemetry()
        with contextlib.suppress(Exception):
            reset_container()

    app.aboutToQuit.connect(_safe_shutdown)

    _start_health_check(app, settings.model.llm_model, settings)

    signal.signal(signal.SIGINT, lambda *_: app.quit())

    result = app.exec()

    for thread in threading.enumerate():
        if thread is not threading.main_thread() and thread.is_alive():
            thread.join(timeout=1.0)

    return result


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logger.exception("Fatal application error")
        traceback.print_exc()
        sys.exit(1)
