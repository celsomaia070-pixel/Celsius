import queue
import traceback

import numpy as np
import sounddevice as sd
import whisper
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.config import get_settings

# Singleton for whisper model - shared across all MicWorker instances
_whisper_model = None


class MicWorkerSignals(QObject):
    recognized = Signal(str)
    error = Signal(str)


class MicWorker(QRunnable):
    """QRunnable for microphone recording and recognition using local Whisper.
    Passes numpy array directly to whisper (no ffmpeg needed)."""

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.fs = 16000
        self.dados_audio = queue.Queue()
        self.rodando = True
        self._lock_stream = None
        self.signals = MicWorkerSignals()

    def _get_model(self):
        global _whisper_model
        if _whisper_model is None:
            model_name = self.settings.whisper_model
            print(f"[MIC] Carregando modelo Whisper: {model_name}")
            _whisper_model = whisper.load_model(model_name)
            print(f"[MIC] Modelo Whisper carregado com sucesso")
        return _whisper_model

    def callback_audio(self, indata, frames, time, status):
        if self.rodando:
            self.dados_audio.put(indata.copy())

    @Slot()
    def run(self):
        lista_frames = []
        try:
            device = sd.default.device[0]
            info = sd.query_devices(device)
            print(f"[MIC] Usando dispositivo: {info['name']}")

            self._lock_stream = sd.InputStream(
                device=device,
                samplerate=self.fs, channels=1, dtype="int16",
                callback=self.callback_audio
            )
            self._lock_stream.start()

            while self.rodando:
                try:
                    dados = self.dados_audio.get(timeout=0.2)
                    lista_frames.append(dados)
                except queue.Empty:
                    continue

        except Exception as e:
            print(f"[MIC] ERRO: {e}")
            traceback.print_exc()
            self.signals.error.emit(f"Erro ao acessar microfone: {e}")
            return
        finally:
            if self._lock_stream:
                try:
                    self._lock_stream.stop()
                    self._lock_stream.close()
                except Exception:
                    pass
                self._lock_stream = None

        if not lista_frames:
            print("[MIC] Nenhum audio capturado")
            self.signals.error.emit("Nenhum audio capturado.")
            return

        gravacao_total = np.concatenate(lista_frames, axis=0)
        print(f"[MIC] Audio capturado, shape: {gravacao_total.shape}")

        min_samples = int(self.fs * 1.0)
        if len(gravacao_total) < min_samples:
            self.signals.error.emit("Audio muito curto. Fale por mais tempo.")
            return

        try:
            audio_float32 = gravacao_total.flatten().astype(np.float32) / 32768.0

            max_vol = np.max(np.abs(audio_float32))
            if max_vol < 0.005:
                self.signals.error.emit("Audio muito silencioso. Fale mais alto.")
                return
            if max_vol > 0.01:
                audio_float32 = audio_float32 / max_vol * 0.8

            model = self._get_model()
            import torch
            audio_tensor = torch.from_numpy(audio_float32)

            print("[MIC] Iniciando transcrição Whisper...")
            result = model.transcribe(
                audio_tensor,
                language="pt",
                fp16=False,
                condition_on_previous_text=False,
                no_speech_threshold=0.3,
                logprob_threshold=-1.0,
            )
            texto = result["text"].strip()
            print(f"[MIC] Transcrição: '{texto}'")
            if texto and len(texto) > 1:
                self.signals.recognized.emit(texto)
            else:
                self.signals.error.emit("Nao entendi o audio. Tente falar mais alto e claro.")

        except Exception as e:
            print(f"[MIC] ERRO reconhecimento: {e}")
            traceback.print_exc()
            self.signals.error.emit(f"Erro ao reconhecer audio: {e}")

    def stop(self):
        self.rodando = False
        if self._lock_stream:
            try:
                self._lock_stream.stop()
                self._lock_stream.close()
            except Exception:
                pass
            self._lock_stream = None
