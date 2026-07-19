from abc import ABC, abstractmethod
from pathlib import Path


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
