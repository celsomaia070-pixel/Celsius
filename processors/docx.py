from pathlib import Path

from processors.base import ProcessadorArquivo, truncar_texto


class ProcessadorDOCX(ProcessadorArquivo):
    extensoes_suportadas = [".docx"]

    @classmethod
    def processar(cls, caminho: str, base_dir: Path | None = None) -> str:
        import docx

        path = cls._validar_caminho(caminho, base_dir)
        doc = docx.Document(str(path))
        texto = ""

        for paragrafo in doc.paragraphs:
            if paragrafo.text.strip():
                texto += paragrafo.text + "\n"

        for tabela in doc.tables:
            texto += "\n--- Tabela ---\n"
            for linha in tabela.rows:
                celulas = [celula.text.strip() for celula in linha.cells]
                texto += " | ".join(celulas) + "\n"
            texto += "--- Fim da Tabela ---\n"

        return truncar_texto(texto.strip())
