"""Explicit web research with dated news and bounded, public-only retrieval."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from core.message_intent import classify_intent, has_local_source, normalize_text, strip_task_prefix
from core.network_security import validate_public_http_url
from core.operation_control import check_control


def is_web_lookup(text: str) -> bool:
    words = normalize_text(text)
    if not classify_intent(text).operational:
        return False
    if has_local_source(text):
        return False
    if re.search(r"\b(?:noticias?|internet|web|previsao|meteorolog\w*|cotacao|clima)\b", words):
        return True
    return bool(re.search(r"\bpesquis\w*\b", words)) and not bool(
        re.search(
            r"\b(?:estoque|inventario|meus?|minhas?|clientes?|fornecedores?|base|documentos?|anexos?)\b",
            words,
        )
    )


def news_window(text: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    words = normalize_text(text)
    monday = today - timedelta(days=today.weekday())
    if "semana passada" in words or "ultima semana" in words:
        return monday - timedelta(days=7), monday
    if "desta semana" in words or "essa semana" in words or "esta semana" in words:
        return monday, today + timedelta(days=1)
    days = re.search(r"ultimos (\d+) dias", words)
    return today - timedelta(days=min(int(days[1]), 90) if days else 7), today + timedelta(days=1)


def search_topic(text: str) -> str:
    words = normalize_text(strip_task_prefix(text))
    match = re.search(
        r"\bnoticias?\s+(?:(?:mais )?(?:relevantes|importantes)\s+)?(?:sobre |de |da |do )?(.+)",
        words,
    )
    if match:
        words = match[1]
    else:
        words = re.sub(
            r"^(?:pesquise|pesquisar|busque|buscar|procure|procurar) (?:na |no )?(?:web |internet )?",
            "",
            words,
        )
    words = re.sub(
        r"\b(?:desta|dessa|esta|essa|na|da)?\s*(?:semana passada|ultima semana|semana|ultimos \d+ dias)\b",
        "",
        words,
    )
    words = re.sub(
        r"\b(?:principais|mais relevantes|mais importantes|noticias|recentes)\b", "", words
    )
    words = re.sub(r"\bia\b", "inteligencia artificial", words)
    return " ".join(words.split()).strip() or "noticias"


def query_from_history(text: str, history: list[dict] | None) -> str:
    words = normalize_text(text)
    if re.search(r"\b(?:dessas noticias|essas noticias|desses resultados|dessas fontes)\b", words):
        for message in reversed(history or []):
            if message.get("role") == "user" and "noticia" in normalize_text(
                message.get("content", "")
            ):
                candidate = str(message.get("content", ""))
                if candidate != text and not re.search(
                    r"\b(?:dessas|essas) noticias\b", normalize_text(candidate)
                ):
                    return candidate
    return text


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_html(text: str) -> str:
    parser = _Text()
    parser.feed(str(text or ""))
    return " ".join(" ".join(parser.parts).split())


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url: str, *, timeout: int = 8, max_bytes: int = 2_000_000) -> tuple[str, bytes]:
    check_control()
    url = validate_public_http_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CelsiusResearch/1.0"})
    with urllib.request.build_opener(_SafeRedirect()).open(request, timeout=timeout) as response:
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("Conteúdo web excede o limite de leitura.")
        final_url = validate_public_http_url(response.geturl())
    check_control()
    return final_url, payload


def _google_news(topic: str, start: date, end: date) -> list[dict]:
    query = f"{topic} after:{start.isoformat()} before:{end.isoformat()}"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
    )
    _, payload = fetch_public(url)
    rows = []
    for item in ET.fromstring(payload).findall("./channel/item")[:30]:
        source = item.find("source")
        rows.append(
            {
                "title": item.findtext("title", ""),
                "url": item.findtext("link", ""),
                "body": item.findtext("description", ""),
                "date": item.findtext("pubDate", ""),
                "source": source.text if source is not None else "Google Notícias",
            }
        )
    return rows


def _publication_date(value: str) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(str(value))
        except (ValueError, TypeError):
            return None
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def search_news(query: str, *, today: date | None = None) -> str:
    from duckduckgo_search import DDGS

    check_control()
    start, end = news_window(query, today)
    topic = search_topic(query)
    rows = []
    try:
        age = ((today or date.today()) - start).days
        period = "w" if age <= 7 else "m" if age <= 30 else "y"
        rows = list(DDGS(timeout=8).news(topic, region="br-pt", timelimit=period, max_results=12))
    except Exception:
        check_control()
    check_control()
    accepted = _dated_news(rows, start, end)
    if len(accepted) < 3:
        try:
            accepted.extend(_dated_news(_google_news(topic, start, end), start, end))
        except (OSError, ValueError, ET.ParseError):
            check_control()
    unique = []
    seen = set()
    sources: dict[str, int] = {}
    priority_words = {
        "modelo",
        "pesquisa",
        "lancamento",
        "regulacao",
        "investimento",
        "bilhoes",
        "data center",
        "chips",
        "seguranca",
        "openai",
        "google",
    }

    def priority(row):
        headline = normalize_text(row["title"])
        return sum(word in headline for word in priority_words)

    for row in sorted(accepted, key=priority, reverse=True):
        headline = normalize_text(row["title"])
        source = row["source"] or urllib.parse.urlparse(row["url"]).netloc
        if row["url"] in seen or headline in seen or sources.get(source, 0) >= 2:
            continue
        seen.add(row["url"])
        seen.add(headline)
        sources[source] = sources.get(source, 0) + 1
        unique.append(row)
        if len(unique) >= 8:
            break
    if not unique:
        return (
            f"Nenhuma notícia com data verificável foi encontrada entre {start:%d/%m/%Y} "
            f"e {end - timedelta(days=1):%d/%m/%Y}. Não substitua por notícias fora desse período."
        )
    lines = [
        f"Recorte verificado: {start:%d/%m/%Y} a {end - timedelta(days=1):%d/%m/%Y}.",
        "Evidência: títulos, datas e resumos do serviço de notícias; artigos completos não foram lidos.",
    ]
    for row in unique:
        lines.append(
            f"[FONTE_WEB] {row['title']}\nPublicada em: {row['published'].isoformat()}\n"
            f"Fonte: {row['source']}\nResumo: {row['body']}\nURL: {row['url']}"
        )
    return "\n\n".join(lines)


def news_digest(evidence: str) -> str:
    if "[FONTE_WEB]" not in evidence:
        return evidence
    header, *blocks = evidence.split("[FONTE_WEB] ")
    parts = [
        "**Notícias encontradas**",
        header.strip(),
        "Seleção por potencial impacto em tecnologia, pesquisa, investimento e regulação; até duas notícias por fonte.",
    ]
    for index, block in enumerate(blocks, 1):
        lines = block.strip().splitlines()
        values = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
        url = values.get("URL", "")
        if not lines or not url.startswith(("https://", "http://")):
            continue
        title = lines[0].replace("[", "(").replace("]", ")")
        parts.append(
            f"{index}. **{title}**\n"
            f"{values.get('Fonte', '')} — {values.get('Publicada em', '')[:10]}\n"
            f"{values.get('Resumo', '')}\n[Fonte]({url})"
        )
    return "\n\n".join(parts)


def _dated_news(rows: list[dict], start: date, end: date) -> list[dict]:
    accepted = []
    for row in rows:
        published = _publication_date(row.get("date", ""))
        url = str(row.get("url", row.get("href", "")))
        if (
            not published
            or not start <= published.date() < end
            or not url.startswith(("http://", "https://"))
        ):
            continue
        title = clean_html(row.get("title", ""))
        if not title:
            continue
        accepted.append(
            {
                "title": title,
                "url": url,
                "published": published,
                "source": clean_html(row.get("source", "")),
                "body": clean_html(row.get("body", ""))[:550],
            }
        )
    return accepted
