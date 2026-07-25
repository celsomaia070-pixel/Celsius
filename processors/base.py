from abc import ABC, abstractmethod
from pathlib import Path

from core.config import MAX_FILE_SIZE_BYTES


class SecurityError(Exception):
    pass


def validate_path(path: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(path).resolve()

    if base_dir is not None:
        base_dir = Path(base_dir).resolve()
        try:
            path.relative_to(base_dir)
        except ValueError:
            raise SecurityError(f"Path traversal attempt blocked: {path}") from None

    if not path.exists():
        raise SecurityError(f"File not found: {path}")

    if not path.is_file():
        raise SecurityError(f"Not a file: {path}")

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        limit_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        raise SecurityError(
            f"File too large: {size_mb:.1f} MB exceeds limit of {limit_mb:.0f} MB: {path}"
        )

    return path


class ProcessadorArquivo(ABC):
    extensoes_suportadas: list[str] = []

    @classmethod
    @abstractmethod
    def processar(cls, caminho: str, base_dir: Path | None = None) -> str:
        pass

    @classmethod
    def _validar_caminho(cls, caminho: str, base_dir: Path | None = None) -> Path:
        return validate_path(caminho, base_dir)

    @classmethod
    def suporta_extensao(cls, extensao: str) -> bool:
        return extensao.lower() in cls.extensoes_suportadas
