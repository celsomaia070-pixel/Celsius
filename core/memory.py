import json
import logging
import os
import tempfile
import threading
from datetime import datetime

import numpy as np
from sentence_transformers import SentenceTransformer

from core.config import get_settings

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._model: SentenceTransformer | None = None
        self._embeddings_cache: dict = {}
        self._memories: list[dict] = []
        self._lock = threading.RLock()
        self._load()

    @property
    def _model_instance(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.settings.embedding_model)
        return self._model

    def _load(self) -> None:
        with self._lock:
            self._embeddings_cache.clear()
            if self.settings.memorias_file.exists():
                try:
                    with open(self.settings.memorias_file, encoding="utf-8") as f:
                        self._memories = json.load(f)
                except Exception as e:
                    logger.warning("Erro ao ler memorias em %s: %s", self.settings.memorias_file, e)
                    self._memories = []
                for memoria in self._memories:
                    texto = memoria.get("texto", "") if isinstance(memoria, dict) else memoria
                    if texto and texto not in self._embeddings_cache:
                        try:
                            self._embeddings_cache[texto] = self._model_instance.encode([texto])[0]
                        except Exception as e:
                            logger.warning(
                                "Erro ao gerar embedding para memoria '%s...': %s",
                                texto[:40],
                                e,
                            )
            else:
                self._memories = []

    def get_all(self) -> list[dict]:
        with self._lock:
            return self._memories.copy()

    def add(self, texto: str) -> dict:
        with self._lock:
            memoria = {"texto": texto, "data": datetime.now().strftime("%d/%m/%Y")}
            self._memories.append(memoria)
            self._embeddings_cache[texto] = self._model_instance.encode([texto])[0]
            self._save()
            return memoria

    def get_all_texts(self) -> list[str]:
        with self._lock:
            return [m.get("texto", "") if isinstance(m, dict) else m for m in self._memories]

    def search(self, query: str) -> list[str]:
        all_texts = self.get_all_texts()
        if not all_texts:
            return []
        if len(all_texts) <= self.settings.inject_all_memories_limit:
            return all_texts
        with self._lock:
            if not self._embeddings_cache:
                return []
            try:
                query_embedding = self._model_instance.encode([query])[0]
                vetores = np.array(list(self._embeddings_cache.values()))

                norm_vetores = np.linalg.norm(vetores, axis=1)
                norm_query = np.linalg.norm(query_embedding)

                if norm_query == 0 or np.any(norm_vetores == 0):
                    return []

                similarities = np.dot(vetores, query_embedding) / (norm_vetores * norm_query)
                top_indices = np.argsort(similarities)[::-1][: self.settings.top_memories]

                return [
                    list(self._embeddings_cache.keys())[i]
                    for i in top_indices
                    if similarities[i] > self.settings.memory_threshold
                ]
            except Exception as e:
                logger.warning("Memory search failed: %s", e)
                return []

    def _save(self) -> None:
        try:
            path = self.settings.memorias_file
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
                text=True,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._memories, f, ensure_ascii=False, indent=2)
            os.replace(tmp_name, path)
        except Exception as e:
            logger.warning("Erro ao salvar memorias: %s", e)

    def clear(self) -> None:
        with self._lock:
            self._memories.clear()
            self._embeddings_cache.clear()
            self._save()


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
    service = get_memory_service()
    with service._lock:
        service._memories = memorias
        service._embeddings_cache.clear()
        for memoria in memorias:
            texto = memoria.get("texto", "") if isinstance(memoria, dict) else memoria
            if texto:
                try:
                    service._embeddings_cache[texto] = service._model_instance.encode([texto])[0]
                except Exception as e:
                    logger.warning(
                        "Erro ao gerar embedding para memoria importada '%s...': %s",
                        texto[:40],
                        e,
                    )
        service._save()


def buscar_memorias(texto: str) -> list[str]:
    return get_memory_service().search(texto)
