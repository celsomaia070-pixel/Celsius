import contextlib
import logging
import os
import tempfile
import threading
from datetime import datetime
from typing import Any

import numpy as np

from core.embeddings import create_sentence_transformer
from core.json_persistence import atomic_write_json, locked_path, read_json
from core.settings import get_settings

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._model: Any | None = None
        self._embeddings_cache: dict = {}
        self._memories: list[dict] = []
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
        with self._lock, locked_path(self.settings.memorias_file):
            self._load_unlocked()

    def _load_unlocked(self) -> None:
        self._embeddings_cache.clear()
        self._load_error = None
        try:
            self._memories = read_json(self.settings.memorias_file, [])
            if not isinstance(self._memories, list):
                raise ValueError("O arquivo de memorias deve conter uma lista JSON.")
            self._file_signature = self._signature()
        except Exception as error:
            logger.warning("Erro ao ler memorias em %s: %s", self.settings.memorias_file, error)
            self._memories = []
            self._load_error = error

        if self._load_error is None:
            keys_to_encode = []
            cached_embeddings = None
            if self._cache_path.exists():
                try:
                    cached_embeddings = np.load(self._cache_path, allow_pickle=False)
                except Exception as e:
                    logger.warning("Falha ao carregar cache de embeddings: %s", e)

            for i, memoria in enumerate(self._memories):
                texto = memoria.get("texto", "") if isinstance(memoria, dict) else memoria
                if not texto:
                    continue
                if cached_embeddings is not None and i < len(cached_embeddings):
                    self._embeddings_cache[texto] = cached_embeddings[i]
                else:
                    keys_to_encode.append(texto)

            if keys_to_encode:
                try:
                    novos = self._model_instance.encode(keys_to_encode)
                    for texto, vetor in zip(keys_to_encode, novos, strict=False):
                        self._embeddings_cache[texto] = vetor
                    self._persist_embeddings()
                except Exception as e:
                    logger.warning("Erro ao gerar embeddings: %s", e)

    def _signature(self) -> tuple[int, int] | None:
        try:
            stat = self.settings.memorias_file.stat()
            return stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return None

    def _refresh_if_changed(self) -> None:
        if self._signature() == self._file_signature:
            return
        with locked_path(self.settings.memorias_file):
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
        with self._lock, locked_path(self.settings.memorias_file):
            self._load_unlocked()
            memoria = {"texto": texto, "data": datetime.now().strftime("%d/%m/%Y")}
            self._memories.append(memoria)
            try:
                self._embeddings_cache[texto] = self._model_instance.encode([texto])[0]
            except Exception as error:
                logger.warning("Erro ao gerar embedding para nova memoria: %s", error)
            self._save_unlocked()
            return memoria

    def get_all_texts(self) -> list[str]:
        with self._lock:
            self._refresh_if_changed()
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

    def _save_unlocked(self) -> None:
        if self._load_error is not None:
            raise RuntimeError(
                "As memorias nao foram salvas porque o arquivo existente esta invalido."
            ) from self._load_error
        atomic_write_json(self.settings.memorias_file, self._memories)
        self._file_signature = self._signature()
        self._persist_embeddings()

    def clear(self) -> None:
        with self._lock, locked_path(self.settings.memorias_file):
            self._load_unlocked()
            self._memories.clear()
            self._embeddings_cache.clear()
            self._save_unlocked()

    def replace_all(self, memories: list[dict]) -> None:
        with self._lock, locked_path(self.settings.memorias_file):
            self._memories = list(memories)
            self._load_error = None
            self._embeddings_cache.clear()
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
