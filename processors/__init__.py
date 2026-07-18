from pathlib import Path

from core.config import DIRETORIO_BASE
from processors.audio import ProcessadorAudio
from processors.base import ProcessadorArquivo
from processors.docx import ProcessadorDOCX
from processors.image import ProcessadorImagem
from processors.odf import ProcessadorODF
from processors.pdf import ProcessadorPDF
from processors.report import GeradorRelatorio
from processors.text import ProcessadorTexto

PROCESSADORES = {
    ".pdf": ProcessadorPDF,
    ".docx": ProcessadorDOCX,
    ".odt": ProcessadorODF,
    ".ods": ProcessadorODF,
    ".odp": ProcessadorODF,
    ".png": ProcessadorImagem,
    ".jpg": ProcessadorImagem,
    ".jpeg": ProcessadorImagem,
    ".bmp": ProcessadorImagem,
    ".gif": ProcessadorImagem,
    ".webp": ProcessadorImagem,
    ".mp3": ProcessadorAudio,
    ".wav": ProcessadorAudio,
    ".ogg": ProcessadorAudio,
    ".m4a": ProcessadorAudio,
    ".flac": ProcessadorAudio,
    ".txt": ProcessadorTexto,
    ".md": ProcessadorTexto,
    ".py": ProcessadorTexto,
    ".json": ProcessadorTexto,
    ".csv": ProcessadorTexto,
    ".xml": ProcessadorTexto,
    ".html": ProcessadorTexto,
    ".css": ProcessadorTexto,
    ".js": ProcessadorTexto,
    ".yaml": ProcessadorTexto,
    ".yml": ProcessadorTexto,
    ".toml": ProcessadorTexto,
    ".ini": ProcessadorTexto,
    ".cfg": ProcessadorTexto,
    ".log": ProcessadorTexto,
}

BASE_DIR = Path(DIRETORIO_BASE).resolve()


def processar_arquivo(caminho: str, base_dir: Path | None = None) -> str:
    import os
    extensao = os.path.splitext(caminho)[1].lower()
    classe = PROCESSADORES.get(extensao)
    if not classe:
        return f"Formato '{extensao}' nao suportado."
    return classe.processar(caminho, base_dir or BASE_DIR)
