import base64
import json
import re
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from html.parser import HTMLParser

from duckduckgo_search import DDGS

_WEATHER_CODES = {
    0: "Céu limpo", 1: "Predominantemente limpo", 2: "Parcialmente nublado",
    3: "Nublado", 45: "Neblina", 48: "Neblina com geada", 51: "Garoa fraca",
    53: "Garoa moderada", 55: "Garoa forte", 61: "Chuva fraca", 63: "Chuva moderada",
    65: "Chuva forte", 71: "Neve fraca", 73: "Neve moderada", 75: "Neve forte",
    80: "Pancadas fracas", 81: "Pancadas moderadas", 82: "Pancadas fortes",
    95: "Trovoada", 96: "Trovoada com granizo fraco", 99: "Trovoada com granizo forte",
}


def _weather_forecast(texto: str) -> str | None:
    """Return a location-specific forecast from Open-Meteo's public API."""
    match = re.search(r"\bem\s+(.+?)\s*$", texto, re.IGNORECASE)
    if not match:
        match = re.search(r"\bpara\s+(.+?)\s*$", texto, re.IGNORECASE)
    if not match:
        return None
    place = match.group(1).strip(" .,!?")
    place = re.sub(r"(?:\s|,)+(?:sp|sao paulo|são paulo)$", "", place, flags=re.IGNORECASE)
    if not place:
        return None
    geocode_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": place, "count": 10, "language": "pt", "format": "json"}
    )
    try:
        request = urllib.request.Request(geocode_url, headers={"User-Agent": "Celsius/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:  # nosec B310 - fixed HTTPS host
            places = json.loads(response.read().decode("utf-8"))
        candidates = places.get("results") or []
        location = next(
            (item for item in candidates if item.get("country_code") == "BR" and item.get("admin1") == "São Paulo"),
            candidates[0] if candidates else None,
        )
        if not location:
            return "Nenhuma localidade foi encontrada para a previsao solicitada."
        forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
            {
                "latitude": location["latitude"], "longitude": location["longitude"],
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "America/Sao_Paulo", "forecast_days": 5,
            }
        )
        request = urllib.request.Request(forecast_url, headers={"User-Agent": "Celsius/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:  # nosec B310 - fixed HTTPS host
            forecast = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return f"Erro na consulta meteorologica: {exc}"
    daily = forecast.get("daily") or {}
    lines = [
        f"[FONTE_WEB] Open-Meteo — previsao para {location['name']}, {location.get('admin1', '')}",
        f"URL: {forecast_url}",
    ]
    for date, low, high, rain, code in zip(
        daily.get("time", []), daily.get("temperature_2m_min", []), daily.get("temperature_2m_max", []),
        daily.get("precipitation_probability_max", []), daily.get("weather_code", []), strict=False,
    ):
        condition = _WEATHER_CODES.get(code, "Condição não especificada")
        lines.append(f"{date}: {condition}; mínima {low}°C; máxima {high}°C; chuva {rain}%.")
    return "\n".join(lines)


class _BingResultParser(HTMLParser):
    """Small dependency-free parser used when DuckDuckGo returns no items."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._in_result = False
        self._in_title = False
        self._in_body = False
        self._href = ""
        self._title: list[str] = []
        self._body: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(str(attributes.get("class", "")).split())
        if tag == "li" and "b_algo" in classes:
            self._in_result = True
            self._title, self._body, self._href = [], [], ""
        elif self._in_result and tag == "a" and not self._href:
            self._href = str(attributes.get("href", ""))
            self._in_title = True
        elif self._in_result and tag in {"p", "div"}:
            self._in_body = True

    def handle_endtag(self, tag):
        if not self._in_result:
            return
        if tag == "a":
            self._in_title = False
        elif tag in {"p", "div"}:
            self._in_body = False
        elif tag == "li":
            title = " ".join("".join(self._title).split())
            body = " ".join("".join(self._body).split())
            if self._href.startswith(("http://", "https://")) and title:
                self.results.append({"title": title, "body": body, "href": self._href})
            self._in_result = False

    def handle_data(self, data):
        if self._in_title:
            self._title.append(data)
        elif self._in_body:
            self._body.append(data)


def _bing_search(texto: str) -> list[dict[str, str]]:
    url = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(texto)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=12) as response:  # nosec B310 - fixed HTTPS host
        parser = _BingResultParser()
        parser.feed(response.read().decode("utf-8", errors="replace"))
        for item in parser.results:
            parsed = urllib.parse.urlparse(item["href"])
            query = urllib.parse.parse_qs(parsed.query)
            encoded = query.get("u", [""])[0]
            if encoded.startswith("a1"):
                try:
                    decoded = base64.urlsafe_b64decode(encoded[2:] + "===").decode()
                    if decoded.startswith(("http://", "https://")):
                        item["href"] = decoded
                except (ValueError, UnicodeDecodeError):
                    pass
        return parser.results[:5]


def pesquisar_web(texto):
    normalized = str(texto).casefold()
    if any(word in normalized for word in ("previsao", "previsão", "tempo", "clima", "meteorolog")):
        forecast = _weather_forecast(str(texto))
        if forecast is not None:
            return forecast
    resultados = []
    try:
        ddgs = DDGS()
        for item in ddgs.text(texto, max_results=5):
            title = str(item.get("title", "")).strip()
            body = str(item.get("body", "")).strip()
            href = str(item.get("href", item.get("url", ""))).strip()
            if not href:
                continue
            resultados.append(f"[FONTE_WEB] {title}\n{body}\nURL: {href}")
    except Exception as e:
        # DuckDuckGo occasionally responds successfully but yields no parsed
        # entries. Bing is a read-only fallback so current-information queries
        # do not silently become an unsourced model response.
        try:
            fallback = _bing_search(texto)
            resultados.extend(
                f"[FONTE_WEB] {item['title']}\n{item['body']}\nURL: {item['href']}"
                for item in fallback
            )
        except Exception as fallback_error:
            return f"Erro na pesquisa web: {e}; fallback: {fallback_error}"
    if not resultados:
        try:
            fallback = _bing_search(texto)
            resultados.extend(
                f"[FONTE_WEB] {item['title']}\n{item['body']}\nURL: {item['href']}"
                for item in fallback
            )
        except Exception as fallback_error:
            return f"Erro na pesquisa web: fallback: {fallback_error}"
    if not resultados:
        return "Nenhuma fonte web verificavel foi encontrada."
    return "\n\n".join(resultados)


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
                webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote_plus(termo)}")
                return f"Pesquisando **{termo}** no Google."

        # "abra google e pesquise X"
        match_gg2 = re.search(
            r"abra\s+o?\s*google\s+(?:e\s+)?(?:pesquise|procure|busque|pesquisar|procurar|buscar)\s+(?:por\s+)?(.+)",
            texto_lower,
        )
        if match_gg2:
            termo = match_gg2.group(1).strip().rstrip("?")
            if termo:
                webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote_plus(termo)}")
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
                webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote_plus(termo)}")
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
        return (
            f"Data atual: {datetime.now().strftime('%d/%m/%Y')} ({datetime.now().strftime('%A')})"
        )

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
