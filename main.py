import contextlib
import faulthandler
import json
import logging
import os
import signal
import sys
import threading  # noqa: F401 (usado em enumerate/main_thread)
import traceback
from pathlib import Path

VERSION = "1.0.0"
logger = logging.getLogger(__name__)
_FAULT_LOG_STREAM = None

BANNER = r"""
   _____ _                            _
  / ____| |                          | |
 | |    | |__   ___  _ __   ___  _ __| |_ ___ _ __
 | |    | '_ \ / _ \| '_ \ / _ \| '__| __/ _ \ '__|
 | |____| | | | (_) | | | | (_) | |  | ||  __/ |
  \_____|_| |_|\___/|_| |_|\___/|_|   \__\___|_|
                                        v{version}
"""


def _safe_print(message: str) -> None:
    """Write only when the current executable has a usable console stream."""

    stream = getattr(sys, "stdout", None)
    if stream is None:
        return
    with contextlib.suppress(AttributeError, OSError):
        print(message, file=stream)


def _enable_faulthandler(log_path: str | Path | None = None) -> None:
    """Enable native crash diagnostics in console and windowed executables."""

    global _FAULT_LOG_STREAM
    if faulthandler.is_enabled():
        return
    stream = getattr(sys, "stderr", None)
    try:
        if stream is None and log_path is not None:
            path = Path(log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            _FAULT_LOG_STREAM = path.open("a", encoding="utf-8")
            stream = _FAULT_LOG_STREAM
        if stream is not None:
            faulthandler.enable(file=stream, all_threads=True)
    except (AttributeError, OSError, RuntimeError):
        _FAULT_LOG_STREAM = None


def _print_banner() -> None:
    _safe_print(BANNER.format(version=VERSION))


def _self_test_report_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    base_dir = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base_dir / "Celsius" / "logs" / "self-test.json"


def _write_self_test_report(
    result: dict,
    *,
    report_path: str | Path | None = None,
) -> Path:
    path = Path(report_path) if report_path is not None else _self_test_report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _start_health_check(app, model_id: str, settings):
    """Start periodic health check for the LLM model."""
    from PySide6.QtCore import QTimer

    from core.llama_cpp import get_llama_manager

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


def run_self_test() -> int:
    """Validate the frozen runtime without starting the model or opening the UI."""
    required_modules = (
        "ai.engine",
        "ai.react",
        "ai.tools",
        "core.agenda",
        "core.charts",
        "core.chat_attachments",
        "core.chat_service",
        "core.container",
        "core.conversations",
        "core.inventory",
        "core.logging_config",
        "core.mobile_access",
        "core.notifications",
        "core.telemetry",
        "core.web_api.app",
        "core.web_api.server",
        "processors.pdf",
        "ui.window",
        "workers.ai_worker",
        "workers.mic_worker",
        "workers.tts_worker",
    )
    imported = []
    current_step = "loading settings"
    try:
        from core.settings import get_settings

        settings = get_settings()
        current_step = "enabling crash diagnostics"
        _enable_faulthandler(settings.logs_dir / "fault.log")
        for module_name in required_modules:
            current_step = f"importing {module_name}"
            __import__(module_name)
            imported.append(module_name)

        current_step = "checking writable directories"
        for directory in (settings.base_dir, settings.data_dir, settings.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        marker = settings.data_dir / ".celsius-write-test"
        marker.write_text("ok", encoding="utf-8")
        marker.unlink()

        current_step = "checking configured model"
        model_path = settings.get_model_path(settings.model.llm_model)
        model_loaded = False
        if getattr(sys, "frozen", False) and model_path.is_file():
            current_step = "loading configured model"
            from core.llama_cpp import get_llama_manager

            manager = get_llama_manager()
            try:
                model_loaded = manager.start(
                    model_id=settings.model.llm_model,
                    n_gpu_layers=settings.model.n_gpu_layers,
                    n_ctx=settings.model.num_ctx,
                    n_batch=settings.model.n_batch,
                    n_threads=settings.model.n_threads,
                )
                if not model_loaded:
                    raise RuntimeError("O gerenciador local recusou o carregamento do modelo.")
            finally:
                manager.stop()

        result = {
            "ok": True,
            "version": VERSION,
            "frozen": bool(getattr(sys, "frozen", False)),
            "base_dir": str(settings.base_dir),
            "data_dir": str(settings.data_dir),
            "resources_dir": str(settings.resources_dir),
            "model_id": settings.model.llm_model,
            "model_available": model_path.is_file(),
            "model_loaded": model_loaded,
            "model_path": str(model_path),
            "imports": imported,
        }
        _write_self_test_report(result)
        _safe_print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        result = {
            "ok": False,
            "version": VERSION,
            "frozen": bool(getattr(sys, "frozen", False)),
            "step": current_step,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "imports": imported,
            "traceback": traceback.format_exc(),
        }
        with contextlib.suppress(Exception):
            _write_self_test_report(result)
        _safe_print(json.dumps(result, ensure_ascii=False))
        return 1


def main():
    from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

    from core.app_context import CelsiusAppContext
    from core.settings import get_settings
    from ui.window import ModernChatWindow

    _print_banner()

    settings = get_settings()
    _enable_faulthandler(settings.logs_dir / "fault.log")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    startup_progress = QProgressDialog(
        "Inicializando o Celsius...",
        None,
        0,
        0,
    )
    startup_progress.setWindowTitle("Celsius Project AI")
    startup_progress.setCancelButton(None)
    startup_progress.setMinimumDuration(0)
    startup_progress.setAutoClose(False)
    startup_progress.setAutoReset(False)
    startup_progress.show()
    app.processEvents()

    def update_startup_status(message: str) -> None:
        startup_progress.setLabelText(message)
        app.processEvents()

    update_startup_status("Preparando os componentes locais...")

    def _ask_model_download(model) -> bool:
        size_text = f" aproximadamente {model.size_gb:.1f} GB" if model else ""
        answer = QMessageBox.question(
            None,
            "Baixar modelo local",
            "O modelo de inteligencia artificial ainda nao esta instalado.\n\n"
            f"O Celsius precisa baixar{size_text} pela internet "
            "(o suporte visual pode exigir um arquivo adicional). "
            "O download sera salvo somente neste computador.\n\n"
            "Deseja iniciar agora?",
            QMessageBox.Yes | QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    context = CelsiusAppContext(
        settings=settings,
        status=update_startup_status,
        confirm_download=lambda _settings, model: _ask_model_download(model),
    )
    if not context.start():
        startup_progress.close()
        QMessageBox.critical(
            None,
            "Celsius nao pode iniciar",
            context.failure_message or "Erro desconhecido ao iniciar o Celsius.",
        )
        return 1

    update_startup_status("Abrindo a interface...")
    window = ModernChatWindow()
    window.show()
    startup_progress.close()
    app.processEvents()

    def _safe_shutdown():
        context.shutdown()

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
        if "--self-test" in sys.argv:
            sys.exit(run_self_test())
        sys.exit(main())
    except Exception as exc:
        if logging.getLogger().handlers:
            logger.exception("Fatal application error")
        result = {
            "ok": False,
            "version": VERSION,
            "frozen": bool(getattr(sys, "frozen", False)),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        with contextlib.suppress(Exception):
            _write_self_test_report(
                result,
                report_path=_self_test_report_path().with_name("startup-error.json"),
            )
        _safe_print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)
