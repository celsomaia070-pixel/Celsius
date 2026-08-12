"""Tests for embedding model helpers."""

from core.embeddings import (
    clear_sentence_transformer_cache,
    create_sentence_transformer,
    resolve_embedding_model_name,
)


class TestEmbeddingModelResolution:
    def test_resolves_qwen3_embedding_alias(self):
        assert resolve_embedding_model_name("qwen3-embedding-0.6b") == ("Qwen/Qwen3-Embedding-0.6B")

    def test_resolves_qwen3_embedding_alias_case_insensitive(self):
        assert resolve_embedding_model_name("QWEN3-EMBEDDING-4B") == ("Qwen/Qwen3-Embedding-4B")

    def test_keeps_custom_sentence_transformer_model(self):
        model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        assert resolve_embedding_model_name(model) == model

    def test_create_sentence_transformer_uses_resolved_model(self, monkeypatch):
        loaded = []
        clear_sentence_transformer_cache()

        class DummySentenceTransformer:
            def __init__(self, model_name, **kwargs):
                loaded.append((model_name, kwargs))

        monkeypatch.setattr(
            "sentence_transformers.SentenceTransformer",
            DummySentenceTransformer,
        )

        create_sentence_transformer("qwen3-embedding-0.6b")

        assert loaded == [("Qwen/Qwen3-Embedding-0.6B", {"local_files_only": False})]
        clear_sentence_transformer_cache()

    def test_reuses_same_embedding_model(self, monkeypatch):
        loaded = []
        clear_sentence_transformer_cache()

        class DummySentenceTransformer:
            def __init__(self, model_name, **kwargs):
                loaded.append((model_name, kwargs))

        monkeypatch.setattr(
            "sentence_transformers.SentenceTransformer",
            DummySentenceTransformer,
        )

        first = create_sentence_transformer("qwen3-embedding-0.6b")
        second = create_sentence_transformer("Qwen/Qwen3-Embedding-0.6B")

        assert first is second
        assert loaded == [("Qwen/Qwen3-Embedding-0.6B", {"local_files_only": False})]
        clear_sentence_transformer_cache()

    def test_frozen_runtime_never_downloads_embedding_model(self, monkeypatch):
        loaded = []
        clear_sentence_transformer_cache()

        class DummySentenceTransformer:
            def __init__(self, model_name, **kwargs):
                loaded.append((model_name, kwargs))

        monkeypatch.setattr(
            "sentence_transformers.SentenceTransformer",
            DummySentenceTransformer,
        )
        monkeypatch.setattr("sys.frozen", True, raising=False)

        create_sentence_transformer("qwen3-embedding-0.6b")

        assert loaded == [("Qwen/Qwen3-Embedding-0.6B", {"local_files_only": True})]
        clear_sentence_transformer_cache()
