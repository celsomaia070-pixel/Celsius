import contextlib
import gc
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ai.engine import gerar_resposta, gerar_resposta_com_imagem


class WorkerSignals(QObject):
    """Signals for worker communication."""

    finished = Signal(str)
    status = Signal(str)
    step = Signal(object)
    chunk = Signal(str)
    error = Signal(str)


class AIWorker(QRunnable):
    """QRunnable for AI responses using thread pool."""

    def __init__(
        self,
        prompt_dict: dict,
        fn_status: Callable[[str], None] | None = None,
        fn_step: Callable[[object], None] | None = None,
        fn_chunk: Callable[[str], None] | None = None,
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

    @Slot()
    def run(self):
        gc.disable()
        try:
            self._prepare_attachments()
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
            self.signals.finished.emit(resposta)
        except Exception as e:
            with contextlib.suppress(RuntimeError):
                self.signals.error.emit(str(e))
            with contextlib.suppress(RuntimeError):
                self.signals.finished.emit(f"Erro: {e}")
        finally:
            gc.enable()

    def _prepare_attachments(self) -> None:
        attachments = self.prompt_dict.pop("anexos", []) or []
        if not attachments:
            return

        from core.settings import get_settings
        from processors import processar_arquivo

        settings = get_settings()
        doc_parts = []
        existing_doc = self.prompt_dict.get("documento", "").strip()
        if existing_doc:
            doc_parts.append(existing_doc)

        doc_names = []
        first_image = ""
        for file_path, file_name in attachments:
            path = Path(file_path)
            suffix = path.suffix.lower()
            if suffix in settings.image_extensions and not first_image:
                first_image = str(path)
                continue

            try:
                processed = processar_arquivo(str(path), base_dir=path.parent)
            except Exception as exc:
                processed = f"Erro ao processar anexo '{file_name}': {exc}"
            doc_names.append(file_name)
            doc_parts.append(f"### Anexo: {file_name}\n{processed}")

        if first_image and not doc_parts:
            self.prompt_dict["caminho_imagem"] = first_image
        elif first_image:
            doc_parts.append(f"### Imagem anexada\nCaminho: {first_image}")

        if doc_parts:
            self.prompt_dict["documento"] = "\n\n".join(doc_parts)
            if doc_names:
                self.prompt_dict["nome_documento"] = ", ".join(doc_names)
            if doc_names:
                self.prompt_dict["caminho_documento"] = "; ".join(
                    str(Path(path)) for path, _name in attachments
                )


class WorkerManager:
    """Manages thread pool and workers."""

    def __init__(self, max_threads: int = 4):
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max_threads)
        self._active_workers: list[AIWorker] = []

    def submit_ai_task(
        self,
        prompt_dict: dict,
        on_finished: Callable[[str], None],
        on_status: Callable[[str], None] | None = None,
        on_step: Callable[[object], None] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> AIWorker:
        """Submit an AI task to the thread pool."""
        worker = AIWorker(
            prompt_dict,
            fn_status=on_status,
            fn_step=on_step,
            fn_chunk=on_chunk,
        )
        worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        worker.signals.finished.connect(lambda _: self._cleanup_worker(worker))

        self._active_workers.append(worker)
        self.pool.start(worker)
        return worker

    def _cleanup_worker(self, worker: AIWorker):
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def cancel_all(self):
        for worker in self._active_workers:
            worker.setAutoDelete(True)
        self.pool.clear()
        self._active_workers.clear()

    def wait_for_done(self, msecs: int = -1) -> bool:
        return self.pool.waitForDone(msecs)
