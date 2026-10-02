"""Hybrid semantic + lexical tool retrieval for a chat turn.

``ai.react._filtrar_ferramentas`` used to decide *only* on a lexical keyword
map. A request the model understood perfectly could still reach it with the
tool it needed hidden — "quais documentos eu tenho?" matched no keyword, so the
document tools were never shown, and the model could only answer from memory.

This module supplies the semantic half of that decision **without deleting the
lexical half**. The caller unions both signals; this module never decides alone.

Design constraints, all of them deliberate:

* **Static embeddings are computed once.** A tool's semantic text never
  changes at runtime, so re-encoding it every turn would be pure waste. The
  cache is keyed by the model id and by the tool names it holds.
* **A general-knowledge question still gets zero tools.** Semantic similarity
  alone cannot tell "Explique energia solar" from "liste meus documentos", so
  an operational-intent gate decides *whether* retrieval runs at all. Below the
  gate the caller keeps its lexical result, which is empty.
* **An operational request never degrades silently to no tools.** When the
  intent gate opens but no signal survived, a small introspection floor is
  applied so the model can at least discover what it can do.
* **Nothing here widens access.** This module only proposes candidates. Mode
  allowlists (``core.agent_modes.filter_tools``), the model tool policy and
  ``ContextBudget.trim_tools_to_budget`` all still run afterwards.

Every knob lives in ``core.settings.AgentModeSettings``; nothing in this module
hardcodes a top-k.
"""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from typing import Any

from core.embeddings import try_get_sentence_transformer
from core.settings import get_settings

logger = logging.getLogger(__name__)

# ── Operational intent ──────────────────────────────────────────
# Domain *nouns* only, not tool names and not action verbs. This is the gate
# that separates "the user wants something done with my data" from "the user is
# asking a general question", and it must stay deliberately narrower than the
# per-tool keyword map: a false positive here only widens what the model may
# try, while a false negative is the exact bug this module exists to fix.
_DOMAIN_TERMS: tuple[str, ...] = (
    # estoque / inventario
    "estoque",
    "inventario",
    "item",
    "itens",
    "peca",
    "pecas",
    "componente",
    "componentes",
    "quantidade",
    "quantidades",
    "movimentacao",
    "movimentacoes",
    "reposicao",
    # documentos
    "documento",
    "documentos",
    "formulario",
    "formularios",
    "contrato",
    "contratos",
    "docx",
    "anexo",
    "anexos",
    "planilha",
    "planilhas",
    # agenda
    "agenda",
    "compromisso",
    "compromissos",
    "visita",
    "visitas",
    "lembrete",
    "lembretes",
    "prazo",
    "prazos",
    "vencimento",
    "vencimentos",
    # cadastros
    "cliente",
    "clientes",
    "fornecedor",
    "fornecedores",
    "orcamento",
    "orcamentos",
    "proposta",
    "propostas",
    "processo",
    "processos",
    "catalogo",
    "sku",
    # web
    "pesquisa",
    "noticia",
    "noticias",
    "internet",
    "youtube",
    # codigo
    "codigo",
    "script",
    "python",
    "algoritmo",
    "funcao",
    "funcoes",
    "programa",
    "programar",
    # arquivos
    "arquivo",
    "arquivos",
    "pasta",
    "pastas",
    "diretorio",
    "diretorios",
    # memoria
    "memorias",
    # entregaveis
    "relatorio",
    "relatorios",
    "grafico",
    "graficos",
    "dashboard",
    "kpi",
)

#: Terms that name *the user's own data* rather than a topic to discuss.
#:
#: The distinction exists because a topic word opens a much weaker door than a
#: data word. "qual a diferenca entre lista e tupla em Python?" contains
#: "python" and asks nothing about local data; "quais clientes eu tenho?"
#: contains "clientes" and asks exactly that. Both matched the single flat list
#: before, so a purely conceptual question was handed introspection tools.
#:
#: A weak term is still allowed to *propose* tools when the encoder is working —
#: retrieval is cheap and the downstream policy filters it. It is not allowed to
#: trigger the caller-side floor, which is what actually put tools in the prompt.
_TOPIC_TERMS: tuple[str, ...] = (
    # codigo
    "codigo",
    "script",
    "python",
    "algoritmo",
    "funcao",
    "funcoes",
    "programa",
    "programar",
    # web
    "pesquisa",
    "noticia",
    "noticias",
    "internet",
    "youtube",
    # entregaveis
    "relatorio",
    "relatorios",
    "grafico",
    "graficos",
    "dashboard",
    "kpi",
)

