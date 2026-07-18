import threading
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from core.config import get_settings


class RAGService:
    """Thread-safe RAG service with ChromaDB."""

    CHUNK_SIZE = 800
    CHUNK_OVERLAP = 120
    TOP_K = 5
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

    def _chunk_text(self, text: str, size: int = None, overlap: int = None) -> list[str]:
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
        with self._lock:
            # Remove existing chunks for this document
            try:
                existing = self.collection.get(where={"nome_doc": doc_name})
                if existing["ids"]:
                    self.collection.delete(ids=existing["ids"])
            except Exception:
                pass

            chunks = self._chunk_text(text)
            if not chunks:
                return 0

            model = self._get_model()
            embeddings = model.encode(chunks).tolist()
            ids = [f"{doc_name}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [
                {"nome_doc": doc_name, "chunk_index": i, **(metadata or {})}
                for i in range(len(chunks))
            ]

            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
            )
            return len(chunks)

    def search_context(self, query: str, top_k: int = None) -> list[str]:
        with self._lock:
            top_k = top_k or self.TOP_K

            if self.collection.count() == 0:
                return []

            model = self._get_model()
            query_embedding = model.encode([query]).tolist()
            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=min(top_k, self.collection.count()),
            )

            documents = results["documents"][0] if results["documents"] else []
            distances = results["distances"][0] if results["distances"] else []

            filtered = [
                doc for doc, dist in zip(documents, distances)
                if dist < self.DISTANCE_THRESHOLD
            ]
            return filtered

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
