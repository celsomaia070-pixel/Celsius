"""Sub-agent system with embedding-based classification.

Uses SentenceTransformer for semantic matching between user queries
and agent capabilities, replacing brittle keyword matching.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@dataclass
class SubAgent:
    nome: str
    descricao: str
    ferramentas: list
    system_prompt_extra: str = ""
    timeout: int = 60
    max_iterations: int = 4
    _embedding: list[float] = field(default_factory=list, repr=False)


REGISTRO_AGENTES = [
    SubAgent(
        nome="rag_agent",
        descricao=("Analise, busca e preenchimento de documentos Word/PDF, formularios e RAG"),
        ferramentas=[
            "inspecionar_formulario_documento",
            "preencher_documento",
            "preencher_documento_com_fontes",
            "gerar_documento_local",
            "indexar_documento",
            "listar_documentos_rag",
            "remover_documento",
        ],
        system_prompt_extra=(
            "Voce e especialista em RAG. Ao indexar documentos, "
            "confirme o sucesso e sugira perguntas relevantes. "
            "Ao buscar contexto, selecione as informacoes mais relevantes. "
            "Para preencher, inspecione primeiro, gere uma copia e nunca invente valores. "
            "Para relatorios pedagogicos, gere um PDF ou DOCX somente com fatos encontrados "
            "nos documentos indexados."
        ),
    ),
    SubAgent(
        nome="code_agent",
        descricao="Execucao e analise de codigo Python, programar, calcular, script",
        ferramentas=["executar_codigo"],
        system_prompt_extra=(
            "Voce e um especialista em Python. Ao executar codigo, "
            "analise os resultados e explique o que aconteceu. "
            "Se houver erro, corrija o codigo e execute novamente. "
            "Sempre mostre o resultado final."
        ),
        timeout=45,
        max_iterations=3,
    ),
    SubAgent(
        nome="browser_agent",
        descricao="Navegacao web, extracao de dados, scraping, acessar sites",
        ferramentas=["navegar_web"],
        system_prompt_extra=(
            "Voce e um especialista em navegacao web. "
            "Interprete a arvore de acessibilidade para entender a pagina. "
            "Extraia apenas informacoes relevantes para a pergunta do usuario."
        ),
        timeout=60,
        max_iterations=5,
    ),
    SubAgent(
        nome="search_agent",
        descricao="Pesquisa web com DuckDuckGo, noticias, precos, dados atualizados da internet",
        ferramentas=["pesquisar_web"],
        system_prompt_extra=(
            "Voce e um pesquisador. Ao pesquisar, resuma os resultados "
            "de forma clara e cite as fontes quando possivel. "
            "Filtre informacoes irrelevantes."
        ),
    ),
    SubAgent(
        nome="file_agent",
        descricao="Gerenciamento e leitura de arquivos, listar pastas, abrir arquivos",
        ferramentas=["listar_arquivos", "ler_arquivo", "processar_arquivo"],
        system_prompt_extra=(
            "Voce e um especialista em arquivos. "
            "Ao ler arquivos grandes, resuma os pontos-chave. "
            "Ao listar diretorios, organize as informacoes."
        ),
    ),
    SubAgent(
        nome="memory_agent",
        descricao="Gerenciamento de memorias, lembrar fatos, salvar informacoes",
        ferramentas=["salvar_memoria", "buscar_memoria"],
        system_prompt_extra=(
            "Voce e especialista em memorias. "
            "Ao salvar, reformule para ser claro e conciso. "
            "Ao buscar, selecione as memorias mais relevantes."
        ),
    ),
]

# Keyword fallback for when embedding model is unavailable
_KEYWORD_MAP = {
    "rag_agent": [
        "indexar",
        "index",
        "documento indexado",
        "buscar documento",
        "listar documentos",
        "preencher documento",
        "preencher formulario",
        "editar word",
        "editar pdf",
    ],
    "code_agent": ["executar codigo", "rodar codigo", "python", "calcular", "script", "programa"],
    "browser_agent": ["navegar", "abrir site", "acessar pagina", "extrair de site", "scraping"],
    "search_agent": ["pesquisar", "buscar na web", "procurar na internet", "noticias", "preco"],
    "file_agent": ["listar arquivos", "ler arquivo", "abrir arquivo", "pasta", "diretorio"],
    "memory_agent": ["lembrar", "memoria", "salvar fato", "buscar fato", "lembrar de"],
}

# Singleton for embedding model
_embedding_model: "SentenceTransformer | None" = None
_embeddings_computed = False


def _get_embedding_model() -> "SentenceTransformer | None":
    """Lazy load SentenceTransformer model."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from core.embeddings import create_sentence_transformer
            from core.settings import get_settings

            settings = get_settings()
            _embedding_model = create_sentence_transformer(settings.embedding_model)
        except Exception as e:
            logger.warning("Failed to load embedding model: %s", e)
            return None
    return _embedding_model


