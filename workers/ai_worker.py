import contextlib
import gc
import logging
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ai.engine import gerar_resposta, gerar_resposta_com_imagem
from core.chat_attachments import prepare_prompt_attachments

logger = logging.getLogger(__name__)

_AI_GENERATION_LOCK = threading.Lock()


class WorkerSignals(QObject):
    """Signals for worker communication."""

    finished = Signal(str)
    status = Signal(str)
    step = Signal(object)
    chunk = Signal(str)
    error = Signal(str)
    suggestion = Signal(str)


class AIWorker(QRunnable):
    """QRunnable for AI responses using thread pool."""

    def __init__(
        self,
        prompt_dict: dict,
        fn_status: Callable[[str], None] | None = None,
        fn_step: Callable[[object], None] | None = None,
        fn_chunk: Callable[[str], None] | None = None,
        fn_suggestion: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self.setAutoDelete(False)
        self.prompt_dict = prompt_dict
        self.signals = WorkerSignals()

        self._fn_status = fn_status
        self._fn_step = fn_step
        self._fn_chunk = fn_chunk

        if fn_status:
            self.signals.status.connect(fn_status)
        if fn_step:
            self.signals.step.connect(fn_step)
        if fn_chunk:
            self.signals.chunk.connect(fn_chunk)
        if fn_suggestion:
            self.signals.suggestion.connect(fn_suggestion)

    @Slot()
    def run(self):
        started_at = time.perf_counter()
        if not _AI_GENERATION_LOCK.acquire(blocking=False):
            with contextlib.suppress(RuntimeError):
                self.signals.error.emit(
                    "Ja existe uma resposta em andamento. Aguarde ela terminar antes de enviar outra pergunta."
                )
            return

        gc.disable()
        try:
            self.signals.status.emit("Preparando sua mensagem...")
            attachments_started_at = time.perf_counter()
            self._prepare_attachments()
            attachments_seconds = time.perf_counter() - attachments_started_at
            generation_started_at = time.perf_counter()
            if self.prompt_dict.get("caminho_imagem"):
                resposta = gerar_resposta_com_imagem(
                    self.prompt_dict["caminho_imagem"],
                    self.prompt_dict.get("pergunta", ""),
                    fn_status=self.signals.status.emit,
                    fn_chunk=self.signals.chunk.emit,
                )
            else:
                resposta = gerar_resposta(
                    self.prompt_dict,
                    fn_status=self.signals.status.emit,
                    fn_passo=self.signals.step.emit,
                    fn_chunk=self.signals.chunk.emit,
                )
            generation_seconds = time.perf_counter() - generation_started_at
            logger.info(
                "Desempenho da resposta: anexos=%.2fs geracao=%.2fs total=%.2fs",
                attachments_seconds,
                generation_seconds,
                time.perf_counter() - started_at,
            )
            self.signals.finished.emit(resposta)
            self._emit_slow_model_suggestion(resposta, generation_seconds)
        except Exception as e:
            logger.exception(
                "Falha na resposta apos %.2fs",
                time.perf_counter() - started_at,
            )
            with contextlib.suppress(RuntimeError):
                self.signals.error.emit(str(e))
            with contextlib.suppress(RuntimeError):
                self.signals.finished.emit(f"Erro: {e}")
        finally:
            gc.enable()
            _AI_GENERATION_LOCK.release()

    def _prepare_attachments(self) -> None:
        from core.settings import get_settings

        prepare_prompt_attachments(
            self.prompt_dict,
            settings=get_settings(),
            fn_status=self.signals.status.emit,
        )

    def _emit_slow_model_suggestion(self, resposta: str, generation_seconds: float) -> None:
        """Emit a lighter-model suggestion when the response was too slow."""
        if not resposta:
            return
        try:
            from core.model_router import get_multi_model_manager
            from core.settings import get_settings
            from core.slow_model_suggestion import (
                estimate_output_tokens,
                suggest_lighter_model,
                suggestions_enabled,
            )

            settings = get_settings()
            if not suggestions_enabled(settings):
                return

            decision = get_multi_model_manager().get_last_decision()
            used_model_id = decision.model_id if decision else None
            if not used_model_id:
                used_model_id = self.prompt_dict.get("modelo_solicitado") or ""
            if not used_model_id:
                return

            from core.hardware import estimate_tokens_per_sec, get_detected_profile

            expected_tps = estimate_tokens_per_sec(used_model_id, get_detected_profile())

            suggestion = suggest_lighter_model(
                used_model_id=used_model_id,
                elapsed_seconds=generation_seconds,
                estimated_output_tokens=estimate_output_tokens(resposta),
                expected_tokens_per_sec=expected_tps,
                resources_dir=settings.get_resources_dir(),
            )
            if suggestion:
                self.signals.suggestion.emit(suggestion.message)
        except Exception as exc:
            logger.debug("Nao foi possivel avaliar lentidao do modelo: %s", exc)


class WorkerManager:
    """Manages thread pool and workers."""

    def __init__(self, max_threads: int = 1):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max_threads)
        self._active_workers: list[AIWorker] = []

    def is_busy(self) -> bool:
        return bool(self._active_workers)

    def submit_ai_task(
        self,
        prompt_dict: dict,
        on_finished: Callable[[str], None],
        on_status: Callable[[str], None] | None = None,
        on_step: Callable[[object], None] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_suggestion: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> AIWorker:
        """Submit an AI task to the thread pool."""
        if self.is_busy():
            raise RuntimeError("Ja existe uma resposta de IA em andamento.")

        worker = AIWorker(
            prompt_dict,
            fn_status=on_status,
            fn_step=on_step,
            fn_chunk=on_chunk,
            fn_suggestion=on_suggestion,
        )
        worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        worker.signals.finished.connect(lambda _: self._cleanup_worker(worker))
        worker.signals.error.connect(lambda _: self._cleanup_worker(worker))

        self._active_workers.append(worker)
        self.pool.start(worker)
        return worker

    def _cleanup_worker(self, worker: AIWorker) -> None:
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def cancel_all(self) -> None:
        for worker in self._active_workers:
            worker.setAutoDelete(True)
        self.pool.clear()
        self._active_workers.clear()

    def wait_for_done(self, msecs: int = -1) -> bool:
        return self.pool.waitForDone(msecs)
