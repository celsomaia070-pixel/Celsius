"""Hybrid RAG Service with dense vector search, BM25 keyword search, and cross-encoder re-ranking.

Implements:
- Semantic chunking (respects document structure)
- Dense vector search via ChromaDB
- BM25 keyword search via rank-bm25
- Hybrid scoring: configurable weighted combination of BM25 + dense
- Cross-encoder re-ranking using sentence-transformers CrossEncoder
- Circuit breaker protection
- Thread-safe with RLock
"""

import re
import threading
from typing import Any

import chromadb
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

from core.circuit_breaker import get_circuit_breaker
from core.settings import get_settings

try:
    from core.logging_config import get_logger

    logger = get_logger(__name__)
except Exception:
    import logging

    logger = logging.getLogger(__name__)

# Circuit breaker for RAG search (ChromaDB + embeddings)
_rag_search_cb = get_circuit_breaker("rag:search", failure_threshold=5, recovery_timeout=60)
_rag_index_cb = get_circuit_breaker("rag:index", failure_threshold=3, recovery_timeout=120)


def _tokenize_for_bm25(text: str) -> list[str]:
    """Simple whitespace + lowercasing tokenizer for BM25."""
    return text.lower().split()


class RAGService:
    """Thread-safe Hybrid RAG service with ChromaDB, BM25, and cross-encoder re-ranking."""

    CHUNK_SIZE = 600
    CHUNK_OVERLAP = 80
    TOP_K = 5
    FINAL_TOP_K = 3
    DISTANCE_THRESHOLD = 1.5

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._model: SentenceTransformer | None = None
        self._cross_encoder: CrossEncoder | None = None
        self._client: chromadb.PersistentClient | None = None
        self._collection: chromadb.Collection | None = None
        self._lock = threading.RLock()

        # BM25 state
        self._bm25: BM25Okapi | None = None
        self._bm25_corpus_tokens: list[list[str]] = []
        self._bm25_doc_ids: list[str] = []
        self._bm25_documents_by_id: dict[str, str] = {}
        self._bm25_metadata_by_id: dict[str, dict[str, Any]] = {}

        rag_settings = getattr(self.settings, "rag", self.settings)
        self.CHUNK_SIZE = getattr(rag_settings, "chunk_size", self.CHUNK_SIZE)
        self.CHUNK_OVERLAP = getattr(rag_settings, "chunk_overlap", self.CHUNK_OVERLAP)
        self.TOP_K = getattr(rag_settings, "top_k", self.TOP_K)
        self.FINAL_TOP_K = getattr(rag_settings, "final_top_k", self.FINAL_TOP_K)
        self.DISTANCE_THRESHOLD = getattr(
            rag_settings,
            "distance_threshold",
            self.DISTANCE_THRESHOLD,
        )
        self._bm25_weight = getattr(rag_settings, "bm25_weight", 0.3)
        self._dense_weight = getattr(rag_settings, "dense_weight", 0.7)
        self._enable_hybrid = getattr(rag_settings, "enable_hybrid_search", True)
        self._enable_reranking = getattr(rag_settings, "enable_reranking", True)
        self._reranker_model_name = getattr(
            rag_settings,
            "reranker_model",
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
        )
        self._rerank_top_k = getattr(rag_settings, "rerank_top_k", 10)

        # Normalize weights
        total_w = self._bm25_weight + self._dense_weight
        if total_w > 0:
            self._bm25_weight /= total_w
            self._dense_weight /= total_w

        self._init_collection()

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.settings.embedding_model)
        return self._model

    def _get_cross_encoder(self) -> CrossEncoder:
        if self._cross_encoder is None:
            logger.info("lazy_loading_cross_encoder model=%s", self._reranker_model_name)
            self._cross_encoder = CrossEncoder(self._reranker_model_name)
        return self._cross_encoder

    def _init_collection(self) -> None:
        with self._lock:
            if self._client is None:
                persist_dir = self.settings.base_dir / "chroma_db"
                self._client = chromadb.PersistentClient(path=str(persist_dir))
                self._collection = self._client.get_or_create_collection(
                    name="documentos",
                    metadata={"hnsw:space": "cosine"},
                )
                self._rebuild_bm25_index()

    @property
    def collection(self):
        self._init_collection()
        return self._collection

    def _rebuild_bm25_index(self) -> None:
        """Rebuild BM25 index from all documents currently in ChromaDB."""
        try:
            all_data = self.collection.get()
            if not all_data["ids"]:
                self._bm25 = None
                self._bm25_corpus_tokens = []
                self._bm25_doc_ids = []
                self._bm25_documents_by_id = {}
                self._bm25_metadata_by_id = {}
                return

            self._bm25_doc_ids = all_data["ids"]
            documents = all_data["documents"]
            metadatas = all_data.get("metadatas") or [{} for _ in documents]
            self._bm25_corpus_tokens = [_tokenize_for_bm25(doc) for doc in documents]
            self._bm25_documents_by_id = dict(zip(self._bm25_doc_ids, documents, strict=False))
            self._bm25_metadata_by_id = dict(zip(self._bm25_doc_ids, metadatas, strict=False))
            self._bm25 = BM25Okapi(self._bm25_corpus_tokens)
            logger.info("bm25_index_rebuilt doc_count=%s", len(self._bm25_doc_ids))
        except Exception as e:
            logger.warning("bm25_rebuild_failed error=%s", e)
            self._bm25 = None

    def _chunk_text_semantic(self, text: str) -> list[str]:
        """Semantic chunking that respects document structure.

        Strategy:
        1. Split by major section breaks (\\n\\n, headers)
        2. Within sections, split by sentences
        3. Merge small sentences into chunks of target size
        4. Add overlap for context continuity
        """
        if not text or not text.strip():
            return []

        # Step 1: Split by major section breaks
        sections = re.split(r"\n{2,}", text)

        # Step 2: Further split long sections by sentences
        chunks = []
        for section in sections:
            section = section.strip()
            if not section:
                continue

            # If section is small enough, keep as-is
            if len(section) <= self.CHUNK_SIZE * 1.5:
                chunks.append(section)
                continue

            # Split by sentences (Portuguese/English)
            sentences = re.split(r"(?<=[.!?])\s+", section)

            # Step 3: Merge sentences into chunks
            current_chunk = []
            current_size = 0

            for sentence in sentences:
                sentence_size = len(sentence)

                if current_size + sentence_size > self.CHUNK_SIZE and current_chunk:
                    # Emit current chunk
                    chunks.append(" ".join(current_chunk))
                    # Keep last sentence for overlap
                    if len(current_chunk) > 1:
                        current_chunk = [current_chunk[-1]]
                        current_size = len(current_chunk[0])
                    else:
                        current_chunk = []
                        current_size = 0

                current_chunk.append(sentence)
                current_size += sentence_size

            # Emit final chunk
            if current_chunk:
                chunks.append(" ".join(current_chunk))

        # Step 4: Add overlap between chunks
        if len(chunks) <= 1:
            return chunks

        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            # Add last part of previous chunk as context
            prev_words = chunks[i - 1].split()[-20:]  # Last 20 words
            if prev_words:
                overlap_text = " ".join(prev_words) + " " + chunks[i]
                # Respect size limit
                if len(overlap_text) > self.CHUNK_SIZE * 1.5:
                    overlap_text = chunks[i]
                overlapped.append(overlap_text)
            else:
                overlapped.append(chunks[i])

        return overlapped

    def _chunk_text(self, text: str, size: int = None, overlap: int = None) -> list[str]:
        """Legacy character-based chunking (fallback)."""
        size = size or self.CHUNK_SIZE
        overlap = overlap or self.CHUNK_OVERLAP
        chunks = []
        start = 0
        while start < len(text):
            end = start + size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start = end - overlap
        return chunks

    def _dense_search(
        self,
        query: str,
        n_results: int,
    ) -> tuple[list[str], list[str], list[float], list[dict[str, Any]]]:
        """Run dense vector search against ChromaDB.

        Returns (doc_ids, documents, distances).
        """
        model = self._get_model()
        query_embedding = model.encode([query], show_progress_bar=False).tolist()
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=min(n_results, self.collection.count()),
        )
        doc_ids = results["ids"][0] if results["ids"] else []
        documents = results["documents"][0] if results["documents"] else []
        distances = results["distances"][0] if results["distances"] else []
        metadatas = results["metadatas"][0] if results.get("metadatas") else []
        return doc_ids, documents, distances, metadatas

    def _bm25_search(self, query: str, n_results: int) -> tuple[list[str], list[float]]:
        """Run BM25 keyword search.

        Returns (doc_ids, bm25_scores).
        """
        if self._bm25 is None or not self._bm25_doc_ids:
            return [], []

        query_tokens = _tokenize_for_bm25(query)
        scores = self._bm25.get_scores(query_tokens)

        # Get top-n indices sorted by score descending
        top_indices = np.argsort(scores)[::-1][:n_results]

        result_ids = []
        result_scores = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0:
                continue
            result_ids.append(self._bm25_doc_ids[idx])
            result_scores.append(score)

        return result_ids, result_scores

    def _normalize_scores(self, scores: list[float]) -> list[float]:
        """Min-max normalize scores to [0, 1]."""
        if not scores:
            return []
        min_s = min(scores)
        max_s = max(scores)
        if max_s - min_s < 1e-9:
            return [1.0] * len(scores)
        return [(s - min_s) / (max_s - min_s) for s in scores]

    def _hybrid_search(self, query: str, n_results: int) -> list[dict[str, Any]]:
        """Combine dense + BM25 search with weighted scoring.

        Returns a list of dicts with keys: id, document, score, dense_dist, bm25_score.
        """
        # Fetch extra candidates for better fusion
        fetch_k = max(n_results * 3, 15)

        # --- Dense search ---
        dense_ids, dense_docs, dense_dists, dense_metas = self._dense_search(query, fetch_k)
        # Convert cosine distance to similarity: sim = 1 - dist
        dense_sims = [1.0 - d for d in dense_dists]

        # --- BM25 search ---
        bm25_ids, bm25_raw_scores = self._bm25_search(query, fetch_k)

        # Build combined score map
        all_ids = set(dense_ids) | set(bm25_ids)
        combined: dict[str, dict[str, Any]] = {}
        for doc_id in all_ids:
            combined[doc_id] = {
                "id": doc_id,
                "document": None,
                "metadata": self._bm25_metadata_by_id.get(doc_id, {}),
                "dense_score": 0.0,
                "bm25_score": 0.0,
                "dense_dist": None,
            }

        # Fill dense scores (normalize)
        if dense_sims:
            norm_dense = self._normalize_scores(dense_sims)
            for doc_id, sim, dist, doc, meta in zip(
                dense_ids,
                norm_dense,
                dense_dists,
                dense_docs,
                dense_metas,
                strict=False,
            ):
                if doc_id in combined:
                    combined[doc_id]["dense_score"] = sim
                    combined[doc_id]["dense_dist"] = dist
                    combined[doc_id]["document"] = doc
                    combined[doc_id]["metadata"] = meta or {}

        # Fill BM25 scores (normalize)
        if bm25_raw_scores:
            norm_bm25 = self._normalize_scores(bm25_raw_scores)
            for doc_id, score in zip(bm25_ids, norm_bm25, strict=False):
                if doc_id in combined:
                    combined[doc_id]["bm25_score"] = score

        # If BM25 has no results, fall back to dense only
        if not bm25_ids:
            for item in combined.values():
                item["score"] = item["dense_score"]
        elif not dense_ids:
            # If dense has no results, fall back to BM25 only
            for item in combined.values():
                item["score"] = item["bm25_score"]
                item["document"] = self._bm25_documents_by_id.get(item["id"])
        else:
            dense_weight = self._dense_weight
            bm25_weight = self._bm25_weight
            # Weighted combination
            for item in combined.values():
                if item["document"] is None:
                    item["document"] = self._bm25_documents_by_id.get(item["id"])
                item["score"] = (
                    bm25_weight * item["bm25_score"] + dense_weight * item["dense_score"]
                )

        # Sort by combined score descending, take top-n
        ranked = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
        return ranked[:n_results]

    def _rerank(
        self, query: str, candidates: list[dict[str, Any]], top_k: int
    ) -> list[dict[str, Any]]:
        """Re-rank candidates using a cross-encoder model."""
        if not candidates:
            return []

        ce = self._get_cross_encoder()
        pairs = [(query, c["document"]) for c in candidates if c["document"]]
        if not pairs:
            return candidates[:top_k]

        ce_scores = ce.predict(pairs, show_progress_bar=False)

        for candidate, ce_score in zip(candidates, ce_scores, strict=False):
            candidate["rerank_score"] = float(ce_score)

        candidates.sort(key=lambda x: x.get("rerank_score", float("-inf")), reverse=True)
        return candidates[:top_k]

    def index_document(
        self, text: str, doc_name: str, metadata: dict[str, Any] | None = None
    ) -> int:
        if not _rag_index_cb.allow_request():
            logger.warning("rag_index_cb_open doc_name=%s", doc_name)
            return 0

        with self._lock:
            # Remove existing chunks for this document
            try:
                existing = self.collection.get(where={"nome_doc": doc_name})
                if existing["ids"]:
                    self.collection.delete(ids=existing["ids"])
            except Exception as e:
                logger.warning("failed_to_remove_existing_chunks doc_name=%s error=%s", doc_name, e)

            # Use semantic chunking
            chunks = self._chunk_text_semantic(text)
            if not chunks:
                # Fallback to character-based
                chunks = self._chunk_text(text)
            if not chunks:
                return 0

            try:
                model = self._get_model()
                embeddings = model.encode(chunks, show_progress_bar=False).tolist()
                ids = [f"{doc_name}_chunk_{i}" for i in range(len(chunks))]
                metadatas = [
                    {
                        "nome_doc": doc_name,
                        "chunk_index": i,
                        "char_count": len(chunk),
                        **(metadata or {}),
                    }
                    for i, chunk in enumerate(chunks)
                ]

                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=chunks,
                    metadatas=metadatas,
                )
                _rag_index_cb.record_success()

                # Rebuild BM25 index after adding new chunks
                self._rebuild_bm25_index()

                logger.info("document_indexed doc_name=%s chunks=%s", doc_name, len(chunks))
                return len(chunks)
            except Exception:
                _rag_index_cb.record_failure()
                raise

    def search_context(self, query: str, top_k: int = None) -> list[str]:
        """Search with hybrid approach: dense + BM25, then cross-encoder re-ranking."""
        if not _rag_search_cb.allow_request():
            logger.warning("rag_search_cb_open")
            return []

        with self._lock:
            top_k = top_k or self.TOP_K

            if self.collection.count() == 0:
                return []

            try:
                if self._enable_hybrid:
                    # Hybrid search: combine dense + BM25
                    rerank_pool = min(self._rerank_top_k, top_k * 3)
                    candidates = self._hybrid_search(query, rerank_pool)

                    # Apply distance threshold filter
                    candidates = [
                        c
                        for c in candidates
                        if c["dense_dist"] is None or c["dense_dist"] < self.DISTANCE_THRESHOLD
                    ]

                    # Re-rank with cross-encoder
                    if self._enable_reranking and candidates:
                        candidates = self._rerank(query, candidates, top_k)
                    else:
                        candidates = candidates[:top_k]
                else:
                    # Dense-only fallback
                    doc_ids, documents, distances, metadatas = self._dense_search(query, top_k)
                    candidates = [
                        {
                            "id": doc_id,
                            "document": doc,
                            "metadata": meta or {},
                            "dense_dist": dist,
                            "score": 1.0 - dist,
                        }
                        for doc_id, doc, dist, meta in zip(
                            doc_ids,
                            documents,
                            distances,
                            metadatas,
                            strict=False,
                        )
                        if dist < self.DISTANCE_THRESHOLD
                    ][:top_k]

                resultados = [
                    self._format_context_candidate(c) for c in candidates if c.get("document")
                ]
                _rag_search_cb.record_success()
                return resultados[: self.FINAL_TOP_K]
            except Exception as e:
                _rag_search_cb.record_failure()
                logger.warning("rag_search_failed error=%s", e)
                return []

    @staticmethod
    def _format_context_candidate(candidate: dict[str, Any]) -> str:
        meta = candidate.get("metadata") or {}
        source = meta.get("nome_doc") or candidate.get("id") or "documento"
        chunk_index = meta.get("chunk_index")
        if chunk_index is not None:
            return f"[Fonte: {source}, trecho {chunk_index}]\n{candidate['document']}"
        return f"[Fonte: {source}]\n{candidate['document']}"

    def list_documents(self) -> str:
        with self._lock:
            if self.collection.count() == 0:
                return "Nenhum documento indexado."

            all_data = self.collection.get()
            names = set()
            for meta in all_data["metadatas"]:
                names.add(meta.get("nome_doc", "desconhecido"))

            result = f"Documentos indexados ({len(names)}):\n"
            for name in sorted(names):
                result += f"- {name}\n"
            return result

    def remove_document(self, doc_name: str) -> str:
        with self._lock:
            try:
                existing = self.collection.get(where={"nome_doc": doc_name})
                if existing["ids"]:
                    self.collection.delete(ids=existing["ids"])
                    # Rebuild BM25 after removal
                    self._rebuild_bm25_index()
                    return f"Documento '{doc_name}' removido ({len(existing['ids'])} chunks)."
                return f"Documento '{doc_name}' nao encontrado."
            except Exception as e:
                return f"Erro ao remover: {e}"

    def close(self) -> None:
        with self._lock:
            if self._client:
                self._client = None
                self._collection = None
                self._bm25 = None
                self._bm25_corpus_tokens = []
                self._bm25_doc_ids = []
                self._cross_encoder = None


# Global instance for backward compatibility
_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


# Backward compatibility functions
def indexar_documento(texto: str, nome_doc: str, metadados: dict[str, Any] | None = None) -> int:
    return get_rag_service().index_document(texto, nome_doc, metadados)


def buscar_contexto(query: str, top_k: int = None) -> list[str]:
    return get_rag_service().search_context(query, top_k)


def listar_documentos() -> str:
    return get_rag_service().list_documents()


def remover_documento(nome_doc: str) -> str:
    return get_rag_service().remove_document(nome_doc)
