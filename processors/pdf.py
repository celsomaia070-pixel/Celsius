from pathlib import Path

from core.config import LIMITE_TEXTO_DOCUMENTO
from processors.base import ProcessadorArquivo


class ProcessadorPDF(ProcessadorArquivo):
    extensoes_suportadas = [".pdf"]

    @classmethod
    def processar(cls, caminho: str, base_dir: Path | None = None) -> str:
        from pypdf import PdfReader

        path = cls._validar_caminho(caminho, base_dir)
        leitor = PdfReader(str(path))

        metadados = leitor.metadata
        info_meta = ""
        if metadados:
            campos = []
            if metadados.title:
                campos.append(f"Título: {metadados.title}")
            if metadados.author:
                campos.append(f"Autor: {metadados.author}")
            if metadados.subject:
                campos.append(f"Assunto: {metadados.subject}")
            if metadados.creator:
                campos.append(f"Criador: {metadados.creator}")
            if campos:
                info_meta = " | ".join(campos) + "\n"

        total_paginas = len(leitor.pages)
        texto = ""

        for i, pagina in enumerate(leitor.pages):
            texto_pagina = pagina.extract_text() or ""
            if texto_pagina.strip():
                texto += f"Página {i + 1}/{total_paginas}\n{texto_pagina}\n\n"

        texto = texto.strip()
        if len(texto) > LIMITE_TEXTO_DOCUMENTO:
            texto = texto[:LIMITE_TEXTO_DOCUMENTO] + "\n... [Documento truncado] ..."

        resultado = f"PDF: {total_paginas} páginas"
        if info_meta:
            resultado += f"\n{info_meta}"
        resultado += f"\n\n{texto}"

        return resultado
