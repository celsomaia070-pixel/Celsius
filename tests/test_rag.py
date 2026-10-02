import gc
import tempfile
from pathlib import Path

import pytest

from ai.rag import RAGService
from core.config import Settings
from core.decisions import DecisionClient, RagGateResult
from core.settings import DecisionLayerSettings


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


class TestRagRelevanceGate:
    def _candidates(self) -> list[dict[str, str]]:
        return [
            {"id": "a", "document": "trecho a"},
            {"id": "b", "document": "trecho b"},
            {"id": "c", "document": "trecho c"},
        ]

    def test_disabled_layer_keeps_all_without_calling_decision(
        self, rag_service: RAGService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise AssertionError("gate must not call the decision layer when disabled")

        monkeypatch.setattr("ai.rag.evaluate_rag_chunk", boom)
        kept = rag_service._rag_relevance_gate("consulta", self._candidates(), DecisionClient())
        assert [c["id"] for c in kept] == ["a", "b", "c"]

    def test_chunks_are_pruned_only_when_the_verdict_says_so(
        self, rag_service: RAGService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rag_service.settings.decision = DecisionLayerSettings(enabled=True, rag_max_gated_chunks=5)

        def evaluate(
            client: DecisionClient,
            settings: DecisionLayerSettings,
            *,
            query: str,
            chunk: str,
        ) -> RagGateResult:
            keep = chunk != "trecho b"
            return RagGateResult(keep=keep, pruned=not keep, normalized=0.1 if keep else 0.0)

        monkeypatch.setattr("ai.rag.evaluate_rag_chunk", evaluate)
        kept = rag_service._rag_relevance_gate("consulta", self._candidates(), DecisionClient())
        assert [c["id"] for c in kept] == ["a", "c"]

    def test_scoring_is_capped_to_bound_latency(
        self, rag_service: RAGService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rag_service.settings.decision = DecisionLayerSettings(enabled=True, rag_max_gated_chunks=2)
        calls: list[str] = []

        def evaluate(
            client: DecisionClient,
            settings: DecisionLayerSettings,
            *,
            query: str,
            chunk: str,
        ) -> RagGateResult:
            calls.append(chunk)
            return RagGateResult(keep=True, normalized=1.0)

        monkeypatch.setattr("ai.rag.evaluate_rag_chunk", evaluate)
        candidates = self._candidates()
        kept = rag_service._rag_relevance_gate("consulta", candidates, DecisionClient())
        assert [c["id"] for c in kept] == ["a", "b", "c"]
        assert calls == ["trecho a", "trecho b"]
