"""Tests for TTS text preparation and provider planning."""

from core.tts import (
    EDGE_TTS_CHUNK_SIZE,
    EDGE_TTS_FIRST_CHUNK_SIZE,
    TTS_PLAYBACK_POLL_MS,
    TTS_STREAM_FOLLOWUP_MAX_CHARS,
    TTS_STREAM_FOLLOWUP_MIN_CHARS,
    TTS_STREAM_FOLLOWUP_SENTENCE_CHARS,
    TTS_STREAM_MAX_CHARS,
    TTS_STREAM_MIN_SENTENCE_CHARS,
    EdgeTTSProvider,
    PlaceholderTTSProvider,
    TTSVoiceConfig,
    available_tts_profiles,
    create_tts_provider,
    naturalize_tts_text,
    normalize_tts_provider,
    pop_ready_tts_chunk,
    prepare_tts_text_for_speech,
    resolve_tts_profile,
    soften_streaming_boundary,
    soften_tts_sentence_pauses,
    split_tts_fast_start,
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

    def test_softens_sentence_periods_for_more_continuous_speech(self):
        text = "Primeira frase. Segunda frase. Ultima frase."

        spoken = soften_tts_sentence_pauses(text)

        assert spoken == "Primeira frase, Segunda frase, Ultima frase."

    def test_softening_preserves_abbreviations_and_numbers(self):
        text = "Dr. Silva revisou 1.500 itens. Depois confirmou."

        spoken = soften_tts_sentence_pauses(text)

        assert "Dr. Silva" in spoken
        assert "1.500" in spoken
        assert "itens, Depois" in spoken

    def test_fast_start_keeps_first_tts_request_short(self):
        text = "Esta primeira frase deve comecar rapido. " + (
            "Depois vem uma explicacao maior sobre estoque e atendimento. " * 40
        )

        chunks = split_tts_fast_start(text)

        assert len(chunks) > 1
        assert len(chunks[0]) <= EDGE_TTS_FIRST_CHUNK_SIZE
        assert chunks[0].startswith("Esta primeira frase")

    def test_streaming_chunk_waits_for_enough_text(self):
        chunk, remaining = pop_ready_tts_chunk("Sim.")

        assert chunk is None
        assert remaining == "Sim."

    def test_streaming_chunk_allows_short_opening_sentence(self):
        text = "Claro, Celso. Vou organizar isso agora."

        chunk, remaining = pop_ready_tts_chunk(text)

        assert len(chunk) >= TTS_STREAM_MIN_SENTENCE_CHARS
        assert chunk == "Claro, Celso."
        assert remaining == "Vou organizar isso agora."

    def test_followup_streaming_chunk_groups_short_sentences(self):
        text = "Primeira frase curta. Segunda frase curta. Terceira frase curta."

        chunk, remaining = pop_ready_tts_chunk(
            text,
            min_chars=TTS_STREAM_FOLLOWUP_MIN_CHARS,
            min_sentence_chars=TTS_STREAM_FOLLOWUP_SENTENCE_CHARS,
            max_chars=TTS_STREAM_FOLLOWUP_MAX_CHARS,
        )

        assert chunk == "Primeira frase curta. Segunda frase curta."
        assert remaining == "Terceira frase curta."

    def test_streaming_boundary_avoids_final_cadence_between_chunks(self):
        assert soften_streaming_boundary("Primeira frase.") == "Primeira frase,"
        assert soften_streaming_boundary("Ultima frase.", continuation=False) == "Ultima frase."

    def test_playback_poll_does_not_add_a_noticeable_gap(self):
        assert TTS_PLAYBACK_POLL_MS <= 40

    def test_streaming_chunk_pops_complete_sentence(self):
        text = (
            "Esta frase ja tem tamanho suficiente para iniciar a voz. "
            "Esta parte deve ficar para depois."
        )

        chunk, remaining = pop_ready_tts_chunk(text)

        assert chunk == "Esta frase ja tem tamanho suficiente para iniciar a voz."
        assert remaining == "Esta parte deve ficar para depois."

    def test_streaming_chunk_falls_back_to_word_boundary(self):
        text = "palavra " * 80

        chunk, remaining = pop_ready_tts_chunk(text)

        assert chunk is not None
        assert len(chunk) <= TTS_STREAM_MAX_CHARS
        assert remaining

    def test_prepares_business_text_for_more_natural_speech(self):
        text = "O PDF tem R$ 120,50 e 15% de desconto. IA e LLM ajudam."

        spoken = prepare_tts_text_for_speech(text)

        assert "P D F" in spoken
        assert "120, 50 reais" in spoken
        assert "15 por cento" in spoken
        assert "inteligencia artificial" in spoken
        assert "modelo de linguagem" in spoken


class TestTTSProviderAbstraction:
    def test_normalizes_provider_aliases(self):
        assert normalize_tts_provider("edge") == "edge-tts"
        assert normalize_tts_provider("omni_voice") == "omnivoice"

    def test_lists_edge_voice_profiles(self):
        profiles = available_tts_profiles("edge")

        assert profiles
        assert all(profile.provider == "edge-tts" for profile in profiles)
        assert any(profile.id == "natural_male_br" for profile in profiles)

    def test_resolves_voice_profile_by_id(self):
        profile = resolve_tts_profile("natural_male_br")

        assert profile is not None
        assert profile.voice == "pt-BR-AntonioNeural"
        assert profile.experimental is False

    def test_factory_creates_edge_provider(self):
        provider = create_tts_provider(TTSVoiceConfig(provider="edge"))

        assert isinstance(provider, EdgeTTSProvider)

    def test_factory_keeps_future_engines_explicit(self):
        provider = create_tts_provider(TTSVoiceConfig(provider="omnivoice"))

        assert isinstance(provider, PlaceholderTTSProvider)


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
