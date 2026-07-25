"""RAG Service with semantic chunking and vector search.

Implements:
- Semantic chunking (respects document structure)
- Vector search with filter by distance threshold
"""
import logging
import re
import threading
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from core.circuit_breaker import get_circuit_breaker
from core.config import get_settings

logger = logging.getLogger(__name__)

# Circuit breaker for RAG search (ChromaDB + embeddings)
_rag_search_cb = get_circuit_breaker("rag:search", failure_threshold=5, recovery_timeout=60)
_rag_index_cb = get_circuit_breaker("rag:index", failure_threshold=3, recovery_timeout=120)


class RAGService:
    """Thread-safe RAG service with ChromaDB and semantic chunking."""

    CHUNK_SIZE = 600
    CHUNK_OVERLAP = 80
    TOP_K = 5
    FINAL_TOP_K = 3
    DISTANCE_THRESHOLD = 1.5

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._model: SentenceTransformer | None = None
        self._client: chromadb.PersistentClient | None = None
        self._collection: chromadb.Collection | None = None
        self._lock = threading.RLock()
        self._init_collection()

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.settings.embedding_model)
        return self._model

    def _init_collection(self) -> None:
        with self._lock:
            if self._client is None:
                persist_dir = self.settings.base_dir / "chroma_db"
                self._client = chromadb.PersistentClient(path=str(persist_dir))
                self._collection = self._client.get_or_create_collection(
                    name="documentos",
                    metadata={"hnsw:space": "cosine"},
                )

    @property
    def collection(self):
        self._init_collection()
        return self._collection

    def _chunk_text_semantic(self, text: str) -> list[str]:
        """Semantic chunking that respects document structure.

        Strategy:
        1. Split by major section breaks (\n\n, headers)
        2. Within sections, split by sentences
        3. Merge small sentences into chunks of target size
        4. Add overlap for context continuity
        """
        if not text or not text.strip():
            return []

        # Step 1: Split by major section breaks
        sections = re.split(r'\n{2,}', text)

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
            sentences = re.split(r'(?<=[.!?])\s+', section)

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
            prev_words = chunks[i-1].split()[-20:]  # Last 20 words
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

    def index_document(self, text: str, doc_name: str, metadata: dict[str, Any] | None = None) -> int:
        if not _rag_index_cb.allow_request():
            logger.warning("RAG index circuit breaker open, skipping indexing of '%s'", doc_name)
            return 0

        with self._lock:
            # Remove existing chunks for this document
            try:
                existing = self.collection.get(where={"nome_doc": doc_name})
                if existing["ids"]:
                    self.collection.delete(ids=existing["ids"])
            except Exception as e:
                logger.warning("Failed to remove existing chunks for '%s': %s", doc_name, e)

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
                    {"nome_doc": doc_name, "chunk_index": i, "char_count": len(chunk), **(metadata or {})}
                    for i, chunk in enumerate(chunks)
                ]

                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=chunks,
                    metadatas=metadatas,
                )
                _rag_index_cb.record_success()
                return len(chunks)
            except Exception:
                _rag_index_cb.record_failure()
                raise

    def search_context(self, query: str, top_k: int = None) -> list[str]:
        """Search with hybrid approach: vector + keyword."""
        if not _rag_search_cb.allow_request():
            logger.warning("RAG search circuit breaker open, returning empty results")
            return []

        with self._lock:
            top_k = top_k or self.TOP_K

            if self.collection.count() == 0:
                return []

            try:
                # Vector search
                model = self._get_model()
                query_embedding = model.encode([query], show_progress_bar=False).tolist()
                results = self.collection.query(
                    query_embeddings=query_embedding,
                    n_results=min(top_k, self.collection.count()),
                )

                documents = results["documents"][0] if results["documents"] else []
                distances = results["distances"][0] if results["distances"] else []

                # Filter by distance threshold and return
                resultados = [
                    doc for doc, dist in zip(documents, distances, strict=False)
                    if dist < self.DISTANCE_THRESHOLD
                ]

                _rag_search_cb.record_success()
                return resultados[:self.FINAL_TOP_K]
            except Exception as e:
                _rag_search_cb.record_failure()
                logger.warning("RAG search failed: %s", e)
                return []

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
                    return f"Documento '{doc_name}' removido ({len(existing['ids'])} chunks)."
                return f"Documento '{doc_name}' nao encontrado."
            except Exception as e:
                return f"Erro ao remover: {e}"

    def close(self) -> None:
        with self._lock:
            if self._client:
                self._client = None
                self._collection = None


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