def preload_embedding_model() -> None:
    """Pre-load embedding model on main thread to avoid GC crash in worker threads."""
    _get_embedding_model()


def _compute_agent_embeddings() -> None:
    """Pre-compute embeddings for all agent descriptions."""
    global _embeddings_computed
    if _embeddings_computed:
        return

    model = _get_embedding_model()
    if model is None:
        return

    try:
        descriptions = [agent.descricao for agent in REGISTRO_AGENTES]
        embeddings = model.encode(descriptions)
        for agent, emb in zip(REGISTRO_AGENTES, embeddings, strict=False):
            agent._embedding = emb.tolist()
        _embeddings_computed = True
    except Exception as e:
        logger.warning("Failed to compute agent embeddings: %s", e)


def _classify_by_embedding(pergunta: str) -> SubAgent | None:
    """Classify user query using embedding similarity."""
    model = _get_embedding_model()
    if model is None or not _embeddings_computed:
        return None

    try:
        import numpy as np

        query_embedding = model.encode([pergunta])[0]
        from core.operation_control import check_control

        check_control()
        # Normalize for cosine similarity
        norm = np.linalg.norm(query_embedding)
        if norm == 0:
            return None
        query_norm = query_embedding / norm

        best_agent = None
        best_score = -1.0
        second_score = -1.0

        for agent in REGISTRO_AGENTES:
            if not agent._embedding:
                continue
            agent_emb = np.array(agent._embedding)
            norm = np.linalg.norm(agent_emb)
            if norm == 0:
                continue
            agent_norm = agent_emb / norm
            score = float(query_norm @ agent_norm)
            if score > best_score:
                second_score = best_score
                best_score = score
                best_agent = agent
            elif score > second_score:
                second_score = score

        # Threshold: require minimum similarity (cosine similarity is 0-1 for normalized vectors)
        if best_score >= 0.4 and best_score - second_score >= 0.08 and best_agent:
            return best_agent
        return None
    except Exception as e:
        logger.warning("Embedding classification failed: %s", e)
        return None


def _classify_by_keywords(pergunta: str) -> SubAgent | None:
    """Fallback classification using keyword matching."""
    import re

    from core.message_intent import normalize_text

    pergunta_lower = normalize_text(pergunta)

    matches = [
        agente
        for agente in REGISTRO_AGENTES
        if any(
            re.search(rf"\b{re.escape(normalize_text(palavra))}\b", pergunta_lower)
            for palavra in _KEYWORD_MAP.get(agente.nome, [])
        )
    ]
    return matches[0] if len(matches) == 1 else None


def classificar_tarefa(pergunta: str, *, semantic: bool = True) -> SubAgent | None:
    """Classify user query to select the best sub-agent.

    Uses cheap keywords first; uncertain semantics keep the general agent.
    """
    if not pergunta or len(pergunta.strip()) < 3:
        return None

    from core.message_intent import classify_intent

    if not classify_intent(pergunta).operational:
        return None
    lexical = _classify_by_keywords(pergunta)
    if lexical:
        return lexical
    if not semantic:
        return None

    from core.operation_control import check_control

    check_control()
    _compute_agent_embeddings()
    check_control()
    result = _classify_by_embedding(pergunta)
    if result:
        return result

    # Fallback to keywords
    return _classify_by_keywords(pergunta)


def obter_prompt_agente(agente: SubAgent | None) -> str:
    """Get the system prompt addition for a sub-agent."""
    if agente is None:
        return ""
    return agente.system_prompt_extra
