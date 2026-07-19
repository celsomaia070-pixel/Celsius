import asyncio
import os
import re
import tempfile
import traceback

import pygame
from PySide6.QtCore import QThread, Signal


class VozWorker(QThread):
    erro_tts = Signal(str)

    def __init__(self, texto: str):
        super().__init__()
        self.texto = re.sub(r"[*`#_]", "", texto).strip()
        self._arquivo_voz: str | None = None
        self._should_stop = False

    def run(self):
        if not self.texto or self._should_stop:
            return

        try:
            import edge_tts
            print(f"[TTS DEBUG] Starting TTS for: {self.texto[:50]}")

            temp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            self._arquivo_voz = temp.name
            temp.close()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _gerar():
                communicate = edge_tts.Communicate(self.texto, "pt-BR-AntonioNeural")
                await communicate.save(self._arquivo_voz)

            loop.run_until_complete(_gerar())
            loop.close()
            print(f"[TTS DEBUG] Audio saved to: {self._arquivo_voz}")

            if not self._should_stop:
                self._reproduzir()
        except Exception as e:
            print(f"[TTS] ERRO: {e}")
            traceback.print_exc()
            if not self._should_stop:
                self.erro_tts.emit(str(e))

    def _reproduzir(self):
        if self._should_stop or not self._arquivo_voz or not os.path.exists(self._arquivo_voz):
            return

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(self._arquivo_voz)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self._should_stop:
                self.msleep(200)
            pygame.mixer.music.unload()
        except Exception as e:
            print(f"[TTS] ERRO ao reproduzir: {e}")
            if not self._should_stop:
                self.erro_tts.emit(str(e))
        finally:
            self._cleanup()

    def _cleanup(self):
        if self._arquivo_voz and os.path.exists(self._arquivo_voz):
            try:
                os.remove(self._arquivo_voz)
            except Exception:
                pass
        self._arquivo_voz = None

    def stop(self):
        self._should_stop = True
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
        self._cleanup()
        self.quit()
        self.wait(1000)
