import contextlib
import json
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

ORIGEM_USUARIO = "usuario"
ORIGEM_CONVERSA = "conversa"

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


def _is_near_duplicate(text: str, existing: list[str]) -> bool:
    """True when most of *text*'s terms already appear in one stored memory."""
    terms = _search_terms(text)
    if not terms:
        return False
    for prior in existing:
        if not prior:
            continue
        prior_terms = _search_terms(prior)
        overlap = terms & prior_terms
        union = terms | prior_terms
        if union and len(overlap) / len(union) >= 0.45:
            return True
    return False


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
                for row in conn.execute(
                    "SELECT texto, data, origem, conversation_id FROM memories ORDER BY id"
                ):
                    self._memories.append(
                        {
                            "texto": row["texto"],
                            "data": row["data"] or "",
                            "origem": row["origem"] or ORIGEM_USUARIO,
                            "conversation_id": row["conversation_id"] or "",
                        }
                    )
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

    def add(self, texto: str, origem: str = ORIGEM_USUARIO, conversation_id: str = "") -> dict:
        with self._lock, locked_path(self._db_path):
            self._load_unlocked()
            memoria = {
                "texto": texto,
                "data": datetime.now().strftime("%d/%m/%Y"),
                "origem": origem,
                "conversation_id": conversation_id,
            }
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

    def add_unique(
        self,
        texto: str,
        *,
        origem: str = ORIGEM_USUARIO,
        conversation_id: str = "",
    ) -> dict | None:
        """Save a memory only when it is not a near-duplicate of an existing one."""
        texto = str(texto or "").strip()
        if not texto:
            return None
        with self._lock, locked_path(self._db_path):
            self._load_unlocked()
            if _is_near_duplicate(texto, self._texts):
                return None
            memoria = {
                "texto": texto,
                "data": datetime.now().strftime("%d/%m/%Y"),
                "origem": origem,
                "conversation_id": conversation_id,
            }
            self._memories.append(memoria)
            self._rebuild_search_index()
            try:
                self._embeddings_cache[texto] = self._model_instance.encode([texto])[0]
            except Exception as error:
                logger.warning("Erro ao gerar embedding para nova memoria: %s", error)
            self._save_unlocked()
            return memoria

    def search_multi(self, queries: list[str]) -> list[str]:
        """Search several conversation turns, merging and de-duplicating results."""
        results: list[str] = []
        seen: set[str] = set()
        for query in queries:
            for match in self.search(query):
                if match not in seen:
                    seen.add(match)
                    results.append(match)
        return results[: self.settings.top_memories]

    def _save_unlocked(self) -> None:
        if self._load_error is not None:
            raise RuntimeError(
                "As memorias nao foram salvas porque o arquivo existente esta invalido."
            ) from self._load_error
        with connect(self._db_path) as conn:
            init_schema(conn)
            conn.execute("DELETE FROM memories")
            conn.executemany(
                "INSERT INTO memories (texto, data, origem, conversation_id) VALUES (?, ?, ?, ?)",
                [
                    (
                        memory.get("texto", "") if isinstance(memory, dict) else str(memory),
                        memory.get("data", "") if isinstance(memory, dict) else "",
                        memory.get("origem", ORIGEM_USUARIO)
                        if isinstance(memory, dict)
                        else ORIGEM_USUARIO,
                        memory.get("conversation_id", "")
                        if isinstance(memory, dict)
                        else "",
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

    def delete_for_conversation(self, conversation_id: str) -> int:
        """Remove auto-extracted memories tied to a deleted conversation.

        Only memories with ``origem=conversa`` and the matching
        ``conversation_id`` are removed.  User memories are never touched.
        Returns how many memories were removed.
        """
        if not conversation_id:
            return 0
        with self._lock, locked_path(self._db_path):
            self._load_unlocked()
            survivors = [
                memory
                for memory in self._memories
                if not (
                    memory.get("origem") == ORIGEM_CONVERSA
                    and memory.get("conversation_id") == conversation_id
                )
            ]
            removed = len(self._memories) - len(survivors)
            if removed <= 0:
                return 0
            self._memories = survivors
            self._rebuild_search_index()
            self._embeddings_cache.clear()
            self._save_unlocked()
            return removed

    def get_user_memories(self) -> list[dict]:
        """Only the memories the user added manually (never auto-extracted)."""
        with self._lock:
            self._refresh_if_changed()
            return [
                memory.copy()
                for memory in self._memories
                if memory.get("origem") != ORIGEM_CONVERSA
            ]

    def get_conversation_memories(self, conversation_id: str) -> list[str]:
        """Texts auto-extracted from a specific conversation."""
        if not conversation_id:
            return []
        with self._lock:
            self._refresh_if_changed()
            return [
                str(memory.get("texto", ""))
                for memory in self._memories
                if memory.get("origem") == ORIGEM_CONVERSA
                and memory.get("conversation_id") == conversation_id
            ]

    def replace_all(self, memories: list[dict]) -> None:
        with self._lock, locked_path(self._db_path):
            normalized = []
            for memoria in memories:
                if not isinstance(memoria, dict):
                    normalized.append(
                        {
                            "texto": str(memoria),
                            "data": "",
                            "origem": ORIGEM_USUARIO,
                            "conversation_id": "",
                        }
                    )
                    continue
                normalized.append(
                    {
                        "texto": memoria.get("texto", ""),
                        "data": memoria.get("data", ""),
                        "origem": memoria.get("origem", ORIGEM_USUARIO),
                        "conversation_id": memoria.get("conversation_id", ""),
                    }
                )
            self._memories = normalized
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


# ---------------------------------------------------------------------------
# Memoria de longo prazo automatica (extracao de fatos das conversas)
# ---------------------------------------------------------------------------

_MEMORY_EXTRACTION_PROMPT = (
    "Voce e a memoria de longo prazo do Celsius. Dado o dialogo abaixo, extraia "
    "apenas fatos duraveis sobre o usuario: preferencias, hobbies, dados pessoais "
    "relevantes (nome, idade, cidade, trabalho), projetos, metas, decisoes e "
    "informacoes recorrentes que devam ser lembradas em conversas futuras.\n\n"
    "Regras:\n"
    "- Responda SOMENTE em JSON: uma lista de strings. Nada alem disso.\n"
    "- Nao invente fatos: baseie-se exclusivamente no que o usuario disse.\n"
    "- Nao memorize trocas triviais ('oi', 'obrigado') nem conteudo do assistente.\n"
    "- Prefira frases curtas e completas em portugues do Brasil.\n"
    "- Retorne no maximo {max_facts} fatos.\n\n"
    "Dialogo:\n{dialogo}"
)

_EXTRACTION_LOCK = threading.Lock()


def _llm_response_text(result: Any) -> str:
    try:
        content = result["choices"][0]["message"]["content"]
        return str(content or "")
    except (KeyError, IndexError, TypeError, AttributeError):
        return str(result or "")


def _parse_facts(text: str, max_facts: int) -> list[str]:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    payload = text[start : end + 1]
    try:
        data = json.loads(payload)
    except ValueError:
        data = re.findall(r'"((?:[^"\\]|\\.)*)"', payload)
    if not isinstance(data, list):
        return []
    facts: list[str] = []
    for item in data:
        fact = str(item).strip()
        if fact and len(fact) <= 500:
            facts.append(fact)
    return facts[:max_facts]


def _extract_facts_from_llm(dialogo: str, max_facts: int) -> list[str]:
    from core.llama_cpp import get_llama_manager

    manager = get_llama_manager()
    if not manager.is_healthy():
        return []
    system = _MEMORY_EXTRACTION_PROMPT.format(
        max_facts=max_facts,
        dialogo=dialogo[:4000],
    )
    try:
        result = manager.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "Extraia os fatos agora."},
            ],
            temperature=0.2,
            max_tokens=512,
            stream=False,
        )
    except Exception as error:
        logger.warning("Extracao de memorias falhou: %s", error)
        return []
    return _parse_facts(_llm_response_text(result), max_facts)


