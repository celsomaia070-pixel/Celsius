"""Real QThreads/signals/SDL decoding, with a deterministic offline WAV provider."""

import gc
import io
import threading
import wave
from pathlib import Path
from unittest.mock import patch


def _wave():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    return output.getvalue()


class OfflineProvider:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail
        self.audio = _wave()

    async def synthesize(self, text):
        self.calls.append((text, threading.get_ident()))
        if self.fail:
            raise RuntimeError("offline synthesis fixture failure")
        return self.audio


def _exercise(mode):
    import pygame
    from PySide6.QtCore import QCoreApplication, Qt

    import workers.tts_worker as production
    from core.settings import get_settings

    app = QCoreApplication.instance() or QCoreApplication([])
    settings = get_settings()
    settings.voice.enabled = mode != "disabled"
    provider = OfflineProvider(fail=mode == "provider_error")
    chunks, errors, finished, played = [], [], [], []
    streaming = mode in {"streaming", "cancel"}
    main_thread = threading.get_ident()
    real_play = pygame.mixer.music.play

    def observe_play(*args, **kwargs):
        real_play(*args, **kwargs)
        played.append(pygame.mixer.music.get_busy())

    # Exercise native SDL decoding without network or physical speakers.
    with (
        patch.object(production, "create_tts_provider", return_value=provider),
        patch.object(pygame.mixer.music, "play", side_effect=observe_play),
    ):
        worker = production.VozWorker(
            "" if streaming else "Local smoke audio.", streaming=streaming
        )
        worker.audio_ready.connect(
            lambda *args: chunks.append(args), Qt.ConnectionType.DirectConnection
        )
        worker.erro_tts.connect(errors.append, Qt.ConnectionType.DirectConnection)
        worker.finished.connect(lambda: finished.append(True), Qt.ConnectionType.DirectConnection)
        if mode == "streaming":
            worker.enqueue_text("First local segment.", continuation=True)
            worker.enqueue_text("Second local segment.", continuation=False)
            worker.finish_stream()
        try:
            worker.start()
            if mode == "cancel":
                # An empty input stream is blocked on its queue until stop posts the sentinel.
                worker.stop()
            assert worker.wait(10000), "TTS QThread failed to finish"
            app.processEvents()
            assert not worker.isRunning()
            assert gc.isenabled()
            assert worker._arquivo_voz is None
            assert not list(Path.cwd().glob("*.mp3")), "TTS temporary audio leaked"
            if mode in {"disabled", "cancel"}:
                assert not provider.calls and not chunks and not played and not errors
            elif mode == "provider_error":
                assert provider.calls and errors and finished
                assert not chunks and not played
            else:
                count = 2 if streaming else 1
                assert len(provider.calls) == len(chunks) == len(played) == count
                assert all(thread_id != main_thread for _, thread_id in provider.calls)
                assert all(audio == provider.audio for audio, _ in chunks)
                assert all(played), "Native SDL playback never became active"
                assert not errors, errors
                assert finished
                assert pygame.mixer.get_init()
                assert not pygame.mixer.music.get_busy()
            assert not any(
                t.name == "CelsiusTTSStream" and t.is_alive() for t in threading.enumerate()
            )
        finally:
            worker.stop()
            worker.wait(3000)
            pygame.mixer.quit()


def playback():
    _exercise("playback")


def streaming():
    _exercise("streaming")


def provider_error():
    _exercise("provider_error")


def disabled():
    _exercise("disabled")


def cancel():
    _exercise("cancel")
