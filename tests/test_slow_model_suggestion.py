"""Tests for slow-model suggestion logic."""

from pathlib import Path

from core.config import GGUF_MODELS, GGUFModel, get_model_by_id
from core.slow_model_suggestion import (
    estimate_output_tokens,
    suggest_lighter_model,
    suggestions_enabled,
)

_HW_TPS = 10  # hardcoded expected tps for the tests


class TestSuggestLighterModel:
    def test_no_suggestion_when_fast_enough(self):
        elapsed = 10.0  # 60 tokens in 10s → 6 tps, acima de 0.5×10=5
        suggestion = suggest_lighter_model(
            used_model_id="qwen3-8b-q4km",
            elapsed_seconds=elapsed,
            estimated_output_tokens=60,
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
            installed_ids={"qwen3-8b-q4km", "gemma3-4b-q4km"},
        )
        assert suggestion is None

    def test_no_suggestion_for_short_response(self):
        suggestion = suggest_lighter_model(
            used_model_id="qwen3-8b-q4km",
            elapsed_seconds=2.0,
            estimated_output_tokens=40,
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
            installed_ids={"qwen3-8b-q4km", "gemma3-4b-q4km"},
        )
        assert suggestion is None

    def test_suggestion_when_slow_and_lighter_installed(self):
        suggestion = suggest_lighter_model(
            used_model_id="qwen3-8b-q4km",
            elapsed_seconds=40.0,
            estimated_output_tokens=20,  # 0.5 tps, far below expected 10
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
            installed_ids={"qwen3-8b-q4km", "gemma3-4b-q4km"},
        )
        assert suggestion is not None
        assert suggestion.suggested_model_id == "gemma3-4b-q4km"
        assert suggestion.used_model_id == "qwen3-8b-q4km"

    def test_suggests_lightest_installed(self):
        suggestion = suggest_lighter_model(
            used_model_id="qwen3-8b-q4km",
            elapsed_seconds=40.0,
            estimated_output_tokens=20,
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
            installed_ids={
                "qwen3-8b-q4km",
                "gemma3-4b-q4km",
                "llama3.2-3b-q5km",
            },
        )
        assert suggestion is not None
        assert suggestion.suggested_model_id == "llama3.2-3b-q5km"

    def test_no_suggestion_when_used_is_lightest_installed(self):
        suggestion = suggest_lighter_model(
            used_model_id="llama3.2-3b-q5km",
            elapsed_seconds=40.0,
            estimated_output_tokens=20,
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
            installed_ids={"gemma3-4b-q4km", "llama3.2-3b-q5km"},
        )
        assert suggestion is None

    def test_no_suggestion_for_unknown_model(self):
        suggestion = suggest_lighter_model(
            used_model_id="nao-existe",
            elapsed_seconds=40.0,
            estimated_output_tokens=20,
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
            installed_ids={"gemma3-4b-q4km"},
        )
        assert suggestion is None

    def test_no_suggestion_without_installed_ids_and_no_dir(self):
        suggestion = suggest_lighter_model(
            used_model_id="qwen3-8b-q4km",
            elapsed_seconds=40.0,
            estimated_output_tokens=20,
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
        )
        assert suggestion is None

    def test_respects_min_elapsed_seconds_param(self):
        suggestion = suggest_lighter_model(
            used_model_id="qwen3-8b-q4km",
            elapsed_seconds=6.0,
            estimated_output_tokens=20,  # 3.3 tps, abaixo de 0.5×10=5
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
            installed_ids={"qwen3-8b-q4km", "gemma3-4b-q4km"},
            min_elapsed_seconds=2.5,
        )
        assert suggestion is not None

    def test_installed_ids_derived_from_resources_dir(self, tmp_path):
        model = get_model_by_id("gemma3-4b-q4km")
        (tmp_path / model.filename).touch()
        suggestion = suggest_lighter_model(
            used_model_id="qwen3-8b-q4km",
            elapsed_seconds=40.0,
            estimated_output_tokens=20,
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
            resources_dir=tmp_path,
        )
        assert suggestion is not None
        assert suggestion.suggested_model_id == "gemma3-4b-q4km"

    def test_message_is_formed(self):
        suggestion = suggest_lighter_model(
            used_model_id="qwen3-8b-q4km",
            elapsed_seconds=40.0,
            estimated_output_tokens=20,
            expected_tokens_per_sec=_HW_TPS,
            catalog=GGUF_MODELS,
            installed_ids={"qwen3-8b-q4km", "gemma3-4b-q4km"},
        )
        assert suggestion is not None
        text = suggestion.message
        assert "Qwen3 8B" in text
        assert "Gemma 3 4B" in text
        assert "tokens/s" in text


class TestEstimateOutputTokens:
    def test_zero_length(self):
        assert estimate_output_tokens("") == 1

    def test_approximate(self):
        assert estimate_output_tokens("a" * 100) == 25


class TestSuggestionsEnabled:
    def test_defaults_to_true(self):
        settings = type("S", (), {})()
        assert suggestions_enabled(settings) is True

    def test_false_when_disabled(self):
        settings = type("S", (), {"slow_model_suggestions": False})()
        assert suggestions_enabled(settings) is False

    def test_false_when_feature_flag_disables(self):
        features = type("F", (), {"slow_model_suggestions": False})()
        settings = type("S", (), {"features": features})()
        assert suggestions_enabled(settings) is False
