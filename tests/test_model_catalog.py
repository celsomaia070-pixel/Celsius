"""Tests for the Celsius product model catalog."""

from core.model_catalog import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    FAST_LLM_MODEL,
    MODEL_PRESETS,
    REASONING_LLM_MODEL,
    VISION_LLM_MODEL,
    ModelCapability,
    ModelPreset,
    get_model_spec,
    get_preset_model,
    models_with_capability,
    user_facing_model_modes,
)


class TestModelCatalog:
    def test_default_models_follow_celsius_product_strategy(self):
        assert DEFAULT_LLM_MODEL == "qwen2.5-vl-7b-q4km"
        assert FAST_LLM_MODEL == "qwen3-4b-q4km"
        assert REASONING_LLM_MODEL == "deepseek-r1-distill-qwen-7b-q4km"
        assert VISION_LLM_MODEL == "qwen2.5-vl-7b-q4km"
        assert DEFAULT_EMBEDDING_MODEL == "qwen3-embedding-0.6b"

    def test_user_facing_presets_hide_technical_names(self):
        modes = user_facing_model_modes()

        assert modes[ModelPreset.FAST.value] == "Rapido"
        assert modes[ModelPreset.BALANCED.value] == "Equilibrado"
        assert get_preset_model(ModelPreset.BALANCED) == DEFAULT_LLM_MODEL
        assert MODEL_PRESETS[ModelPreset.DOCUMENTS] == VISION_LLM_MODEL

    def test_model_specs_have_business_capabilities(self):
        balanced = get_model_spec(DEFAULT_LLM_MODEL)
        vision = get_model_spec(VISION_LLM_MODEL)

        assert balanced is not None
        assert balanced.has(ModelCapability.CHAT)
        assert vision is not None
        assert vision.has(ModelCapability.VISION)
        assert vision.has(ModelCapability.DOCUMENTS)

    def test_embedding_models_are_separate_from_chat_models(self):
        embeddings = models_with_capability(ModelCapability.EMBEDDING)

        assert embeddings
        assert any(model.id == DEFAULT_EMBEDDING_MODEL for model in embeddings)
        assert all(not model.has(ModelCapability.CHAT) for model in embeddings)
