"""Tests for configuration module."""
from pathlib import Path

from core.config import GGUFModel, GGUF_MODELS, Settings, _get_base_dir, get_model_by_id


class TestConfig:
    def test_settings_creation(self):
        settings = Settings()
        assert settings.default_llm_model == "qwen2.5-vl-7b-q4km"
        assert settings.embedding_model == "paraphrase-multilingual-MiniLM-L12-v2"
        assert settings.base_dir is not None
        assert isinstance(settings.base_dir, Path)

    def test_gguf_models_registry(self):
        assert len(GGUF_MODELS) >= 9
        assert all(isinstance(m, GGUFModel) for m in GGUF_MODELS)
        assert GGUF_MODELS[0].id == "qwen2.5-vl-7b-q4km"
        assert "Qwen" in GGUF_MODELS[0].name

    def test_get_model_by_id(self):
        model = get_model_by_id("qwen2.5-vl-7b-q5km")
        assert model is not None
        assert model.quant == "Q5_K_M"
        assert get_model_by_id("nonexistent") is None

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
        path = settings.get_model_path("qwen2.5-vl-7b-q4km")
        assert path.name == "qwen2.5-vl-7b-q4_k_m.gguf"

    def test_gguf_model_display_name(self):
        model = GGUF_MODELS[0]
        assert "Q4_K_M" in model.display_name
        assert "Qwen" in model.display_name


class TestBaseDir:
    def test_get_base_dir_not_frozen(self, monkeypatch):
        monkeypatch.setattr("sys.frozen", False, raising=False)
        base = _get_base_dir()
        assert base.name == "PythonProject" or base.parent.name == "PythonProject"


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
