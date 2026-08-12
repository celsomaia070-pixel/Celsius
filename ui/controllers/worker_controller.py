"""
WorkerController - Gerencia workers de IA e processamento assÃ­ncrono.
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
    mic_level = Signal(float)
    voice_text_ready = Signal(str)
    voice_error = Signal(str)
    voice_audio_ready = Signal(bytes, str)
    voice_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker_manager = WorkerManager()
        self._mic_worker = None
        self._voz_worker = None
        self._ai_busy = False

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
        if self._ai_busy:
            self.ai_status_update.emit("Aguarde a resposta atual terminar...")
            return False

        self._ai_busy = True
        self.ai_response_started.emit()
        self.ai_status_update.emit("Pensando...")

        doc_parts = []
        history = conversation_history or []
        if history:
            self.ai_status_update.emit("Carregando contexto da conversa...")
        if memories:
            mem_texts = [m.get("text", str(m)) if isinstance(m, dict) else str(m) for m in memories]
            doc_parts.append("MemÃ³rias relevantes:\n" + "\n".join(mem_texts))

        if memories:
            self.ai_status_update.emit("Consultando memorias relevantes...")

        if attachments:
            self.ai_status_update.emit("Preparando anexos...")

        prompt_dict = {
            "pergunta": message,
            "documento": "\n\n".join(doc_parts) if doc_parts else "",
            "nome_documento": "",
            "anexos": attachments or [],
            "modelo_solicitado": model_name or "",
            "system_prompt": system_prompt,
            "historico": history,
        }

        try:
            self.worker_manager.submit_ai_task(
                prompt_dict=prompt_dict,
                on_finished=self._on_finished,
                on_status=self.ai_status_update.emit,
                on_chunk=self._on_token,
                on_error=self._on_error,
            )
        except Exception as exc:
            self._ai_busy = False
            self.ai_response_error.emit(str(exc))
            return False
        return True

    def _on_token(self, token: str):
        self.ai_response_token.emit(token)

    def _on_finished(self, full_text: str):
        self._ai_busy = False
        self.ai_response_finished.emit(full_text)

    def _on_error(self, error: str):
        self._ai_busy = False
        self.ai_response_error.emit(error)

    def load_models(self):
        """Carrega lista de modelos (placeholder)."""
        pass

    def pull_model(self, model_name: str):
        """Baixa um modelo (placeholder)."""
        pass

    def load_model(self, model_name: str):
        """Carrega modelo na memÃ³ria (placeholder)."""
        pass

    def start_mic(self):
        """Inicia gravaÃ§Ã£o de microfone."""
        self._mic_worker = MicWorker()
        self._mic_worker.signals.recognized.connect(self.voice_text_ready.emit)
        self._mic_worker.signals.error.connect(self.mic_error.emit)
        self._mic_worker.signals.started.connect(self.mic_ready.emit)
        self._mic_worker.signals.audio_level.connect(self.mic_level.emit)
        QThreadPool.globalInstance().start(self._mic_worker)

    def stop_mic(self) -> str:
        """Para gravaÃ§Ã£o e retorna texto."""
        if self._mic_worker:
            self._mic_worker.stop()
            return ""
        return ""

    def start_voice(self, text: str, *, force_enabled: bool = False):
        """Inicia sÃ­ntese de voz (TTS) com o texto dado."""
        if self._voz_worker and self._voz_worker.isRunning():
            self._voz_worker.stop()
        self._voz_worker = None
        self._voz_worker = VozWorker(text, force_enabled=force_enabled)
        self._voz_worker.erro_tts.connect(self.voice_error.emit)
        self._voz_worker.audio_ready.connect(self.voice_audio_ready.emit)
        self._voz_worker.finished.connect(self.voice_finished.emit)
        self._voz_worker.start()

    def start_voice_stream(self, *, force_enabled: bool = False):
        """Inicia uma sessao continua de voz para receber trechos em fila."""
        if self._voz_worker and self._voz_worker.isRunning():
            self._voz_worker.stop()
        self._voz_worker = VozWorker("", force_enabled=force_enabled, streaming=True)
        self._voz_worker.erro_tts.connect(self.voice_error.emit)
        self._voz_worker.audio_ready.connect(self.voice_audio_ready.emit)
        self._voz_worker.finished.connect(self.voice_finished.emit)
        self._voz_worker.start()

    def enqueue_voice_chunk(self, text: str, *, continuation: bool = True):
        """Adiciona um trecho de fala na sessao continua atual."""
        if self._voz_worker:
            self._voz_worker.enqueue_text(text, continuation=continuation)

    def finish_voice_stream(self):
        """Fecha a entrada da sessao continua apos enfileirar todos os trechos."""
        if self._voz_worker:
            self._voz_worker.finish_stream()

    def stop_voice(self):
        """Para sÃ­ntese de voz."""
        if self._voz_worker and self._voz_worker.isRunning():
            self._voz_worker.stop()

    def process_file(self, file_path: str, on_finished=None, on_error=None):
        """Processa arquivo em background (placeholder)."""
        pass

    def cleanup(self):
        """Limpa todos os workers."""
        self.stop_voice()
        self.worker_manager.cancel_all()
