import gc
import tempfile
from pathlib import Path

import pytest

from ai.rag import RAGService
from core.config import Settings


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        yield Path(d)


@pytest.fixture
def mock_settings(tmp_dir):
    settings = Settings()
    settings.base_dir = tmp_dir
    settings.embedding_model = "paraphrase-multilingual-MiniLM-L12-v2"
    return settings


@pytest.fixture
def rag_service(mock_settings):
    service = RAGService(settings=mock_settings)
    yield service
    service.close()
    del service
    gc.collect()


class TestRAGService:
    def test_init_creates_collection(self, rag_service):
        assert rag_service._collection is not None

    def test_chunk_text(self, rag_service):
        text = "word " * 2000
        chunks = rag_service._chunk_text(text, size=500, overlap=50)
        assert len(chunks) > 1

    def test_chunk_text_small(self, rag_service):
        chunks = rag_service._chunk_text("Hello world", size=500, overlap=50)
        assert chunks == ["Hello world"]

    def test_chunk_empty(self, rag_service):
        chunks = rag_service._chunk_text("   ", size=500, overlap=50)
        assert chunks == []

    def test_search_empty_collection(self, rag_service):
        result = rag_service.search_context("test")
        assert result == []

    def test_list_documents_empty(self, rag_service):
        result = rag_service.list_documents()
        assert "Nenhum documento" in result

    def test_remove_nonexistent(self, rag_service):
        result = rag_service.remove_document("nonexistent")
        assert "nao encontrado" in result.lower()
