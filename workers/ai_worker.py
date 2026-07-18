from collections.abc import Callable

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
        try:
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
            try:
                self.signals.error.emit(str(e))
            except RuntimeError:
                pass
            try:
                self.signals.finished.emit(f"Erro: {e}")
            except RuntimeError:
                pass


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
            pass
        self.pool.clear()
        self._active_workers.clear()

    def wait_for_done(self, msecs: int = -1) -> bool:
        return self.pool.waitForDone(msecs)
