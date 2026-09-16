"""Content validation for untrusted files before native parsers receive them."""

from __future__ import annotations

import io
import warnings
import zipfile
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
TEXT_EXTENSIONS = {
    ".cfg",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".log",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
ZIP_DOCUMENT_EXTENSIONS = {".docx", ".odt", ".ods", ".odp"}


class UnsafeFileContentError(ValueError):
    """Raised when bytes do not safely match the claimed file type."""


def validate_file_content(filename: str, content: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise UnsafeFileContentError("O conteudo nao corresponde a um arquivo PDF valido.")
    if suffix in IMAGE_EXTENSIONS:
        _validate_image(content)
    elif suffix in ZIP_DOCUMENT_EXTENSIONS:
        _validate_zip_document(suffix, content)
    elif suffix in TEXT_EXTENSIONS and b"\x00" in content[:65536]:
        raise UnsafeFileContentError("Arquivo de texto contem dados binarios inesperados.")
    elif suffix in {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".webm"}:
        _validate_audio(suffix, content)


def validate_image_content(content: bytes) -> None:
    _validate_image(content)


def _validate_image(content: bytes) -> None:
    try:
        from PIL import Image

        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                if width <= 0 or height <= 0 or width > 12000 or height > 12000:
                    raise UnsafeFileContentError("Dimensoes da imagem excedem o limite seguro.")
                if width * height > 40_000_000:
                    raise UnsafeFileContentError("Imagem excede o limite seguro de pixels.")
                image.verify()
    except UnsafeFileContentError:
        raise
    except Exception as exc:
        raise UnsafeFileContentError("O conteudo nao corresponde a uma imagem valida.") from exc


def _validate_zip_document(suffix: str, content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 10_000:
                raise UnsafeFileContentError("Documento compactado contem arquivos demais.")
            total_size = sum(entry.file_size for entry in entries)
            compressed_size = max(1, sum(entry.compress_size for entry in entries))
            if total_size > 250 * 1024 * 1024 or total_size / compressed_size > 200:
                raise UnsafeFileContentError("Documento compactado excede os limites seguros.")
            names = {entry.filename for entry in entries}
            expected = {
                ".docx": lambda: any(name.startswith("word/") for name in names),
                ".odt": lambda: "content.xml" in names,
                ".ods": lambda: "content.xml" in names,
                ".odp": lambda: "content.xml" in names,
            }
            if not expected[suffix]():
                raise UnsafeFileContentError("O conteudo nao corresponde ao formato informado.")
    except UnsafeFileContentError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise UnsafeFileContentError("Documento compactado invalido.") from exc


def _validate_audio(suffix: str, content: bytes) -> None:
    signatures = {
        ".wav": content.startswith(b"RIFF") and content[8:12] == b"WAVE",
        ".ogg": content.startswith(b"OggS"),
        ".flac": content.startswith(b"fLaC"),
        ".webm": content.startswith(b"\x1aE\xdf\xa3"),
        ".m4a": len(content) >= 12 and content[4:8] == b"ftyp",
        ".mp3": content.startswith(b"ID3")
        or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0),
    }
    if not signatures[suffix]:
        raise UnsafeFileContentError("O conteudo nao corresponde ao formato de audio informado.")
