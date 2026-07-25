"""Sub-agent system with embedding-based classification.

Uses SentenceTransformer for semantic matching between user queries
and agent capabilities, replacing brittle keyword matching.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

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
        descricao="Analise e busca em documentos indexados, RAG, indexar documentos",
        ferramentas=["indexar_documento", "listar_documentos_rag", "remover_documento"],
        system_prompt_extra=(
            "Voce e especialista em RAG. Ao indexar documentos, "
            "confirme o sucesso e sugira perguntas relevantes. "
            "Ao buscar contexto, selecione as informacoes mais relevantes."
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
    "rag_agent": ["indexar", "index", "documento indexado", "buscar documento", "listar documentos"],
    "code_agent": ["executar codigo", "rodar codigo", "python", "calcular", "script", "programa"],
    "browser_agent": ["navegar", "abrir site", "acessar pagina", "extrair de site", "scraping"],
    "search_agent": ["pesquisar", "buscar na web", "procurar na internet", "noticias", "preco"],
    "file_agent": ["listar arquivos", "ler arquivo", "abrir arquivo", "pasta", "diretorio"],
    "memory_agent": ["lembrar", "memoria", "salvar fato", "buscar fato", "lembrar de"],
}

# Singleton for embedding model
_embedding_model = None
_embeddings_computed = False


def _get_embedding_model():
    """Lazy load SentenceTransformer model."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            from core.config import get_settings
            settings = get_settings()
            _embedding_model = SentenceTransformer(settings.embedding_model)
        except Exception as e:
            logger.warning("Failed to load embedding model: %s", e)
            return None
    return _embedding_model


def preload_embedding_model():
    """Pre-load embedding model on main thread to avoid GC crash in worker threads."""
    _get_embedding_model()


def _compute_agent_embeddings():
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
        for agent, emb in zip(REGISTRO_AGENTES, embeddings):
            agent._embedding = emb.tolist()
        _embeddings_computed = True
    except Exception as e:
        logger.warning("Failed to compute agent embeddings: %s", e)


def _classify_by_embedding(pergunta: str) -> Optional[SubAgent]:
    """Classify user query using embedding similarity."""
    model = _get_embedding_model()
    if model is None or not _embeddings_computed:
        return None

    try:
        import numpy as np
        query_embedding = model.encode([pergunta])[0]
        # Normalize for cosine similarity
        query_norm = query_embedding / np.linalg.norm(query_embedding)

        best_agent = None
        best_score = -1.0

        for agent in REGISTRO_AGENTES:
            if not agent._embedding:
                continue
            agent_emb = np.array(agent._embedding)
            agent_norm = agent_emb / np.linalg.norm(agent_emb)
            score = float(query_norm @ agent_norm)
            if score > best_score:
                best_score = score
                best_agent = agent

        # Threshold: require minimum similarity (cosine similarity is 0-1 for normalized vectors)
        if best_score >= 0.4 and best_agent:
            return best_agent
        return None
    except Exception as e:
        logger.warning("Embedding classification failed: %s", e)
        return None


def _classify_by_keywords(pergunta: str) -> Optional[SubAgent]:
    """Fallback classification using keyword matching."""
    pergunta_lower = pergunta.lower()

    for agente in REGISTRO_AGENTES:
        for palavra in _KEYWORD_MAP.get(agente.nome, []):
            if palavra in pergunta_lower:
                return agente

    return None


def classificar_tarefa(pergunta: str) -> Optional[SubAgent]:
    """Classify user query to select the best sub-agent.
    
    Uses embedding-based classification with keyword fallback.
    """
    if not pergunta or len(pergunta.strip()) < 3:
        return None

    # Try embedding classification first
    _compute_agent_embeddings()
    result = _classify_by_embedding(pergunta)
    if result:
        return result

    # Fallback to keywords
    return _classify_by_keywords(pergunta)


def obter_prompt_agente(agente: Optional[SubAgent]) -> str:
    """Get the system prompt addition for a sub-agent."""
    if agente is None:
        return ""
    return agente.system_prompt_extra
