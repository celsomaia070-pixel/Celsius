"""Text-to-speech helpers and provider abstractions for Celsius."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

EDGE_TTS_CHUNK_SIZE = 2200
EDGE_TTS_SINGLE_PASS_LIMIT = 2600
EDGE_TTS_FIRST_CHUNK_SIZE = 360
EDGE_TTS_FOLLOWUP_CHUNK_SIZE = 900
TTS_STREAM_MIN_CHARS = 48
TTS_STREAM_MIN_SENTENCE_CHARS = 12
TTS_STREAM_FOLLOWUP_MIN_CHARS = 48
TTS_STREAM_FOLLOWUP_SENTENCE_CHARS = 32
TTS_STREAM_MAX_CHARS = 320
TTS_STREAM_FOLLOWUP_MAX_CHARS = 360
TTS_PLAYBACK_POLL_MS = 25
EDGE_TTS_DEFAULT_RATE = "+0%"
EDGE_TTS_DEFAULT_PITCH = "+0Hz"
EDGE_TTS_DEFAULT_VOLUME = "+0%"
EDGE_TTS_FALLBACK_VOICES = (
    "pt-BR-AntonioNeural",
    "pt-BR-DonatoNeural",
    "pt-BR-FranciscaNeural",
)
TTS_ABBREVIATIONS = ("Sr.", "Sra.", "Dr.", "Dra.", "Prof.", "Profa.", "etc.", "Ex.", "ex.")


PROVIDER_EDGE_TTS = "edge-tts"
PROVIDER_PIPER = "piper"
PROVIDER_OMNIVOICE = "omnivoice"
SUPPORTED_TTS_PROVIDERS = (PROVIDER_EDGE_TTS, PROVIDER_PIPER, PROVIDER_OMNIVOICE)


@dataclass(frozen=True)
class TTSVoiceConfig:
    """Runtime voice settings for a TTS provider."""

    voice: str = "pt-BR-AntonioNeural"
    rate: str = EDGE_TTS_DEFAULT_RATE
    pitch: str = EDGE_TTS_DEFAULT_PITCH
    volume: str = EDGE_TTS_DEFAULT_VOLUME
    provider: str = PROVIDER_EDGE_TTS
    profile: str = "natural_male_br"


@dataclass(frozen=True)
class TTSVoiceProfile:
    """A product-level voice preset independent from the engine internals."""

    id: str
    name: str
    provider: str
    voice: str
    rate: str
    pitch: str
    volume: str
    description: str
    experimental: bool = False


TTS_VOICE_PROFILES = (
    TTSVoiceProfile(
        id="natural_male_br",
        name="Masculina natural",
        provider=PROVIDER_EDGE_TTS,
        voice="pt-BR-AntonioNeural",
        rate="+8%",
        pitch="-2Hz",
        volume="+0%",
        description="Voz masculina brasileira, direta e menos arrastada.",
    ),
    TTSVoiceProfile(
        id="calm_male_br",
        name="Masculina calma",
        provider=PROVIDER_EDGE_TTS,
        voice="pt-BR-DonatoNeural",
        rate="+5%",
        pitch="-3Hz",
        volume="+0%",
        description="Voz masculina brasileira com ritmo um pouco mais calmo.",
    ),
    TTSVoiceProfile(
        id="natural_female_br",
        name="Feminina natural",
        provider=PROVIDER_EDGE_TTS,
        voice="pt-BR-FranciscaNeural",
        rate="+8%",
        pitch="+0Hz",
        volume="+0%",
        description="Voz feminina brasileira, clara e natural.",
    ),
    TTSVoiceProfile(
        id="local_piper_future",
        name="Piper local",
        provider=PROVIDER_PIPER,
        voice="pt_BR",
        rate="+0%",
        pitch="+0Hz",
        volume="+0%",
        description="Reserva para TTS local leve sem internet.",
        experimental=True,
    ),
    TTSVoiceProfile(
        id="omnivoice_future",
        name="OmniVoice experimental",
        provider=PROVIDER_OMNIVOICE,
        voice="male, brazilian portuguese, natural",
        rate="+0%",
        pitch="+0Hz",
        volume="+0%",
        description="Reserva para voz local expressiva e clonagem futura.",
        experimental=True,
    ),
)


def normalize_tts_provider(provider: str | None) -> str:
    """Normalize provider aliases into stable provider ids."""

    normalized = (provider or PROVIDER_EDGE_TTS).strip().lower().replace("_", "-")
    aliases = {
        "edge": PROVIDER_EDGE_TTS,
        "edge-tts": PROVIDER_EDGE_TTS,
        "edgetts": PROVIDER_EDGE_TTS,
        "microsoft-edge": PROVIDER_EDGE_TTS,
        "piper": PROVIDER_PIPER,
        "omnivoice": PROVIDER_OMNIVOICE,
        "omni-voice": PROVIDER_OMNIVOICE,
    }
    return aliases.get(normalized, normalized)


def available_tts_profiles(provider: str | None = None) -> list[TTSVoiceProfile]:
    """Return product voice presets, optionally filtered by provider."""

    if provider is None:
        return list(TTS_VOICE_PROFILES)
    normalized = normalize_tts_provider(provider)
    return [profile for profile in TTS_VOICE_PROFILES if profile.provider == normalized]


def resolve_tts_profile(profile_id: str | None) -> TTSVoiceProfile | None:
    """Resolve a preset id without leaking provider-specific details to the UI."""

    if not profile_id:
        return None
    wanted = profile_id.strip().lower()
    return next((profile for profile in TTS_VOICE_PROFILES if profile.id == wanted), None)


class TTSProvider(Protocol):
    """Common interface for future TTS engines."""

    async def synthesize(self, text: str) -> bytes:
        """Generate audio bytes for a text segment."""


def naturalize_tts_text(text: str) -> str:
    """Convert assistant text into speech-friendly Portuguese."""

    text = text or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"https?://\S+", " link ", text)
    text = re.sub(r"\bR\$\s*([0-9][0-9.,]*)", r"\1 reais", text)
    text = re.sub(r"\bIA\b", "inteligencia artificial", text)
    text = re.sub(r"\bLLM\b", "modelo de linguagem", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPDF\b", "P D F", text, flags=re.IGNORECASE)
    text = re.sub(r"\bQR\s*Code\b", "QR Code", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=\d)%", " por cento", text)
    text = re.sub(r"\s+[|]\s+", ". ", text)
    text = re.sub(r"(^|\n)\s*[-*+]\s+", r"\1", text)
    text = re.sub(r"(^|\n)\s*\d+[.)]\s+", r"\1", text)
    text = re.sub(r"[*#_>\[\]{}|]", " ", text)
    text = re.sub(r"[/\\]", " ", text)
    text = re.sub(r"&", " e ", text)
    text = re.sub(r"([.!?;:]){2,}", r"\1", text)
    text = re.sub(r"\s*([,.;:!?])\s*", r"\1 ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def soften_tts_sentence_pauses(text: str) -> str:
    """Reduce long synthetic pauses after sentence-ending periods."""

    spoken = text or ""
    protected: dict[str, str] = {}

    def protect(value: str) -> str:
        key = f"__CELSIUS_TTS_DOT_{len(protected)}__"
        protected[key] = value
        return key

    for abbreviation in TTS_ABBREVIATIONS:
        spoken = spoken.replace(abbreviation, protect(abbreviation))
    spoken = re.sub(r"(?<=\d)\.(?=\d)", lambda _match: protect("."), spoken)
    spoken = re.sub(r"\.\s+(?=[A-Z0-9])", ", ", spoken)

    for key, value in protected.items():
        spoken = spoken.replace(key, value)
    return spoken


def prepare_tts_text_for_speech(text: str) -> str:
    """Apply all provider-agnostic text cleanup for a more human voice."""

    return soften_tts_sentence_pauses(naturalize_tts_text(text))


def soften_streaming_boundary(text: str, *, continuation: bool = True) -> str:
    """Avoid final-sentence cadence at the boundary between streamed chunks."""

    clean_text = naturalize_tts_text(text)
    if not continuation:
        return clean_text
    return re.sub(r"\.\s*$", ",", clean_text)


def split_tts_text(text: str, limit: int = EDGE_TTS_CHUNK_SIZE) -> list[str]:
    """Split text into short, natural chunks for lower latency."""

    clean_text = naturalize_tts_text(text)
    if not clean_text:
        return []

    chunks: list[str] = []
    current = ""
    parts = re.split(r"(?<=[.!?;:])\s+", clean_text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(part[i : i + limit].strip() for i in range(0, len(part), limit))
            continue
        candidate = f"{current} {part}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = part

    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def split_tts_fast_start(
    text: str,
    *,
    first_limit: int = EDGE_TTS_FIRST_CHUNK_SIZE,
    followup_limit: int = EDGE_TTS_FOLLOWUP_CHUNK_SIZE,
) -> list[str]:
    """Split speech so the first Edge TTS request is intentionally small."""

    clean_text = naturalize_tts_text(text)
    if not clean_text:
        return []
    if len(clean_text) <= first_limit:
        return [clean_text]

    chunks: list[str] = []
    current = ""
    limit = first_limit
    parts = re.split(r"(?<=[.!?;:])\s+", clean_text)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        while len(part) > limit:
            if current:
                chunks.append(current)
                current = ""
                limit = followup_limit
            chunks.append(part[:limit].strip())
            part = part[limit:].strip()
            limit = followup_limit

        candidate = f"{current} {part}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
        current = part
        limit = followup_limit

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk]


def pop_ready_tts_chunk(
    buffer: str,
    *,
    min_chars: int = TTS_STREAM_MIN_CHARS,
    min_sentence_chars: int = TTS_STREAM_MIN_SENTENCE_CHARS,
    max_chars: int = TTS_STREAM_MAX_CHARS,
) -> tuple[str | None, str]:
    """Return a speech-ready chunk from a growing text stream."""

    text = buffer or ""
    stripped = text.lstrip()
    if len(stripped) < min_sentence_chars:
        return None, stripped

    boundary = None
    for match in re.finditer(r"[.!?;:](?:\s+|$)", stripped):
        if match.end() >= min_sentence_chars:
            boundary = match.end()
            break

    if boundary is None and len(stripped) < min_chars:
        return None, stripped

    if boundary is None and len(stripped) >= max_chars:
        boundary = stripped.rfind(" ", 0, max_chars)
        if boundary <= 0:
            boundary = max_chars

    if boundary is None:
        return None, stripped

    chunk = stripped[:boundary].strip()
    remaining = stripped[boundary:].lstrip()
    if not chunk:
        return None, remaining
    return chunk, remaining


class EdgeTTSProvider:
    """Edge TTS provider with resilient voice/options fallback."""

    def __init__(self, config: TTSVoiceConfig):
        self.config = config

    async def synthesize(self, text: str) -> bytes:
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("edge_tts nao esta instalado") from exc

        attempts = self._attempts()
        last_error: Exception | None = None
        speech_text = prepare_tts_text_for_speech(text)
        for voice, options in attempts:
            try:
                audio = bytearray()
                communicate = edge_tts.Communicate(speech_text, voice, **options)
                async for item in communicate.stream():
                    if item.get("type") == "audio":
                        audio.extend(item.get("data", b""))
                if audio:
                    return bytes(audio)
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise RuntimeError("O TTS nao retornou audio para um trecho da resposta.")

    def _attempts(self) -> list[tuple[str, dict[str, str]]]:
        attempts: list[tuple[str, dict[str, str]]] = []

        def add(voice: str, options: dict[str, str]):
            if not voice:
                return
            candidate = (voice, options)
            if candidate not in attempts:
                attempts.append(candidate)

        add(
            self.config.voice,
            {
                "rate": self.config.rate,
                "pitch": self.config.pitch,
                "volume": self.config.volume,
            },
        )
        add(
            self.config.voice,
            {
                "rate": EDGE_TTS_DEFAULT_RATE,
                "pitch": EDGE_TTS_DEFAULT_PITCH,
                "volume": EDGE_TTS_DEFAULT_VOLUME,
            },
        )
        add(self.config.voice, {})
        for voice in EDGE_TTS_FALLBACK_VOICES:
            add(voice, {})
            add(
                voice,
                {
                    "rate": EDGE_TTS_DEFAULT_RATE,
                    "pitch": EDGE_TTS_DEFAULT_PITCH,
                    "volume": EDGE_TTS_DEFAULT_VOLUME,
                },
            )
        return attempts


class PlaceholderTTSProvider:
    """Explicit placeholder for future local engines."""

    def __init__(self, provider: str):
        self.provider = normalize_tts_provider(provider)

    async def synthesize(self, text: str) -> bytes:
        raise RuntimeError(
            f"Provedor TTS '{self.provider}' ainda nao esta habilitado nesta instalacao. "
            "Use edge-tts por enquanto ou instale o motor local correspondente."
        )


def create_tts_provider(config: TTSVoiceConfig) -> TTSProvider:
    """Create the configured provider behind a stable interface."""

    provider = normalize_tts_provider(config.provider)
    normalized_config = TTSVoiceConfig(
        voice=config.voice,
        rate=config.rate,
        pitch=config.pitch,
        volume=config.volume,
        provider=provider,
        profile=config.profile,
    )
    if provider == PROVIDER_EDGE_TTS:
        return EdgeTTSProvider(normalized_config)
    if provider in {PROVIDER_PIPER, PROVIDER_OMNIVOICE}:
        return PlaceholderTTSProvider(provider)
    raise RuntimeError(
        f"Provedor TTS desconhecido: {config.provider}. "
        f"Use um destes: {', '.join(SUPPORTED_TTS_PROVIDERS)}."
    )


def friendly_tts_error(error: Exception) -> str:
    message = str(error)
    if "no audio was received" in message.lower():
        return (
            "O Edge TTS nao entregou audio para esta resposta, mesmo tentando "
            "parametros neutros e vozes brasileiras alternativas. Verifique a conexao "
            "com a internet ou tente uma resposta menor."
        )
    return message
