import asyncio
import contextlib
import gc
import logging
import os
import tempfile
from pathlib import Path

import pygame
from PySide6.QtCore import QThread, Signal

from core.settings import get_settings
from core.tts import (
    EDGE_TTS_SINGLE_PASS_LIMIT,
    EdgeTTSProvider,
    TTSVoiceConfig,
    friendly_tts_error,
    naturalize_tts_text,
    split_tts_text,
)

logger = logging.getLogger(__name__)


class VozWorker(QThread):
    erro_tts = Signal(str)
    audio_ready = Signal(bytes, str)
    finished = Signal()

    def __init__(self, texto: str, *, force_enabled: bool = False):
        super().__init__()
        settings = get_settings().voice
        self.texto = naturalize_tts_text(texto)
        self._provider = EdgeTTSProvider(
            TTSVoiceConfig(
                voice=settings.voice,
                rate=settings.rate,
                pitch=settings.pitch,
                volume=settings.volume,
            )
        )
        self._arquivo_voz: str | None = None
        self._should_stop = False
        self._voice_enabled = settings.enabled or force_enabled
        self._max_playback_ms = settings.max_playback_ms

    def run(self):
        gc.disable()
        try:
            if not self.texto or self._should_stop or not self._voice_enabled:
                return

            loop = None
            try:
                logger.debug("Starting TTS for: %s", self.texto[:50])

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
        for segment in segments:
            if self._should_stop:
                break
            audio = await self._provider.synthesize(segment)
            if self._should_stop:
                break
            generated_any = True
            self.audio_ready.emit(audio, "audio/mpeg")
            self._write_segment_audio(audio)
            self._reproduzir()
        if not generated_any and not self._should_stop:
            raise RuntimeError("O TTS nao retornou audio para esta resposta.")

    def _speech_segments(self) -> list[str]:
        if len(self.texto) <= EDGE_TTS_SINGLE_PASS_LIMIT:
            return [self.texto]
        return split_tts_text(self.texto)

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
                self.msleep(200)
                elapsed += 200
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
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
        self._cleanup()
        self.quit()
        self.wait(1000)
