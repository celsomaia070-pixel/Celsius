from pathlib import Path

from core.settings import get_settings
from processors.base import ProcessadorArquivo


class ProcessadorODF(ProcessadorArquivo):
    extensoes_suportadas = [".odt", ".ods", ".odp"]

    @classmethod
    def processar(cls, caminho: str, base_dir: Path | None = None) -> str:
        path = cls._validar_caminho(caminho, base_dir)
        extensao = path.suffix.lower().lstrip(".")

        if extensao == "odt":
            return cls._processar_odt(path)
        elif extensao == "ods":
            return cls._processar_ods(path)
        elif extensao == "odp":
            return cls._processar_odp(path)
        return "Formato ODF nao reconhecido."

    @classmethod
    def _processar_odt(cls, caminho: Path) -> str:
        from odf import teletype, text
        from odf.opendocument import load

        doc = load(str(caminho))
        texto = ""
        for paragrafo in doc.getElementsByType(text.P):
            texto += teletype.extractText(paragrafo) + "\n"
        return cls._truncar(texto.strip())

    @classmethod
    def _processar_ods(cls, caminho: Path) -> str:
        from odf import teletype
        from odf.opendocument import load
        from odf.table import Table, TableCell, TableRow
        from odf.text import P

        doc = load(str(caminho))
        texto = ""

        for tabela in doc.getElementsByType(Table):
            nome = tabela.getAttribute("name") or "Planilha"
            texto += f"\n--- Tabela: {nome} ---\n"
            for linha in tabela.getElementsByType(TableRow):
                celulas = []
                for celula in linha.getElementsByType(TableCell):
                    repeticoes = celula.getAttribute("numbercolumnsrepeated")
                    conteudo = ""
                    for p in celula.getElementsByType(P):
                        conteudo += (
                            teletype.extractText(p) if hasattr(teletype, "extractText") else ""
                        )
                    try:
                        if repeticoes and int(repeticoes) > 10:
                            continue
                    except (ValueError, TypeError):
                        pass
                    celulas.append(conteudo.strip())
                if any(c for c in celulas):
                    texto += " | ".join(celulas) + "\n"
            texto += "--- Fim ---\n"

        return cls._truncar(texto.strip())

    @classmethod
    def _processar_odp(cls, caminho: Path) -> str:
        from odf.opendocument import load
        from odf.text import P

        doc = load(str(caminho))
        texto = ""
        for paragrafo in doc.getElementsByType(P):
            texto += paragrafo.firstChild.data if paragrafo.firstChild else ""
            texto += "\n"
        return cls._truncar(texto.strip())

    @classmethod
    def _truncar(cls, texto: str) -> str:
        limite_texto = get_settings().doc_text_limit
        if len(texto) > limite_texto:
            return texto[:limite_texto] + "\n... [Documento truncado] ..."
        return texto
