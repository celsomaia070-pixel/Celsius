"""Tests for configuration module."""
from pathlib import Path

from core.config import ModelConfig, Settings, _get_base_dir


class TestConfig:
    def test_settings_creation(self):
        settings = Settings()
        assert settings.default_llm_model == "gemma3:12b"
        assert settings.embedding_model == "all-MiniLM-L6-v2"
        assert settings.base_dir is not None
        assert isinstance(settings.base_dir, Path)

    def test_available_models(self):
        settings = Settings()
        models = settings.available_models
        assert len(models) == 7
        assert all(isinstance(m, ModelConfig) for m in models)
        assert models[0].id == "gemma3:12b"
        assert "Gemma" in models[0].name

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


class TestBaseDir:
    def test_get_base_dir_not_frozen(self, monkeypatch):
        # Not frozen - should return parent of __file__
        monkeypatch.setattr("sys.frozen", False, raising=False)
        base = _get_base_dir()
        assert base.name == "PythonProject" or base.parent.name == "PythonProject"


class TestModelConfig:
    def test_model_config(self):
        model = ModelConfig(id="test:1b", name="Test Model")
        assert model.id == "test:1b"
        assert model.name == "Test Model"
