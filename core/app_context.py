"""Non-Qt application lifecycle: logging, telemetry, model and local servers.

Keeps the heavy startup orchestration out of ``main.py`` so it can be tested
headlessly. Qt concerns (progress dialog, message boxes, window) stay in the
entry point and are passed in as callbacks.
"""

from __future__ import annotations

import contextlib
import faulthandler
import logging
import os
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from core.container import get_container, reset_container
from core.file_security import restrict_private_directory
from core.llama_cpp import start_llama_server, stop_llama_server
from core.logging_config import setup_logging
from core.mobile_access import get_mobile_runtime, rotate_mobile_token, start_for_settings
from core.settings import Settings, get_feature_flags, get_settings
from core.sqlite_store import DEFAULT_BACKUP_KEEP, backup_database, db_path_for
from core.telemetry import init_telemetry, shutdown_telemetry

logger = logging.getLogger(__name__)

#: Tests opt out of creating real ``backups/`` folders on shutdown.
_SKIP_BACKUP_UNDER_PYTEST = True

StatusCallback = Callable[[str], None]
ConfirmDownload = Callable[["Settings", object], bool]

VERSION = "1.0.0"
_FAULT_LOG_STREAM = None


def enable_faulthandler(log_path: str | Path | None = None) -> None:
    """Enable native crash diagnostics in console and windowed executables."""
    global _FAULT_LOG_STREAM
    if faulthandler.is_enabled():
        return
    stream = getattr(__import__("sys"), "stderr", None)
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


def _import_optional(name: str):
    try:
        return __import__(name)
    except ImportError:
        return None


def _ensure_model_available(settings, fn_status=None) -> None:
    model_id = settings.model.llm_model
    from core.config import get_model_by_id
    from core.model_downloader import download_mmproj, download_model

    def report(message: str) -> None:
        logger.info("[Model] %s", message)
        if fn_status:
            fn_status(message)

    model_path = settings.get_model_path(model_id)
    if not model_path.exists():
        logger.info("Modelo ausente: %s. Tentando download sob demanda", model_path.name)
        downloaded = download_model(model_id, fn_status=report)
        if downloaded is None:
            raise FileNotFoundError(
                f"Modelo '{model_id}' nao encontrado e download automatico falhou.\n"
                f"Coloque o arquivo GGUF em {settings.resources_dir} ou escolha outro modelo."
            )

    model = get_model_by_id(model_id)
    if (
        model
        and model.has_mmproj
        and settings.get_mmproj_path(model_id) is None
        and download_mmproj(model_id, fn_status=report) is None
    ):
        logger.warning("Projetor visual nao foi obtido; analise de imagens ficara indisponivel")


