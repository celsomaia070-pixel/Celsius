import queue
import traceback

import numpy as np
import sounddevice as sd
import whisper
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.config import get_settings


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
        self._model = None

    def _get_model(self):
        if self._model is None:
            model_name = self.settings.whisper_model
            self._model = whisper.load_model(model_name)
        return self._model

    def callback_audio(self, indata, frames, time, status):
        if self.rodando:
            self.dados_audio.put(indata.copy())

    @Slot()
    def run(self):
        lista_frames = []
        try:
            device = sd.default.device[0]
            info = sd.query_devices(device)
            print(f"[MIC DEBUG] Usando dispositivo: {info['name']}")

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
            print(f"[MIC DEBUG] ERRO: {e}")
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
            print("[MIC DEBUG] Nenhum audio capturado")
            self.signals.error.emit("Nenhum audio capturado.")
            return

        gravacao_total = np.concatenate(lista_frames, axis=0)
        print(f"[MIC DEBUG] Audio captured, shape: {gravacao_total.shape}")

        try:
            audio_float32 = gravacao_total.flatten().astype(np.float32) / 32768.0

            model = self._get_model()
            import torch
            audio_tensor = torch.from_numpy(audio_float32)

            print("[MIC DEBUG] Starting Whisper transcription...")
            result = model.transcribe(
                audio_tensor,
                language="pt",
                fp16=False
            )
            texto = result["text"].strip()
            print(f"[MIC DEBUG] Transcription: '{texto}'")
            if texto:
                self.signals.recognized.emit(texto)
            else:
                self.signals.error.emit("Nao entendi o audio.")

        except Exception as e:
            print(f"[MIC DEBUG] ERRO reconhecimento: {e}")
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
