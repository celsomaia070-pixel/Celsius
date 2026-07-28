import contextlib
import os
import tempfile
from pathlib import Path

from core.config import MODELO_WHISPER
from processors.base import ProcessadorArquivo


class ProcessadorAudio(ProcessadorArquivo):
    extensoes_suportadas = [".mp3", ".wav", ".ogg", ".m4a", ".flac"]

    _modelo_whisper = None

    @classmethod
    def _carregar_modelo(cls):
        if cls._modelo_whisper is None:
            import whisper

            cls._modelo_whisper = whisper.load_model(MODELO_WHISPER)
        return cls._modelo_whisper

    @classmethod
    def processar(cls, caminho: str, base_dir: Path | None = None) -> str:
        path = cls._validar_caminho(caminho, base_dir)
        modelo = cls._carregar_modelo()

        caminho_wav = str(path)
        temporario = False

        if path.suffix.lower() != ".wav":
            try:
                from pydub import AudioSegment

                audio = AudioSegment.from_file(str(path))
                audio = audio.set_channels(1).set_frame_rate(16000)

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
                    caminho_wav = temp.name

                audio.export(caminho_wav, format="wav")
                temporario = True
            except Exception as e:
                return f"Erro ao converter audio: {e}"

        try:
            resultado = modelo.transcribe(caminho_wav, language="pt")
            texto = resultado["text"].strip()

            idioma_detectado = resultado.get("language", "desconhecido")
            duracao = ""

            if "segments" in resultado and resultado["segments"]:
                duracao_seg = resultado["segments"][-1]["end"]
                minutos = int(duracao_seg // 60)
                segundos = int(duracao_seg % 60)
                duracao = f" | Duracao: {minutos}m{segundos:02d}s"

            return (
                f"[Audio: {path.name}]\n"
                f"[Idioma detectado: {idioma_detectado}{duracao}]\n\n"
                f"Transcricao:\n{texto}"
            )
        except Exception as e:
            return f"Erro ao transcrever audio: {e}"
        finally:
            if temporario and os.path.exists(caminho_wav):
                with contextlib.suppress(Exception):
                    os.remove(caminho_wav)
