"""Plans for unambiguous local work that needs no model or semantic retrieval."""

import re
from urllib.parse import parse_qs, quote_plus, urlparse

from core.message_intent import is_local_memory_read, normalize_text, strip_task_prefix


def direct_tool_allowed(tool: str, mode_id: str | None, work_agents: list[str] | None) -> bool:
    from core.agent_modes import get_mode

    modes = work_agents or ([mode_id] if mode_id is not None else [])
    return any(get_mode(mode).allows(tool) for mode in modes)


def simple_memory_lookup(text: str) -> bool:
    words = normalize_text(strip_task_prefix(text))
    return is_local_memory_read(text) and not bool(
        re.search(
            r"\b(?:analise|analisar|resuma|resumir|compare|comparar|explique|explicar|"
            r"interprete|interpretar|sugira|sugerir|avalie|avaliar|deduza|conclua)\b",
            words,
        )
    )


def memory_lookup_response(text: str, memories: list[str]) -> str | None:
    if not simple_memory_lookup(text):
        return None
    records = list(dict.fromkeys(str(m).strip() for m in memories if str(m).strip()))
    if not records:
        return (
            "Não encontrei registro relevante nas memórias consultadas. "
            "Isso não confirma nem descarta uma relação."
        )
    return "Nas suas memórias, encontrei estes registros:\n\n" + "\n\n".join(
        "> " + record.replace("\n", "\n> ") for record in records
    )


def youtube_open_arguments(text: str) -> dict | None:
    body = strip_task_prefix(text).strip().rstrip(".!?")
    body = re.sub(
        r"^(?:ol[aá]|oi|bom dia|boa tarde|boa noite)(?: celsius)?[\s,!.]+",
        "",
        body,
        flags=re.IGNORECASE,
    )
    prefix = r"(?:por favor[, ]+)?(?:pode |poderia )?(?:abra|abrir|abre)\s+(?:o\s+)?"
    site = r"you\s*tube"
    match = re.fullmatch(
        prefix
        + site
        + r"(?:\s+(?:em|com|sobre|(?:e\s+)?(?:pesquise|procure|busque)(?:\s+por)?)\s+(.+))?",
        body,
        re.IGNORECASE,
    )
    if match:
        term = (match[1] or "").strip()
    else:
        match = re.fullmatch(prefix + r"(.+?)\s+no\s+" + site, body, re.IGNORECASE)
        if not match:
            return None
        term = match[1].strip()
    if (
        "\n" in body
        or ";" in body
        or len(term) > 500
        or re.search(
            r"\b(?:e|depois|entao|tambem)\s+(?:depois\s+)?(?:abra|abrir|envie|mande|baixe|salve|toque|reproduza|analise|resuma|exclua|compre|gere|acesse|pesquise|faca|consulte|liste|mostre|cadastre|registre|adicione|remova|apague|execute|agende|crie|preencha|edite)\b",
            normalize_text(term),
        )
    ):
        return None
    target = "https://www.youtube.com"
    if term:
        target += "/results?search_query=" + quote_plus(term)
    return {"url": target}


def same_youtube_open(expected: dict, actual: dict) -> bool:
    if expected == actual:
        return True
    if set(actual) != {"url"}:
        return False
    target = urlparse(expected["url"])
    term = parse_qs(target.query).get("search_query", [""])[0]
    legacy = "youtube" + (" " + term if term else "")
    return str(actual["url"]).strip().casefold() == legacy.casefold()


def simple_news_query(text: str) -> str | None:
    words = normalize_text(strip_task_prefix(text))
    words = re.sub(r"^(?:ola|oi|bom dia|boa tarde|boa noite)(?: celsius)?\s+", "", words)
    if re.search(
        r"\b(?:analise|resuma|compare|explique|impacto|envie|mande|gere|crie|documentos?|meus?|minhas?|anexos?)\b",
        words,
    ):
        return None
    if re.fullmatch(
        r"(?:por favor )?(?:(?:liste|traga|mostre|busque|pesquise)(?: pra mim| para mim)?|"
        r"preciso que (?:voce )?me traga)(?: da web| na web| na internet)? "
        r"(?:as )?(?:principais )?noticias(?: .+)?",
        words,
    ):
        return strip_task_prefix(text)
    return None


def inventory_report_arguments(text: str) -> dict | None:
    words = normalize_text(strip_task_prefix(text))
    words = re.sub(r"^(?:ola|oi|bom dia|boa tarde|boa noite)(?: celsius)?\s+", "", words)
    match = re.fullmatch(
        r"(?:por favor )?(?:pode |poderia |quero que (?:voce )?|preciso que (?:voce )?)?"
        r"(?:gere|gerar|crie|criar|faca|produza|emita) (?:um |uma |o |meu )?"
        r"relatorio (?:completo |geral |atual )?(?:(?:de|do|sobre) )?"
        r"(?:(?:o )?meu )?(?:estoque|inventario)(?: atual| completo)?"
        r"(?: (?:em |no formato )?(pdf|docx|word|xlsx|excel|markdown|md))?(?: por favor)?",
        words,
    )
    if not match:
        return None
    output_format = {"word": "docx", "excel": "xlsx", "markdown": "md"}.get(
        match[1], match[1] or "pdf"
    )
    return {
        "titulo": "Relatório de estoque",
        "tipo": "Estoque",
        "fonte": "Estoque",
        "formato": output_format,
        "periodo": "Atual",
    }
