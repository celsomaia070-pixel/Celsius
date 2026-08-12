"""Tests for configuration module."""

from pathlib import Path

import core.config
from core.config import GGUF_MODELS, GGUFModel, Settings, _get_base_dir, get_model_by_id


class TestConfig:
    def test_settings_creation(self):
        settings = Settings()
        assert settings.default_llm_model == "qwen2.5-vl-7b-q4km"
        assert settings.embedding_model == "qwen3-embedding-0.6b"
        assert settings.base_dir is not None
        assert isinstance(settings.base_dir, Path)

    def test_gguf_models_registry(self):
        assert len(GGUF_MODELS) >= 14
        assert all(isinstance(m, GGUFModel) for m in GGUF_MODELS)
        assert GGUF_MODELS[0].id == "qwen3-4b-q4km"
        assert get_model_by_id("qwen3-8b-q4km") is not None
        assert get_model_by_id("deepseek-r1-distill-qwen-7b-q4km") is not None

    def test_get_model_by_id(self):
        model = get_model_by_id("qwen2.5-vl-7b-q5km")
        assert model is not None
        assert model.quant == "Q5_K_M"
        assert get_model_by_id("nonexistent") is None

    def test_qwen_omni_hf_file_uses_repository_casing(self):
        model = get_model_by_id("qwen2.5-omni-7b-q4km")
        assert model is not None
        assert model.hf_file == "Qwen2.5-Omni-7B-Q4_K_M.gguf"
        assert model.chat_format is None

    def test_qwen_vl_higher_quantizations_use_available_repository(self):
        for model_id in ("qwen2.5-vl-7b-q5km", "qwen2.5-vl-7b-q6k"):
            model = get_model_by_id(model_id)
            assert model is not None
            assert model.hf_repo == "unsloth/Qwen2.5-VL-7B-Instruct-GGUF"

    def test_set_llm_model(self):
        settings = Settings()
        settings.set_llm_model("test-model")
        assert settings.llm_model == "test-model"

    def test_properties(self):
        settings = Settings()
        assert len(settings.all_extensions) > 0
        assert ".pdf" in settings.all_extensions
        assert "*" in settings.file_filter
        assert ".pdf" in settings.file_filter

    def test_post_init_files(self):
        settings = Settings()
        assert settings.memorias_file.name == "memorias.json"
        assert settings.chats_file.name == "chats.json"
        assert settings.audio_temp_file.name == "temp_kfu_voice.mp3"
        assert settings.audio_mic_file.name == "temp_audio.wav"

    def test_model_path(self):
        settings = Settings()
        path = settings.get_model_path("qwen3-8b-q4km")
        assert path.name == "qwen3-8b-instruct-q4_k_m.gguf"

    def test_gguf_model_display_name(self):
        model = GGUF_MODELS[0]
        assert "Q4_K_M" in model.display_name
        assert "Qwen" in model.display_name


class TestBaseDir:
    def test_get_base_dir_not_frozen(self, monkeypatch):
        monkeypatch.setattr("sys.frozen", False, raising=False)
        base = _get_base_dir()
        expected = Path(core.config.__file__).resolve().parent.parent
        assert base == expected


class TestGGUFModel:
    def test_gguf_model(self):
        model = GGUFModel(
            id="test:1b",
            name="Test Model",
            category="fast",
            filename="test.gguf",
            hf_repo="test/repo",
            hf_file="test.gguf",
            size_gb=1.0,
            quant="Q4_K_M",
        )
        assert model.id == "test:1b"
        assert model.name == "Test Model"
        assert model.category == "fast"