#: ``_DOMAIN_TERMS`` minus the topical words above.
_LOCAL_DATA_TERMS: tuple[str, ...] = tuple(
    term for term in _DOMAIN_TERMS if term not in set(_TOPIC_TERMS)
)


def _pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    """Word-boundary safe matcher: "item" must not fire inside "itemizar"."""
    return re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)"
    )


_TERM_PATTERN = _pattern(_DOMAIN_TERMS)
_LOCAL_DATA_PATTERN = _pattern(_LOCAL_DATA_TERMS)

# ── Semantic text ──────────────────────────────────────────────


def _normalize(value: Any) -> str:
    """Fold accents so Portuguese queries match the ASCII tool vocabulary."""
    folded = unicodedata.normalize("NFKD", str(value or ""))
    return folded.encode("ascii", "ignore").decode("ascii").lower()


def _schema_terms(schema: Any, *, depth: int = 0) -> list[str]:
    """Collect parameter names, descriptions and enum values from a JSON schema.

    Deep enough for the one level of nesting the Celsius tool schemas use, and
    bounded so a pathological schema cannot produce an unbounded embedding text.
    """
    terms: list[str] = []
    if depth > 3 or not isinstance(schema, dict):
        return terms

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, spec in properties.items():
            terms.append(_normalize(name).replace("_", " "))
            if not isinstance(spec, dict):
                continue
            description = spec.get("description")
            if isinstance(description, str):
                terms.append(_normalize(description))
            enum_values = spec.get("enum")
            if isinstance(enum_values, list):
                terms.extend(_normalize(value) for value in enum_values)
            terms.extend(_schema_terms(spec, depth=depth + 1))
    return terms


def tool_semantic_text(ferramenta: Any) -> str:
    """Build the text embedded for one tool.

    Derived entirely from the tool's own registered data — name, description and
    parameter schema — so a new tool becomes retrievable the moment it is
    registered, with no second list to maintain. Underscores become spaces so
    ``listar_documentos_rag`` reads as ``listar documentos rag`` to the encoder.
    """
    nome = _normalize(getattr(ferramenta, "nome", "")).replace("_", " ")
    descricao = _normalize(getattr(ferramenta, "descricao", ""))
    schema = getattr(ferramenta, "schema", None)
    params = _schema_terms(schema)
    partes = [nome, descricao, *params]
    seen: set[str] = set()
    unicos: list[str] = []
    for parte in partes:
        limpa = " ".join(parte.split())
        if limpa and limpa not in seen:
            seen.add(limpa)
            unicos.append(limpa)
    return " | ".join(unicos)


# ── Cached encoder + static embeddings ─────────────────────────

_model_lock = threading.Lock()
_model: Any | None = None
_model_loaded = False
_embeddings: dict[str, list[float]] = {}
_embeddings_model: str = ""


def get_embedding_model():
    """Shared encoder, loaded lazily. ``None`` when unavailable."""
    global _model, _model_loaded
    if _model_loaded:
        return _model
    with _model_lock:
        if not _model_loaded:
            settings = get_settings()
            _model = try_get_sentence_transformer(settings.embedding_model)
            _model_loaded = True
    return _model


def preload_tool_embeddings() -> None:
    """Warm the encoder and the static tool embeddings on a background-free path.

    Mirrors ``ai.agents.preload_embedding_model`` so the model is resident before
    the first chat turn; both calls share one cached instance.
    """
    model = get_embedding_model()
    if model is None:
        return
    try:
        from ai.tools import REGISTRO_FERRAMENTAS

        _tool_embeddings(REGISTRO_FERRAMENTAS)
    except Exception as exc:
        logger.debug("Falha ao pre-carregar embeddings de ferramentas: %s", exc)


def _tool_embeddings(ferramentas: list[Any]) -> dict[str, list[float]]:
    """Embed every tool once per model id, then reuse for the process lifetime."""
    global _embeddings, _embeddings_model
    if not ferramentas:
        return {}

    model = get_embedding_model()
    if model is None:
        return {}

    settings = get_settings()
    model_name = settings.embedding_model
    nomes = [getattr(ferramenta, "nome", "") for ferramenta in ferramentas]
    fingerprint = f"{model_name}:{len(nomes)}:{hash(tuple(nomes))}"

    with _model_lock:
        if _embeddings and _embeddings_model == fingerprint:
            return _embeddings

        try:
            textos = [tool_semantic_text(ferramenta) for ferramenta in ferramentas]
            vectors = model.encode(textos)
            _embeddings = {
                nome: vector.tolist() for nome, vector in zip(nomes, vectors, strict=False)
            }
            _embeddings_model = fingerprint
        except Exception as exc:
            logger.warning("Falha ao calcular embeddings de ferramentas: %s", exc)
            _embeddings = {}
            _embeddings_model = ""
        return _embeddings


