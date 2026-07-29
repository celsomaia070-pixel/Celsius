"""Tests for TTS text preparation and provider planning."""

from core.tts import (
    EDGE_TTS_CHUNK_SIZE,
    EdgeTTSProvider,
    TTSVoiceConfig,
    naturalize_tts_text,
    split_tts_text,
)


class TestTTSNaturalization:
    def test_naturalizes_markdown_and_urls_for_speech(self):
        text = """
        ### Resumo
        1. Acesse `estoque`.
        - Veja https://example.com/item
        ```python
        print("nao falar")
        ```
        """

        spoken = naturalize_tts_text(text)

        assert "```" not in spoken
        assert "https://" not in spoken
        assert "link" in spoken
        assert "estoque" in spoken
        assert "nao falar" not in spoken

    def test_splits_long_text_into_short_chunks(self):
        text = "Primeira frase. " + ("Texto longo " * 120) + "Fim."

        chunks = split_tts_text(text, limit=120)

        assert len(chunks) > 1
        assert all(0 < len(chunk) <= 120 for chunk in chunks)

    def test_default_chunks_are_large_enough_to_avoid_excessive_requests(self):
        assert EDGE_TTS_CHUNK_SIZE >= 2000


class TestEdgeTTSProvider:
    def test_edge_tts_attempts_preserve_configured_voice_first(self):
        provider = EdgeTTSProvider(
            TTSVoiceConfig(
                voice="pt-BR-TesteNeural",
                rate="+8%",
                pitch="-2Hz",
                volume="+0%",
            )
        )

        attempts = provider._attempts()

        assert attempts[0] == (
            "pt-BR-TesteNeural",
            {"rate": "+8%", "pitch": "-2Hz", "volume": "+0%"},
        )
        assert ("pt-BR-TesteNeural", {}) in attempts
        assert ("pt-BR-AntonioNeural", {}) in attempts
