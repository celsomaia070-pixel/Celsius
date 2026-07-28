"""
WorkerController - Gerencia workers de IA e processamento assíncrono.
"""

from PySide6.QtCore import QObject, QThreadPool, Signal

from workers.ai_worker import WorkerManager
from workers.mic_worker import MicWorker
from workers.tts_worker import VozWorker


class WorkerController(QObject):
    """Controller para workers de IA."""

    ai_response_started = Signal()
    ai_response_token = Signal(str)
    ai_response_finished = Signal(str)
    ai_response_error = Signal(str)
    ai_status_update = Signal(str)
    model_loaded = Signal(str)
    model_load_error = Signal(str)
    model_list_loaded = Signal(list)
    mic_ready = Signal()
    mic_error = Signal(str)
    voice_text_ready = Signal(str)
    voice_error = Signal(str)
    voice_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker_manager = WorkerManager()
        self._mic_worker = None
        self._voz_worker = None

    def send_message(
        self,
        message: str,
        system_prompt: str = "",
        conversation_history: list = None,
        memories: list = None,
        model_name: str = None,
        attachments: list = None,
    ):
        """Envia mensagem para IA."""
        self.ai_response_started.emit()

        doc_parts = []
        if conversation_history:
            for h in conversation_history[-10:]:
                role = "Usuário" if h["role"] == "user" else "Assistente"
                doc_parts.append(f"{role}: {h['content']}")
        if memories:
            mem_texts = [m.get("text", str(m)) if isinstance(m, dict) else str(m) for m in memories]
            doc_parts.append("Memórias relevantes:\n" + "\n".join(mem_texts))

        prompt_dict = {
            "pergunta": message,
            "documento": "\n\n".join(doc_parts) if doc_parts else "",
            "nome_documento": "",
            "anexos": attachments or [],
            "modelo_solicitado": model_name or "",
        }

        self.worker_manager.submit_ai_task(
            prompt_dict=prompt_dict,
            on_finished=self._on_finished,
            on_status=self.ai_status_update.emit,
            on_chunk=self._on_token,
            on_error=self._on_error,
        )

    def _on_token(self, token: str):
        self.ai_response_token.emit(token)

    def _on_finished(self, full_text: str):
        self.ai_response_finished.emit(full_text)

    def _on_error(self, error: str):
        self.ai_response_error.emit(error)

    def load_models(self):
        """Carrega lista de modelos (placeholder)."""
        pass

    def pull_model(self, model_name: str):
        """Baixa um modelo (placeholder)."""
        pass

    def load_model(self, model_name: str):
        """Carrega modelo na memória (placeholder)."""
        pass

    def start_mic(self):
        """Inicia gravação de microfone."""
        self._mic_worker = MicWorker()
        self._mic_worker.signals.recognized.connect(self.voice_text_ready.emit)
        self._mic_worker.signals.error.connect(self.mic_error.emit)
        self._mic_worker.signals.started.connect(self.mic_ready.emit)
        QThreadPool.globalInstance().start(self._mic_worker)

    def stop_mic(self) -> str:
        """Para gravação e retorna texto."""
        if self._mic_worker:
            self._mic_worker.stop()
            return ""
        return ""

    def start_voice(self, text: str):
        """Inicia síntese de voz (TTS) com o texto dado."""
        if self._voz_worker and self._voz_worker.isRunning():
            self._voz_worker.stop()
        self._voz_worker = VozWorker(text)
        self._voz_worker.erro_tts.connect(self.voice_error.emit)
        self._voz_worker.finished.connect(self.voice_finished.emit)
        self._voz_worker.start()

    def stop_voice(self):
        """Para síntese de voz."""
        if self._voz_worker and self._voz_worker.isRunning():
            self._voz_worker.stop()

    def process_file(self, file_path: str, on_finished=None, on_error=None):
        """Processa arquivo em background (placeholder)."""
        pass

    def cleanup(self):
        """Limpa todos os workers."""
        self.worker_manager.cancel_all()