class CelsiusAppContext:
    """Owns the runtime components started before the window opens."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        status: StatusCallback | None = None,
        confirm_download: ConfirmDownload | None = None,
        start_llama: bool = True,
        start_web: bool = True,
    ) -> None:
        self.settings = settings or get_settings()
        self._status = status or (lambda _message: None)
        self._confirm_download = confirm_download
        self.start_llama = start_llama
        self.start_web = start_web

        self.web_api_server: Any | None = None
        self._whisper_thread: threading.Thread | None = None
        self._llama_started = False
        self._started = False
        self.failure_message: str | None = None

    def report(self, message: str) -> None:
        self._status(message)
        logger.info("%s", message)

    def start(self) -> bool:
        settings = self.settings
        self.failure_message = None
        try:
            self._prepare_private_runtime(settings)
            self._bootstrap_logging(settings)
            self._start_decision_layer(settings)
            if getattr(settings.customer, "local_offline_required", False):
                self.report(
                    "Celsius em MODO OFF-LINE: documentos, memorias e dados permanecem nesta maquina."
                )
            self._log_hardware(settings)
            features = get_feature_flags()
            self._preload_embeddings(features)
            self._preload_whisper(features)

            if self.start_llama and not self._prepare_model(settings):
                return False
            if self.start_web:
                self._start_web_server(settings)
            self._start_mobile(settings)

            self._started = True
            return True
        except FileNotFoundError as exc:
            self.failure_message = str(exc)
        except Exception as exc:
            logger.exception("Falha ao iniciar o Celsius: %s", exc)
            self.failure_message = f"{type(exc).__name__}: {exc}"
        self._started = False
        self.shutdown()
        return False

    @staticmethod
    def _prepare_private_runtime(settings: Settings) -> None:
        """Keep application and third-party caches inside a private local tree."""
        restrict_private_directory(settings.data_dir)
        cache_dir = settings.data_dir / "cache"
        restrict_private_directory(cache_dir)
        os.environ.setdefault("CELSIUS_CACHE_HOME", str(cache_dir))
        os.environ.setdefault("HF_HOME", str(cache_dir / "huggingface"))
        os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))
        # Force offline mode for Hugging Face Hub and transformers
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    def shutdown(self) -> None:
        self._backup_databases()
        self._stop_mobile()
        with contextlib.suppress(Exception):
            if self.web_api_server is not None:
                self.web_api_server.stop()
        if self._llama_started:
            with contextlib.suppress(Exception):
                stop_llama_server()
            self._llama_started = False
        with contextlib.suppress(Exception):
            shutdown_telemetry()
        with contextlib.suppress(Exception):
            reset_container()

    def _backup_databases(self) -> None:
        settings = self.settings
        if getattr(settings, "backup_enabled", True) is False:
            return
        if _SKIP_BACKUP_UNDER_PYTEST and "pytest" in sys.modules:
            return
        for json_file in (settings.inventory_file, settings.memorias_file):
            with contextlib.suppress(sqlite3.Error, OSError):
                backup_database(db_path_for(json_file), keep=DEFAULT_BACKUP_KEEP)

    def _bootstrap_logging(self, settings: Settings) -> None:
        enable_faulthandler(settings.logs_dir / "fault.log")
        setup_logging(
            level=settings.telemetry.log_level.value,
            log_file=str(settings.logs_dir / "celsius.log"),
        )
        _import_optional("edge_tts")
        _import_optional("sentence_transformers")
        _import_optional("transformers")
        if settings.telemetry.enabled:
            if settings.customer.local_offline_required:
                logger.warning(
                    "Telemetria nao inicializada: modo local/offline obrigatorio — "
                    "nenhum dado sai desta maquina."
                )
            else:
                init_telemetry(
                    service_name=settings.telemetry.service_name,
                    service_version=VERSION,
                    otlp_endpoint=settings.telemetry.otlp_endpoint,
                    sample_rate=settings.telemetry.sample_rate,
                    log_level=settings.telemetry.log_level.value,
                )
        get_container()

    def _start_decision_layer(self, settings: Settings) -> None:
        """Start the already-installed local KEV supervisor when configured."""
        decision = settings.decision
        if not decision.enabled or decision.provider != "local" or not decision.auto_start:
            return
        if "pytest" in sys.modules:
            return
        root = Path(__file__).resolve().parents[1]
        supervisor = root / "scripts" / "kev-supervisor.ps1"
        kev_python = root / "kev-venv" / "Scripts" / "python.exe"
        if not supervisor.is_file() or not kev_python.is_file():
            logger.warning(
                "JEV/KEV habilitado, mas o runtime ainda nao foi preparado. "
                "Execute scripts\\kev-server.ps1 -NoStart."
            )
            return
        port = 8009
        try:
            parsed = urlsplit(decision.base_url)
            port = parsed.port or 8009
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(supervisor),
                    "-Action",
                    "Start",
                    "-Port",
                    str(port),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=12,
                creationflags=flags,
                check=False,
            )
            if result.returncode == 0:
                self.report("Supervisor local JEV/KEV iniciado.")
            else:
                logger.warning("Falha ao iniciar supervisor JEV/KEV: %s", result.stderr.strip())
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            logger.warning("Supervisor JEV/KEV indisponivel: %s", exc)

    def _start_mobile(self, settings: Settings) -> None:
        if not settings.mobile.enabled:
            return
        runtime = get_mobile_runtime()
        token = rotate_mobile_token(settings)
        if token != settings.mobile.pairing_token:
            settings.mobile.pairing_token = token
            with contextlib.suppress(OSError):
                settings.save_local_preferences()
        try:
            server, _https_warning = start_for_settings(
                settings,
                command_callback=runtime.command,
                voice_command_callback=runtime.voice,
            )
            runtime.attach(server)
            self.report("Acesso pelo celular disponivel.")
        except Exception as exc:
            logger.warning(
                "Nao foi possivel iniciar o acesso movel durante a inicializacao: %s", exc
            )

    def _stop_mobile(self) -> None:
        if not self.settings.mobile.enabled:
            return
        with contextlib.suppress(Exception):
            get_mobile_runtime().close()

    def _log_hardware(self, settings: Settings) -> None:
        if not settings.hardware.auto_detect:
            return
        try:
            from core.hardware import detect_hardware
            from core.model_selector import select_optimal_model

            profile = detect_hardware()
            recommendation = select_optimal_model(profile)
            logger.info("Hardware detected: %s", recommendation.profile.summary)
            logger.info("Modelo recomendado: %s", recommendation.main_model_id)
            logger.info("Modelo ativo: %s", settings.model.llm_model)
        except Exception as exc:
            logger.warning("Deteccao de hardware falhou: %s", exc)

    def _preload_embeddings(self, features) -> None:
        if features.multi_agent:
            self.report("Preparando memoria semantica...")
            try:
                from ai.agents import preload_embedding_model
                from ai.tool_retrieval import preload_tool_embeddings

                preload_embedding_model()
                # Shares the encoder loaded just above; only the static tool
                # vectors are new, so the first chat turn starts warm.
                preload_tool_embeddings()
            except Exception as exc:
                logger.warning("Falha ao pre-carregar modelo de embeddings: %s", exc)

    def _preload_whisper(self, features) -> None:
        if not features.voice_input:
            return
        try:

            def _preload() -> None:
                try:
                    from workers.mic_worker import preload_whisper_model

                    preload_whisper_model()
                except Exception as exc:
                    logger.warning("Falha ao pre-carregar Whisper em background: %s", exc)

            self._whisper_thread = threading.Thread(target=_preload, daemon=True)
            self._whisper_thread.start()
        except Exception as exc:
            logger.warning("Falha ao iniciar preloader do Whisper: %s", exc)

    def _prepare_model(self, settings: Settings) -> bool:
        from core.config import get_model_by_id

        model_path = settings.get_model_path(settings.model.llm_model)
        model = get_model_by_id(settings.model.llm_model)
        needs_model = not model_path.exists()
        needs_mmproj = bool(
            model
            and model.has_mmproj
            and settings.get_mmproj_path(settings.model.llm_model) is None
        )
        if needs_model or needs_mmproj:
            if self._confirm_download is None or not self._confirm_download(settings, model):
                self.failure_message = (
                    "O modelo local nao esta instalado e o download nao foi autorizado."
                )
                return False
            self.report("Preparando download do modelo...")

        self.report("Verificando o modelo local...")
        _ensure_model_available(settings, fn_status=self.report)
        self.report("Carregando a inteligencia artificial local...")
        from core.model_router import model_start_kwargs

        start_kwargs = model_start_kwargs(settings.model.llm_model)
        if not start_llama_server(
            model_id=settings.model.llm_model,
            n_gpu_layers=start_kwargs.get("n_gpu_layers", settings.model.n_gpu_layers),
            n_ctx=start_kwargs.get("n_ctx", settings.model.num_ctx),
            n_batch=settings.model.n_batch,
            n_threads=settings.model.n_threads,
        ):
            self.failure_message = (
                "Nao foi possivel iniciar o modelo local (llama.cpp).\n"
                "Verifique se o arquivo GGUF existe na pasta resources/."
            )
            return False
        self._llama_started = True
        return True

    def _start_web_server(self, settings: Settings) -> None:
        self.report("Iniciando interface web local...")
        try:
            from core.web_api.server import LocalWebApiServer

            server = LocalWebApiServer(settings=settings)
            if server.start():
                self.web_api_server = server
        except Exception as exc:
            logger.warning("A API web local nao foi iniciada: %s", exc)
            self.web_api_server = None