def reset_tool_embeddings() -> None:
    """Drop cached embeddings and the encoder (isolated tests)."""
    global _model, _model_loaded, _embeddings, _embeddings_model
    with _model_lock:
        _model = None
        _model_loaded = False
        _embeddings = {}
        _embeddings_model = ""


# ── Ranking ────────────────────────────────────────────────────


def _cosine(query_vector: Any, target_vector: list[float]) -> float:
    import numpy as np

    alvo = np.asarray(target_vector, dtype=float)
    norma = float(np.linalg.norm(alvo))
    if norma == 0:
        return 0.0
    return float(query_vector @ alvo / (float(np.linalg.norm(query_vector)) * norma))


def score_tools(pergunta: str, ferramentas: list[Any] | None = None) -> dict[str, float]:
    """Cosine similarity between the question and each tool.

    Returns an empty mapping when the encoder is unavailable, so every caller
    degrades to its lexical path instead of failing the turn.
    """
    texto = str(pergunta or "").strip()
    if not texto:
        return {}

    if ferramentas is None:
        from ai.tools import REGISTRO_FERRAMENTAS

        ferramentas = list(REGISTRO_FERRAMENTAS)

    embeddings = _tool_embeddings(list(ferramentas))
    if not embeddings:
        return {}

    model = get_embedding_model()
    if model is None:
        return {}

    try:
        import numpy as np

        bruto = model.encode([texto])[0]
        consulta = bruto / np.linalg.norm(bruto)
    except Exception as exc:
        logger.warning("Falha ao codificar a pergunta para recuperacao: %s", exc)
        return {}

    scores: dict[str, float] = {}
    for nome, vetor in embeddings.items():
        try:
            scores[nome] = _cosine(consulta, vetor)
        except Exception:
            continue
    return scores


def top_tools(
    scores: dict[str, float] | None,
    *,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[tuple[str, float]]:
    """Best tools from precomputed *scores*, capped at top-k.

    Split out from :func:`rank_tools` so a caller that already needs the scores
    for the operational-intent gate does not pay for a second query encoding.
    """
    if not scores:
        return []

    settings = get_settings()
    if not settings.agent.tool_retrieval_enabled:
        return []

    limite = max(1, int(settings.agent.tool_retrieval_top_k if top_k is None else top_k))
    piso = float(
        settings.agent.tool_retrieval_min_score if min_score is None else min_score
    )
    ordenados = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [(nome, score) for nome, score in ordenados if score >= piso][:limite]


def rank_tools(pergunta: str, ferramentas: list[Any] | None = None) -> list[tuple[str, float]]:
    """Convenience wrapper: encode the question once, then rank."""
    return top_tools(score_tools(pergunta, ferramentas))


def is_operational(pergunta: str, scores: dict[str, float] | None = None) -> bool:
    """Whether the message asks for something to be *done with local data*.

    Two independent reasons open the gate:

    1. a local-data domain noun is present ("documentos", "estoque", "clientes");
    2. the semantic ranker is confident on its own (``operational_intent_min_score``),
       which is what lets a paraphrase with no known noun still reach its tool.

    With no encoder available only reason 1 applies, which is exactly the
    previous behaviour.
    """
    texto = _normalize(pergunta)
    if not texto.strip():
        return False

    if _TERM_PATTERN.search(texto):
        return True

    settings = get_settings()
    if not settings.agent.tool_retrieval_enabled or scores is None:
        return False

    limiar = float(settings.agent.operational_intent_min_score)
    return any(score >= limiar for score in scores.values())


def asks_about_local_data(pergunta: str) -> bool:
    """Whether the message names the user's own data.

    Stronger than :func:`is_operational`: a topical word such as "python" or
    "relatorio" is not enough. Callers that *add* tools when retrieval comes up
    empty must use this, otherwise a conceptual question ("a diferenca entre
    lista e tupla em Python?") receives tools it has no use for.
    """
    texto = _normalize(pergunta)
    if not texto.strip():
        return False
    return bool(_LOCAL_DATA_PATTERN.search(texto))
