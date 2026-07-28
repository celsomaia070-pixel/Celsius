import gc
import os
import queue
import time
import traceback

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.config import get_settings

# Singleton for faster-whisper model
_whisper_model = None

# Otimizar threads CPU
os.environ["CT2_INTER_THREADS"] = "4"
os.environ["CT2_INTRA_THREADS"] = "4"


class MicWorkerSignals(QObject):
    recognized = Signal(str)
    error = Signal(str)
    started = Signal()


class MicWorker(QRunnable):
    """QRunnable for microphone recording using faster-whisper (CTranslate2)."""

    MAX_DURATION_SECONDS = 30

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.fs = 16000
        self.dados_audio = queue.Queue()
        self.rodando = True
        self._lock_stream = None
        self.signals = MicWorkerSignals()
        self._start_time = None

    def _get_model(self):
        global _whisper_model
        if _whisper_model is None:
            model_name = self.settings.whisper_model
            print(f"[MIC] Carregando faster-whisper: {model_name}")
            from faster_whisper import WhisperModel

            _whisper_model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
            )
            print("[MIC] Modelo faster-whisper carregado com sucesso")
        return _whisper_model

    def callback_audio(self, indata, frames, time_info, status):
        if self.rodando:
            self.dados_audio.put(indata.copy())

    @Slot()
    def run(self):
        gc.disable()
        lista_frames = []
        try:
            device = sd.default.device[0]
            info = sd.query_devices(device)
            print(f"[MIC] Usando dispositivo: {info['name']}")

            self._lock_stream = sd.InputStream(
                device=device,
                samplerate=self.fs,
                channels=1,
                dtype="int16",
                callback=self.callback_audio,
            )
            self._lock_stream.start()
            self._start_time = time.time()
            self.signals.started.emit()

            while self.rodando:
                if (
                    self._start_time
                    and (time.time() - self._start_time) > self.MAX_DURATION_SECONDS
                ):
                    print(f"[MIC] Tempo máximo atingido ({self.MAX_DURATION_SECONDS}s)")
                    break

                try:
                    dados = self.dados_audio.get(timeout=0.2)
                    lista_frames.append(dados)
                except queue.Empty:
                    continue

        except Exception as e:
            print(f"[MIC] ERRO: {e}")
            traceback.print_exc()
            self.signals.error.emit(f"Erro ao acessar microfone: {e}")
            gc.enable()
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
            gc.enable()
            return

        gravacao_total = np.concatenate(lista_frames, axis=0)
        print(f"[MIC] Audio capturado, shape: {gravacao_total.shape}")

        min_samples = int(self.fs * 1.0)
        if len(gravacao_total) < min_samples:
            self.signals.error.emit("Audio muito curto. Fale por mais tempo.")
            gc.enable()
            return

        try:
            audio_float32 = gravacao_total.flatten().astype(np.float32) / 32768.0
            audio_original = audio_float32.copy()

            # Gate de ruído: zera apenas frames MUITO silenciosos
            frame_size = int(self.fs * 0.02)
            for i in range(0, len(audio_float32), frame_size):
                frame = audio_float32[i : i + frame_size]
                if len(frame) > 0 and np.max(np.abs(frame)) < 0.001:
                    audio_float32[i : i + frame_size] = 0.0

            # Remover silêncio do início e fim
            threshold = 0.005
            non_silent = np.where(np.abs(audio_float32) > threshold)[0]
            if len(non_silent) > 10:
                start = max(0, non_silent[0] - int(self.fs * 0.1))
                end = min(len(audio_float32), non_silent[-1] + int(self.fs * 0.1))
                audio_float32 = audio_float32[start:end]

            # Garantir que não ficou vazio
            if len(audio_float32) < int(self.fs * 0.5):
                audio_float32 = audio_original

            max_vol = np.max(np.abs(audio_float32))
            if max_vol < 0.005:
                self.signals.error.emit("Audio muito silencioso. Fale mais alto.")
                gc.enable()
                return

            audio_float32 = audio_float32 / max_vol * 0.8
            audio_float32 = np.tanh(audio_float32 * 1.2) / np.tanh(np.float32(1.2))
            audio_float32 = audio_float32.astype(np.float32)

            model = self._get_model()

            print("[MIC] Iniciando transcrição faster-whisper...")
            t0 = time.time()
            segments, info = model.transcribe(
                audio_float32,
                language="pt",
                beam_size=3,
                vad_filter=True,
                vad_parameters={
                    "min_silence_duration_ms": 300,
                    "speech_pad_ms": 200,
                },
                initial_prompt="Português do Brasil. Celsius, assistente pessoal.",
                word_timestamps=False,
            )
            texto = " ".join(seg.text.strip() for seg in segments)
            elapsed = time.time() - t0
            print(f"[MIC] Transcrição ({elapsed:.2f}s): '{texto}'")

            if texto and len(texto) > 1:
                self.signals.recognized.emit(texto)
            else:
                self.signals.error.emit("Não entendi o áudio. Tente falar mais alto e claro.")

        except Exception as e:
            print(f"[MIC] ERRO reconhecimento: {e}")
            traceback.print_exc()
            self.signals.error.emit(f"Erro ao reconhecer áudio: {e}")
        finally:
            gc.enable()

    def stop(self):
        self.rodando = False
        if self._lock_stream:
            try:
                self._lock_stream.stop()
                self._lock_stream.close()
            except Exception:
                pass
            self._lock_stream = None


def preload_whisper_model():
    """Pre-load faster-whisper model in background."""
    global _whisper_model
    if _whisper_model is None:
        settings = get_settings()
        model_name = settings.whisper_model
        print(f"[MIC] Pre-carregando faster-whisper: {model_name}")
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
        )
        print("[MIC] Modelo faster-whisper pre-carregado com sucesso")
