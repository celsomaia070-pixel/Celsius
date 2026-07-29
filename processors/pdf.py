from pathlib import Path

from core.settings import get_settings
from processors.base import ProcessadorArquivo, SecurityError


class ProcessadorPDF(ProcessadorArquivo):
    extensoes_suportadas = [".pdf"]

    @classmethod
    def processar(cls, caminho: str, base_dir: Path | None = None) -> str:
        from pypdf import PdfReader

        settings = get_settings()
        path = cls._validar_caminho(caminho, base_dir, enforce_size_limit=False)
        tamanho_mb = path.stat().st_size / (1024 * 1024)
        limite_normal_mb = settings.max_file_size_mb
        limite_pdf_mb = settings.file.max_pdf_size_mb
        pdf_grande = tamanho_mb > limite_normal_mb

        if tamanho_mb > limite_pdf_mb:
            raise SecurityError(
                "PDF muito grande para processamento local seguro: "
                f"{tamanho_mb:.1f} MB. Limite atual para PDFs: {limite_pdf_mb} MB."
            )

        leitor = PdfReader(str(path))

        metadados = leitor.metadata
        info_meta = ""
        if metadados:
            campos = []
            if metadados.title:
                campos.append(f"Titulo: {metadados.title}")
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
        paginas_lidas = 0
        limite_texto = settings.doc_text_limit
        limite_paginas = settings.file.large_pdf_page_limit if pdf_grande else total_paginas
        paginas_para_ler = min(total_paginas, limite_paginas)

        for i in range(paginas_para_ler):
            pagina = leitor.pages[i]
            texto_pagina = pagina.extract_text() or ""
            if texto_pagina.strip():
                texto += f"Pagina {i + 1}/{total_paginas}\n{texto_pagina}\n\n"
            paginas_lidas = i + 1
            if len(texto) >= limite_texto:
                break

        texto = texto.strip()
        if len(texto) > limite_texto:
            texto = texto[:limite_texto] + "\n... [Documento truncado] ..."

        resultado = f"PDF: {total_paginas} paginas | Tamanho: {tamanho_mb:.1f} MB"
        if pdf_grande:
            resultado += (
                "\nAviso: PDF acima do limite normal de 50 MB. "
                f"Foi extraida uma amostra local segura de ate {limite_paginas} paginas "
                f"e {limite_texto} caracteres. Se precisar de uma pagina especifica, "
                "peca pelo numero da pagina ou intervalo."
            )
        if paginas_lidas and paginas_lidas < total_paginas:
            resultado += f"\nPaginas analisadas nesta leitura: 1-{paginas_lidas}/{total_paginas}"
        if info_meta:
            resultado += f"\n{info_meta}"
        resultado += f"\n\n{texto}"

        return resultado
