import contextlib
import logging
import os
import re
import tempfile
import threading
import unicodedata
from datetime import datetime
from typing import Any

import numpy as np

from core.embeddings import create_sentence_transformer
from core.json_persistence import locked_path
from core.settings import get_settings
from core.sqlite_store import (
    connect,
    db_path_for,
    init_schema,
    migrate_memories_json,
)

logger = logging.getLogger(__name__)

_MEMORY_RECALL_TERMS = (
    "lembra",
    "lembrar",
    "memoria",
    "o que eu disse",
    "o que eu falei",
    "quem sou eu",
    "me conhece",
    "minha preferencia",
    "meu perfil",
)
_SEARCH_STOP_WORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "eu",
    "me",
    "meu",
    "minha",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "para",
    "por",
    "que",
    "se",
    "um",
    "uma",
    "usuario",
}


def _search_terms(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", str(text).casefold())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return {
        token
        for token in re.findall(r"[a-z0-9]{2,}", ascii_text)
        if token not in _SEARCH_STOP_WORDS
    }


def _explicit_memory_recall(query: str) -> bool:
    normalized = unicodedata.normalize("NFKD", query.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return any(term in normalized for term in _MEMORY_RECALL_TERMS)


class MemoryService:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._db_path = db_path_for(self.settings.memorias_file)
        self._model: Any | None = None
        self._embeddings_cache: dict = {}
        self._memories: list[dict] = []
        self._texts: list[str] = []
        self._term_index: dict[str, set[int]] = {}
        self._lock = threading.RLock()
        self._file_signature: tuple[int, int] | None = None
        self._load_error: Exception | None = None
        self._load()

    @property
    def _model_instance(self) -> Any:
        if self._model is None:
            self._model = create_sentence_transformer(self.settings.embedding_model)
        return self._model

    @property
    def _cache_path(self):
        return self.settings.memorias_file.with_suffix(".embeddings_cache.npy")

    def _load(self) -> None:
        with self._lock, locked_path(self._db_path):
            self._load_unlocked()

    def _load_unlocked(self) -> None:
        self._embeddings_cache.clear()
        self._load_error = None
        try:
            self._memories = []
            with connect(self._db_path) as conn:
                init_schema(conn)
                migrate_memories_json(self.settings.memorias_file, conn)
                for row in conn.execute("SELECT texto, data FROM memories ORDER BY id"):
                    self._memories.append({"texto": row["texto"], "data": row["data"]})
            self._rebuild_search_index()
            self._file_signature = self._signature()
        except Exception as error:
            logger.warning("Erro ao ler memorias em %s: %s", self.settings.memorias_file, error)
            self._memories = []
            self._rebuild_search_index()
            self._load_error = error

        if self._load_error is None:
            cached_embeddings = None
            if self._cache_path.exists():
                try:
                    cached_embeddings = np.load(self._cache_path, allow_pickle=False)
                except Exception as e:
                    logger.warning("Falha ao carregar cache de embeddings: %s", e)

            texts = self._texts

            # Embeddings are optional and loaded only when a recall-style query
            # needs semantic fallback. Ordinary chat must not initialize a large
            # embedding model merely because memories exist.
            if cached_embeddings is not None and len(cached_embeddings) == len(texts):
                for texto, vetor in zip(texts, cached_embeddings, strict=True):
                    self._embeddings_cache[texto] = vetor

    def _rebuild_search_index(self) -> None:
        self._texts = []
        self._term_index = {}
        for memory in self._memories:
            text = memory.get("texto", "") if isinstance(memory, dict) else str(memory)
            if not text:
                continue
            index = len(self._texts)
            self._texts.append(text)
            for term in _search_terms(text):
                self._term_index.setdefault(term, set()).add(index)

    def _signature(self) -> tuple[int, int] | None:
        try:
            stat = self._db_path.stat()
            return stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return None

    def _refresh_if_changed(self) -> None:
        if self._signature() == self._file_signature:
            return
        with locked_path(self._db_path):
            if self._signature() != self._file_signature:
                self._load_unlocked()

    def _persist_embeddings(self) -> None:
        tmp_name = ""
        try:
            texts = [m.get("texto", "") if isinstance(m, dict) else m for m in self._memories]
            vetores = np.array(
                [self._embeddings_cache[k] for k in texts if k in self._embeddings_cache]
            )
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{self._cache_path.name}.", suffix=".npy", dir=self._cache_path.parent
            )
            os.close(fd)
            np.save(tmp_name, vetores)
            os.replace(tmp_name, self._cache_path)
        except Exception as e:
            logger.warning("Falha ao persistir cache de embeddings: %s", e)
            if tmp_name:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(tmp_name)

    def get_all(self) -> list[dict]:
        with self._lock:
            self._refresh_if_changed()
            return self._memories.copy()

    def add(self, texto: str) -> dict:
        with self._lock, locked_path(self._db_path):
            self._load_unlocked()
            memoria = {"texto": texto, "data": datetime.now().strftime("%d/%m/%Y")}
            self._memories.append(memoria)
            self._rebuild_search_index()
            try:
                self._embeddings_cache[texto] = self._model_instance.encode([texto])[0]
            except Exception as error:
                logger.warning("Erro ao gerar embedding para nova memoria: %s", error)
            self._save_unlocked()
            return memoria

    def get_all_texts(self) -> list[str]:
        with self._lock:
            self._refresh_if_changed()
            return self._texts.copy()

    def search(self, query: str) -> list[str]:
        all_texts = self.get_all_texts()
        query = str(query or "").strip()
        if not all_texts or not query:
            return []

        query_terms = _search_terms(query)
        candidate_indices: set[int] = set()
        for term in query_terms:
            candidate_indices.update(self._term_index.get(term, ()))
        lexical_matches: list[tuple[float, int, str]] = []
        for index in candidate_indices:
            text = all_texts[index]
            memory_terms = _search_terms(text)
            overlap = query_terms & memory_terms
            if not overlap:
                continue
            score = len(overlap) / max(1, len(query_terms))
            lexical_matches.append((score, -index, text))
        if lexical_matches:
            lexical_matches.sort(reverse=True)
            return [item[2] for item in lexical_matches[: self.settings.top_memories]]

        # Semantic retrieval is intentionally reserved for explicit recall. This
        # avoids encoding every unrelated chat message on CPU.
        if not _explicit_memory_recall(query):
            return []

        with self._lock:
            try:
                if len(self._embeddings_cache) != len(all_texts):
                    embeddings = self._model_instance.encode(all_texts)
                    self._embeddings_cache = dict(zip(all_texts, embeddings, strict=True))
                    self._persist_embeddings()
                query_embedding = self._model_instance.encode([query])[0]
                vetores = np.array([self._embeddings_cache[text] for text in all_texts])

                norm_vetores = np.linalg.norm(vetores, axis=1)
                norm_query = np.linalg.norm(query_embedding)

                if norm_query == 0 or np.any(norm_vetores == 0):
                    return []

                similarities = np.dot(vetores, query_embedding) / (norm_vetores * norm_query)
                top_indices = np.argsort(similarities)[::-1][: self.settings.top_memories]

                return [
                    all_texts[i]
                    for i in top_indices
                    if similarities[i] > self.settings.memory_threshold
                ]
            except Exception as e:
                logger.warning("Memory search failed: %s", e)
                return []

    def _save_unlocked(self) -> None:
        if self._load_error is not None:
            raise RuntimeError(
                "As memorias nao foram salvas porque o arquivo existente esta invalido."
            ) from self._load_error
        with connect(self._db_path) as conn:
            init_schema(conn)
            conn.execute("DELETE FROM memories")
            conn.executemany(
                "INSERT INTO memories (texto, data) VALUES (?, ?)",
                [
                    (
                        memory.get("texto", "") if isinstance(memory, dict) else str(memory),
                        memory.get("data", "") if isinstance(memory, dict) else "",
                    )
                    for memory in self._memories
                ],
            )
        self._file_signature = self._signature()
        self._persist_embeddings()

    def clear(self) -> None:
        with self._lock, locked_path(self._db_path):
            self._load_unlocked()
            self._memories.clear()
            self._rebuild_search_index()
            self._embeddings_cache.clear()
            self._save_unlocked()

    def replace_all(self, memories: list[dict]) -> None:
        with self._lock, locked_path(self._db_path):
            self._memories = list(memories)
            self._load_error = None
            self._embeddings_cache.clear()
            self._rebuild_search_index()
            for memoria in self._memories:
                texto = memoria.get("texto", "") if isinstance(memoria, dict) else memoria
                if texto:
                    try:
                        self._embeddings_cache[texto] = self._model_instance.encode([texto])[0]
                    except Exception as error:
                        logger.warning(
                            "Erro ao gerar embedding para memoria importada '%s...': %s",
                            texto[:40],
                            error,
                        )
            self._save_unlocked()


# Global instance for backward compatibility
_memory_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


# Backward compatibility functions
def carregar_memorias() -> list[dict]:
    return get_memory_service().get_all()


def salvar_memorias(memorias: list[dict]) -> None:
    get_memory_service().replace_all(memorias)


def buscar_memorias(texto: str) -> list[str]:
    return get_memory_service().search(texto)
