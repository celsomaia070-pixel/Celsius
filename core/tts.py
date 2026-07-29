"""Text-to-speech helpers and provider abstractions for Celsius."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

EDGE_TTS_CHUNK_SIZE = 2200
EDGE_TTS_SINGLE_PASS_LIMIT = 2600
EDGE_TTS_DEFAULT_RATE = "+0%"
EDGE_TTS_DEFAULT_PITCH = "+0Hz"
EDGE_TTS_DEFAULT_VOLUME = "+0%"
EDGE_TTS_FALLBACK_VOICES = (
    "pt-BR-AntonioNeural",
    "pt-BR-DonatoNeural",
    "pt-BR-FranciscaNeural",
)


@dataclass(frozen=True)
class TTSVoiceConfig:
    """Runtime voice settings for a TTS provider."""

    voice: str
    rate: str = EDGE_TTS_DEFAULT_RATE
    pitch: str = EDGE_TTS_DEFAULT_PITCH
    volume: str = EDGE_TTS_DEFAULT_VOLUME


class TTSProvider(Protocol):
    """Common interface for future TTS engines."""

    async def synthesize(self, text: str) -> bytes:
        """Generate audio bytes for a text segment."""


def naturalize_tts_text(text: str) -> str:
    """Convert assistant text into speech-friendly Portuguese."""

    text = re.sub(r"```.*?```", " ", text or "", flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"https?://\S+", " link ", text)
    text = re.sub(r"(^|\n)\s*[-*+]\s+", r"\1", text)
    text = re.sub(r"(^|\n)\s*\d+[.)]\s+", r"\1", text)
    text = re.sub(r"[*#_>\[\]{}|]", " ", text)
    text = re.sub(r"([.!?;:]){2,}", r"\1", text)
    text = re.sub(r"\s*([,.;:!?])\s*", r"\1 ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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
        for voice, options in attempts:
            try:
                audio = bytearray()
                communicate = edge_tts.Communicate(text, voice, **options)
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


def friendly_tts_error(error: Exception) -> str:
    message = str(error)
    if "no audio was received" in message.lower():
        return (
            "O Edge TTS nao entregou audio para esta resposta, mesmo tentando "
            "parametros neutros e vozes brasileiras alternativas. Verifique a conexao "
            "com a internet ou tente uma resposta menor."
        )
    return message
