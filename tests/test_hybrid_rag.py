"""Tests for ai.rag (RAGService: BM25, dense search, hybrid, re-ranking).

These tests mock the heavy ML dependencies (SentenceTransformer, CrossEncoder,
ChromaDB) so they run without GPU or model downloads.
"""

import gc
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from rank_bm25 import BM25Okapi

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        yield Path(d)


@pytest.fixture
def rag_service(tmp_dir):
    """Provide an RAGService with all heavy dependencies mocked."""
    from core.config import Settings

    settings = Settings()
    settings.base_dir = tmp_dir

    with (
        patch("ai.rag._rag_search_cb") as mock_cb_search,
        patch("ai.rag._rag_index_cb") as mock_cb_index,
    ):
        mock_cb_search.allow_request.return_value = True
        mock_cb_index.allow_request.return_value = True
        mock_cb_search.record_success = MagicMock()
        mock_cb_search.record_failure = MagicMock()
        mock_cb_index.record_success = MagicMock()
        mock_cb_index.record_failure = MagicMock()

        from ai.rag import RAGService

        service = RAGService(settings=settings)

        # Mock the embedding model
        fake_model = MagicMock()

        def fake_encode(texts, **kw):
            arr = np.random.RandomState(42).rand(len(texts), 128)
            return arr  # numpy array, supports .tolist()

        fake_model.encode = MagicMock(side_effect=fake_encode)
        service._model = fake_model

        # Mock the cross encoder
        fake_ce = MagicMock()

        def fake_predict(pairs, **kw):
            scores = []
            for q, doc in pairs:
                q_words = set(q.lower().split())
                d_words = set(doc.lower().split())
                scores.append(float(len(q_words & d_words)))
            return np.array(scores)

        fake_ce.predict = MagicMock(side_effect=fake_predict)
        service._cross_encoder = fake_ce

        yield service
        service.close()
        del service
        gc.collect()


def _seed_bm25(service, documents: list[str], doc_name: str = "test_doc"):
    """Seed the BM25 index directly (bypasses ChromaDB)."""
    from ai.rag import _tokenize_for_bm25

    ids = [f"{doc_name}_chunk_{i}" for i in range(len(documents))]
    service._bm25_doc_ids = ids
    service._bm25_corpus_tokens = [_tokenize_for_bm25(doc) for doc in documents]
    service._bm25 = BM25Okapi(service._bm25_corpus_tokens)


# ── BM25 search tests ────────────────────────────────────────────────


class TestBM25Search:
    def test_bm25_returns_relevant(self, rag_service):
        _seed_bm25(
            rag_service,
            [
                "Python is a popular programming language",
                "JavaScript is used for web development",
                "Rust is a systems programming language",
            ],
        )
        ids, scores = rag_service._bm25_search("python programming", 3)
        assert len(ids) > 0
        assert ids[0] == "test_doc_chunk_0"

    def test_bm25_empty_index(self, rag_service):
        ids, scores = rag_service._bm25_search("anything", 5)
        assert ids == []
        assert scores == []

    def test_bm25_no_match(self, rag_service):
        _seed_bm25(rag_service, ["hello world"])
        ids, scores = rag_service._bm25_search("quantum physics", 5)
        assert ids == [] or all(s <= 0 for s in scores)

    def test_bm25_ranking_order(self, rag_service):
        _seed_bm25(
            rag_service,
            [
                "data science and machine learning",
                "cooking recipes for dinner",
                "data analysis and data visualization",
            ],
        )
        ids, scores = rag_service._bm25_search("data", 3)
        assert len(ids) >= 2
        cooking_pos = next((i for i, _id in enumerate(ids) if "chunk_1" in _id), None)
        if cooking_pos is not None:
            assert cooking_pos > 0


# ── Normalize scores ─────────────────────────────────────────────────


