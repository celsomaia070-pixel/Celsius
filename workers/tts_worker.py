import asyncio
import contextlib
import gc
import logging
import os
import queue
import tempfile
import threading
from pathlib import Path

import pygame
from PySide6.QtCore import QThread, Signal

from core.settings import get_settings
from core.tts import (
    TTS_PLAYBACK_POLL_MS,
    TTSVoiceConfig,
    create_tts_provider,
    friendly_tts_error,
    naturalize_tts_text,
    soften_streaming_boundary,
    split_tts_fast_start,
)

logger = logging.getLogger(__name__)


class VozWorker(QThread):
    erro_tts = Signal(str)
    audio_ready = Signal(bytes, str)
    finished = Signal()

    def __init__(self, texto: str, *, force_enabled: bool = False, streaming: bool = False):
        super().__init__()
        settings = get_settings().voice
        self.texto = naturalize_tts_text(texto)
        self._provider = create_tts_provider(
            TTSVoiceConfig(
                voice=settings.voice,
                rate=settings.rate,
                pitch=settings.pitch,
                volume=settings.volume,
                provider=settings.provider,
            )
        )
        self._arquivo_voz: str | None = None
        self._should_stop = False
        self._voice_enabled = settings.enabled or force_enabled
        self._max_playback_ms = settings.max_playback_ms
        self._streaming = streaming
        self._stream_closed = threading.Event()
        self._input_queue: queue.Queue[tuple[str, bool] | None] = queue.Queue()
        if self._streaming and self.texto:
            self._input_queue.put((self.texto, False))

    def run(self):
        gc.disable()
        try:
            if (
                (not self.texto and not self._streaming)
                or self._should_stop
                or not self._voice_enabled
            ):
                return

            loop = None
            try:
                logger.debug("Starting TTS for: %s", self.texto[:50])

                if self._streaming:
                    self._generate_and_play_stream()
                else:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._generate_and_play_segments())
                self.finished.emit()
            except Exception as e:
                logger.exception("Erro ao gerar TTS: %s", e)
                self._cleanup()
                if not self._should_stop:
                    self.erro_tts.emit(friendly_tts_error(e))
                self.finished.emit()
            finally:
                if loop and not loop.is_closed():
                    loop.close()
        finally:
            gc.enable()
            self._cleanup()

    async def _generate_and_play_segments(self):
        segments = self._speech_segments()
        if not segments:
            return
        generated_any = False
        for index, segment in enumerate(segments):
            if self._should_stop:
                break
            speech = soften_streaming_boundary(
                segment,
                continuation=index < len(segments) - 1,
            )
            audio = await self._provider.synthesize(speech)
            if self._should_stop:
                break
            generated_any = True
            self.audio_ready.emit(audio, "audio/mpeg")
            self._write_segment_audio(audio)
            self._reproduzir()
        if not generated_any and not self._should_stop:
            raise RuntimeError("O TTS nao retornou audio para esta resposta.")

    def _speech_segments(self) -> list[str]:
        return split_tts_fast_start(self.texto)

    def _generate_and_play_stream(self):
        audio_queue: queue.Queue[tuple[bytes, str] | Exception | None] = queue.Queue(maxsize=3)

        def synthesize_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                while not self._should_stop:
                    item = self._input_queue.get()
                    if item is None:
                        break
                    text, continuation = item
                    segments = split_tts_fast_start(text)
                    for index, segment in enumerate(segments):
                        if self._should_stop:
                            break
                        speech = soften_streaming_boundary(
                            segment,
                            continuation=continuation or index < len(segments) - 1,
                        )
                        audio = loop.run_until_complete(self._provider.synthesize(speech))
                        audio_queue.put((audio, "audio/mpeg"))
            except Exception as exc:
                audio_queue.put(exc)
            finally:
                audio_queue.put(None)
                loop.close()

        synth_thread = threading.Thread(
            target=synthesize_loop,
            name="CelsiusTTSStream",
            daemon=True,
        )
        synth_thread.start()

        while not self._should_stop:
            item = audio_queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            audio, mime_type = item
            self.audio_ready.emit(audio, mime_type)
            self._write_segment_audio(audio)
            self._reproduzir()

        self._stream_closed.set()
        synth_thread.join(timeout=1)

    def _write_segment_audio(self, audio: bytes):
        self._cleanup()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp:
            self._arquivo_voz = temp.name
        Path(self._arquivo_voz).write_bytes(audio)

    def _reproduzir(self):
        if self._should_stop or not self._arquivo_voz or not os.path.exists(self._arquivo_voz):
            return

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(self._arquivo_voz)
            pygame.mixer.music.play()
            elapsed = 0
            while pygame.mixer.music.get_busy() and not self._should_stop:
                self.msleep(TTS_PLAYBACK_POLL_MS)
                elapsed += TTS_PLAYBACK_POLL_MS
                if elapsed > self._max_playback_ms:
                    logger.warning("Playback TTS excedeu o limite e sera interrompido")
                    break
            pygame.mixer.music.unload()
        except Exception as e:
            logger.exception("Erro ao reproduzir TTS: %s", e)
            if not self._should_stop:
                self.erro_tts.emit(str(e))
        finally:
            self._cleanup()

    def _cleanup(self):
        if self._arquivo_voz and os.path.exists(self._arquivo_voz):
            with contextlib.suppress(Exception):
                os.remove(self._arquivo_voz)
        self._arquivo_voz = None

    def stop(self):
        self._should_stop = True
        if self._streaming:
            self._stream_closed.set()
            self._input_queue.put(None)
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
        self._cleanup()
        self.quit()
        self.wait(1000)

    def enqueue_text(self, text: str, *, continuation: bool = True):
        cleaned = naturalize_tts_text(text)
        if not self._streaming or self._should_stop or self._stream_closed.is_set() or not cleaned:
            return
        self._input_queue.put((cleaned, continuation))

    def finish_stream(self):
        if not self._streaming or self._stream_closed.is_set():
            return
        self._stream_closed.set()
        self._input_queue.put(None)
