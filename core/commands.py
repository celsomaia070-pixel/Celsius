import re
import urllib.parse
import webbrowser
from datetime import datetime

from duckduckgo_search import DDGS


def pesquisar_web(texto):
    resultados = []
    try:
        with DDGS() as ddgs:
            for item in ddgs.text(texto, max_results=2):
                resultados.append(
                    f"- {item.get('title', '')}\n{item.get('body', '')}"
                )
    except Exception as e:
        return f"Erro na pesquisa: {e}"
    return "\n".join(resultados)


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = re.sub(r"\s+", " ", texto)
    texto = texto.replace("you tube", "youtube")
    texto = re.sub(r"[?!.,;:]+", "", texto)
    return texto.strip()


def executar_comando(texto):
    texto_lower = _normalizar(texto)

    if "--- inicio do documento ---" in texto_lower:
        return None

    tem_youtube = "youtube" in texto_lower
    tem_google = "google" in texto_lower

    if tem_youtube:
        match_yt = re.search(
            r"abra\s+o?\s*youtube\s+(?:e\s+)?(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+(?:por\s+)?(.+)"
            r"|(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+no\s+youtube\s+(.+)"
            r"|(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+(.+)\s+no\s+youtube",
            texto_lower,
        )
        if match_yt:
            termo = match_yt.group(1) or match_yt.group(2) or match_yt.group(3)
            if termo:
                termo_limpo = termo.strip().rstrip("?")
                if termo_limpo:
                    webbrowser.open(
                        f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(termo_limpo)}"
                    )
                    return f"Abrindo o YouTube e pesquisando por: '{termo_limpo}'..."

        if re.search(r"abra\s+o?\s*youtube|abrir\s+o?\s*youtube|^youtube$", texto_lower):
            webbrowser.open("https://www.youtube.com")
            return "Abrindo a pagina inicial do YouTube!"

    if tem_google:
        match_gg = re.search(
            r"abra\s+o?\s*google\s+(?:e\s+)?(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+(?:por\s+)?(.+)"
            r"|(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+no\s+google\s+(.+)"
            r"|(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+(.+)\s+no\s+google",
            texto_lower,
        )
        if match_gg:
            termo = match_gg.group(1) or match_gg.group(2) or match_gg.group(3)
            if termo:
                termo_limpo = termo.strip().rstrip("?")
                if termo_limpo:
                    webbrowser.open(
                        f"https://www.google.com/search?q={urllib.parse.quote_plus(termo_limpo)}"
                    )
                    return f"Abrindo o Google e pesquisando por: '{termo_limpo}'..."

        if re.search(r"abra\s+o?\s*google|abrir\s+o?\s*google|^google$", texto_lower):
            webbrowser.open("https://www.google.com")
            return "Abrindo a pagina inicial do Google!"

    padroes_hora = [
        r"que horas sao",
        r"horas",
        r"hora\b",
        r"qual a hora",
        r"horario",
    ]
    if any(re.search(p, texto_lower) for p in padroes_hora):
        return f"Hora atual: {datetime.now().strftime('%H:%M')}"

    return None