class TestNormalizeScores:
    def test_empty(self, rag_service):
        assert rag_service._normalize_scores([]) == []

    def test_single_value(self, rag_service):
        result = rag_service._normalize_scores([5.0])
        assert result == [1.0]

    def test_same_values(self, rag_service):
        result = rag_service._normalize_scores([3.0, 3.0, 3.0])
        assert all(r == 1.0 for r in result)

    def test_range_0_1(self, rag_service):
        result = rag_service._normalize_scores([1.0, 5.0, 3.0])
        assert all(0.0 <= r <= 1.0 for r in result)
        assert result[1] == 1.0
        assert result[0] == 0.0

    def test_preserves_order(self, rag_service):
        result = rag_service._normalize_scores([1.0, 2.0, 3.0])
        assert result[0] < result[1] < result[2]


# ── Chunking tests ───────────────────────────────────────────────────


class TestChunking:
    def test_semantic_chunk_empty(self, rag_service):
        assert rag_service._chunk_text_semantic("") == []
        assert rag_service._chunk_text_semantic("   ") == []

    def test_semantic_chunk_short_text(self, rag_service):
        chunks = rag_service._chunk_text_semantic("Hello world")
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_semantic_chunk_respects_sections(self, rag_service):
        text = "Section one content.\n\nSection two content.\n\nSection three content."
        chunks = rag_service._chunk_text_semantic(text)
        assert len(chunks) >= 1

    def test_legacy_chunk_text(self, rag_service):
        text = "word " * 2000
        chunks = rag_service._chunk_text(text, size=500, overlap=50)
        assert len(chunks) > 1

    def test_legacy_chunk_single(self, rag_service):
        chunks = rag_service._chunk_text("short", size=500, overlap=50)
        assert chunks == ["short"]

    def test_legacy_chunk_empty(self, rag_service):
        assert rag_service._chunk_text("   ", size=500, overlap=50) == []


# ── Re-ranking tests ─────────────────────────────────────────────────


class TestReranking:
    def test_rerank_returns_subset(self, rag_service):
        candidates = [
            {"id": "c1", "document": "Python is great", "score": 0.5, "dense_dist": 0.3},
            {"id": "c2", "document": "Cooking food", "score": 0.3, "dense_dist": 0.5},
            {"id": "c3", "document": "Python programming", "score": 0.4, "dense_dist": 0.4},
        ]
        result = rag_service._rerank("python", candidates, top_k=2)
        assert len(result) == 2

    def test_rerank_changes_order(self, rag_service):
        candidates = [
            {"id": "c1", "document": "Python is great for coding", "score": 0.3},
            {"id": "c2", "document": "Cooking pasta recipes dinner", "score": 0.8},
        ]
        result = rag_service._rerank("python coding", candidates, top_k=2)
        assert result[0]["id"] == "c1"

    def test_rerank_with_empty(self, rag_service):
        result = rag_service._rerank("query", [], top_k=5)
        assert result == []

    def test_rerank_adds_rerank_score(self, rag_service):
        candidates = [
            {"id": "c1", "document": "Python is great", "score": 0.5},
        ]
        result = rag_service._rerank("python", candidates, top_k=5)
        assert "rerank_score" in result[0]

    def test_rerank_no_documents_fallback(self, rag_service):
        candidates = [
            {"id": "c1", "document": None, "score": 0.5},
        ]
        result = rag_service._rerank("query", candidates, top_k=5)
        assert len(result) >= 1


# ── Search context (integration) ─────────────────────────────────────


class TestSearchContext:
    def test_empty_returns_empty(self, rag_service):
        result = rag_service.search_context("anything")
        assert result == []


# ── Close ─────────────────────────────────────────────────────────────


class TestClose:
    def test_close_resets_state(self, rag_service):
        rag_service.close()
        assert rag_service._client is None
        assert rag_service._collection is None
        assert rag_service._bm25 is None
        assert rag_service._bm25_doc_ids == []