def remember_from_turn(
    messages: list[dict],
    *,
    max_facts: int = 5,
    conversation_id: str = "",
) -> int:
    """Extract and persist durable user facts after a finished chat turn.

    Runs the LLM once (blocking) and stores only new, non-duplicate memories.
    Memories are tagged as ``conversa`` and linked to *conversation_id* so they
    can be removed when that conversation is deleted.
    Returns how many memories were actually added.
    """
    settings = get_settings()

    if not getattr(getattr(settings, "features", None), "memory", True):
        return 0
    memory_settings = getattr(settings, "memory", None)
    if memory_settings is not None and not getattr(memory_settings, "auto_extract_facts", False):
        return 0
    max_facts = max_facts or 5
    dialog_lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "")).strip()
        content = str(message.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            dialog_lines.append(f"{role}: {content}")
    if not dialog_lines:
        return 0
    dialogo = "\n".join(dialog_lines[-16:])

    from core.llama_cpp import get_llama_manager

    llama = get_llama_manager()
    if llama.is_inference_busy() is True:
        logger.info("Extracao de memoria adiada: inferencia do chat em andamento")
        return 0
    try:
        from core.model_router import get_multi_model_manager

        if get_multi_model_manager().fast_manager.is_inference_busy() is True:
            logger.info("Extracao de memoria adiada: modelo rapido em uso")
            return 0
    except Exception:
        pass

    with _EXTRACTION_LOCK:
        facts = _extract_facts_from_llm(dialogo, max_facts=max_facts)
        if not facts:
            return 0
        service = get_memory_service()
        added = 0
        for fact in facts:
            if (
                service.add_unique(
                    fact,
                    origem=ORIGEM_CONVERSA,
                    conversation_id=conversation_id,
                )
                is not None
            ):
                added += 1
    if added:
        logger.info("Memoria de longo prazo: %d fato(s) aprendido(s) na conversa", added)
    return added


def extract_and_store_async(messages: list[dict], *, conversation_id: str = "") -> None:
    """Start a background thread that learns durable facts from a chat turn."""
    settings = get_settings()
    memory_settings = getattr(settings, "memory", None)
    max_facts = getattr(memory_settings, "extraction_max_facts", 5)
    thread = threading.Thread(
        target=remember_from_turn,
        args=(messages,),
        kwargs={
            "max_facts": max_facts,
            "conversation_id": conversation_id,
        },
        name="memory-extract",
        daemon=True,
    )
    thread.start()


def memory_query_context(
    user_messages: list[str],
    *,
    extra_queries: list[str] | None = None,
) -> list[str]:
    """Turn the most recent user messages into a ranked memory search query set.

    Real chat rarely repeats stored vocabulary, so a single query can miss the
    relevant facts. Building one query per recent turn (oldest first) lets the
    lexical index match each topic the user has been talking about.
    """
    queries = [str(text).strip() for text in (extra_queries or []) if str(text).strip()]
    for text in user_messages[-8:]:
        cleaned = str(text).strip()
        if cleaned:
            queries.append(cleaned)
    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        if query in seen:
            continue
        seen.add(query)
        unique.append(query)
    return unique
