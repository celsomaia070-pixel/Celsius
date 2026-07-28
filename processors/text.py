from pathlib import Path

from processors.base import ProcessadorArquivo


class ProcessadorTexto(ProcessadorArquivo):
    extensoes_suportadas = [
        ".txt",
        ".md",
        ".py",
        ".json",
        ".csv",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".log",
    ]

    @classmethod
    def processar(cls, caminho: str | Path, base_dir: Path | None = None) -> str:
        path = Path(caminho)
        if base_dir:
            path = cls._validar_caminho(str(path), base_dir)

        with open(path, encoding="utf-8", errors="replace") as f:
            conteudo = f.read(10000)
        if len(conteudo) == 10000:
            conteudo += "\n... [arquivo truncado] ..."
        return conteudo
