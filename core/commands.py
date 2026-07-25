import re
import urllib.parse
import webbrowser
from datetime import datetime

from duckduckgo_search import DDGS


def pesquisar_web(texto):
    resultados = []
    try:
        ddgs = DDGS()
        for item in ddgs.text(texto, max_results=5):
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

    # ── YouTube ──────────────────────────────────────────────
    if tem_youtube:
        # "abra X no youtube" / "abra o X no youtube" / "abra o site X no youtube"
        match_yt = re.search(
            r"abra\s+(?:o\s+)?(?:site\s+)?(.+?)\s+no\s+youtube",
            texto_lower,
        )
        if match_yt:
            termo = match_yt.group(1).strip().rstrip("?")
            if termo:
                webbrowser.open(
                    f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(termo)}"
                )
                return f"Pesquisando **{termo}** no YouTube."

        # "abra youtube e pesquise X" / "abra youtube pesquise X"
        match_yt2 = re.search(
            r"abra\s+o?\s*youtube\s+(?:e\s+)?(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+(?:por\s+)?(.+)",
            texto_lower,
        )
        if match_yt2:
            termo = match_yt2.group(1).strip().rstrip("?")
            if termo:
                webbrowser.open(
                    f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(termo)}"
                )
                return f"Pesquisando **{termo}** no YouTube."

        # "pesquise no youtube X" / "pesquise X no youtube"
        match_yt3 = re.search(
            r"(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+no\s+youtube\s+(.+)"
            r"|(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+(.+)\s+no\s+youtube",
            texto_lower,
        )
        if match_yt3:
            termo = (match_yt3.group(1) or match_yt3.group(2) or "").strip().rstrip("?")
            if termo:
                webbrowser.open(
                    f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(termo)}"
                )
                return f"Pesquisando **{termo}** no YouTube."

        # "abra youtube" / "abrir youtube" / "youtube" (somente)
        if re.search(r"abra\s+o?\s*youtube|abrir\s+o?\s*youtube|^youtube$", texto_lower):
            webbrowser.open("https://www.youtube.com")
            return "Abrindo YouTube."

    # ── Google ───────────────────────────────────────────────
    if tem_google:
        # "abra X no google" / "abra o site X no google"
        match_gg = re.search(
            r"abra\s+(?:o\s+)?(?:site\s+)?(.+?)\s+no\s+google",
            texto_lower,
        )
        if match_gg:
            termo = match_gg.group(1).strip().rstrip("?")
            if termo:
                webbrowser.open(
                    f"https://www.google.com/search?q={urllib.parse.quote_plus(termo)}"
                )
                return f"Pesquisando **{termo}** no Google."

        # "abra google e pesquise X"
        match_gg2 = re.search(
            r"abra\s+o?\s*google\s+(?:e\s+)?(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+(?:por\s+)?(.+)",
            texto_lower,
        )
        if match_gg2:
            termo = match_gg2.group(1).strip().rstrip("?")
            if termo:
                webbrowser.open(
                    f"https://www.google.com/search?q={urllib.parse.quote_plus(termo)}"
                )
                return f"Pesquisando **{termo}** no Google."

        # "pesquise no google X" / "pesquise X no google"
        match_gg3 = re.search(
            r"(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+no\s+google\s+(.+)"
            r"|(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+(.+)\s+no\s+google",
            texto_lower,
        )
        if match_gg3:
            termo = (match_gg3.group(1) or match_gg3.group(2) or "").strip().rstrip("?")
            if termo:
                webbrowser.open(
                    f"https://www.google.com/search?q={urllib.parse.quote_plus(termo)}"
                )
                return f"Pesquisando **{termo}** no Google."

        # "abra google" / "abrir google" / "google" (somente)
        if re.search(r"abra\s+o?\s*google|abrir\s+o?\s*google|^google$", texto_lower):
            webbrowser.open("https://www.google.com")
            return "Abrindo Google."

    # ── Hora ─────────────────────────────────────────────────
    padroes_hora = [
        r"que horas sao",
        r"\bhoras\b",
        r"\bhora\b",
        r"qual a hora",
        r"\bhorario\b",
    ]
    if any(re.search(p, texto_lower) for p in padroes_hora):
        return f"Hora atual: {datetime.now().strftime('%H:%M')}"

    # ── Data ─────────────────────────────────────────────────
    padroes_data = [
        r"que dia e hoje",
        r"qual a data",
        r"que data",
        r"\bdata\b",
        r"dia atual",
    ]
    if any(re.search(p, texto_lower) for p in padroes_data):
        return f"Data atual: {datetime.now().strftime('%d/%m/%Y')} ({datetime.now().strftime('%A')})"

    # ── Pesquisa web (DuckDuckGo) ────────────────────────────
    # Com "na web"/"na internet" (original)
    padroes_pesquisa = [
        r"pesquisar\s+(?:na\s+)?(?:web|internet|duckduckgo)\s+(.+)",
        r"buscar\s+(?:na\s+)?(?:web|internet|duckduckgo)\s+(.+)",
        r"pesquise\s+(?:na\s+)?(?:web|internet|duckduckgo)\s+(.+)",
        r"busque\s+(?:na\s+)?(?:web|internet|duckduckgo)\s+(.+)",
        r"procure\s+(?:na\s+)?(?:web|internet|duckduckgo)\s+(.+)",
        r"procurar\s+(?:na\s+)?(?:web|internet|duckduckgo)\s+(.+)",
    ]
    for p in padroes_pesquisa:
        m = re.search(p, texto_lower)
        if m:
            termo = m.group(1).strip().rstrip("?")
            if termo:
                return pesquisar_web(termo)

    # Sem "na web" — detectar intenção de pesquisa na web
    padroes_pesquisa_geral = [
        r"(?:pesquise|pesquisar|busque|buscar|procure|procurar)\s+(.+)",
        r"ultimas?\s+noticias?\s+(?:sobre|de|do|da|dos|das)\s+(.+)",
        r"noticias?\s+(?:sobre|de|do|da|dos|das)\s+(.+)",
    ]
    for p in padroes_pesquisa_geral:
        m = re.search(p, texto_lower)
        if m:
            termo = m.group(1).strip().rstrip("?")
            if termo:
                return pesquisar_web(termo)

    return None
