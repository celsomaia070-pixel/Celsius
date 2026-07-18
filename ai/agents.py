from dataclasses import dataclass


@dataclass
class SubAgent:
    nome: str
    descricao: str
    ferramentas: list
    system_prompt_extra: str = ""
    timeout: int = 60
    max_iterations: int = 4


REGISTRO_AGENTES = [
    SubAgent(
        nome="rag_agent",
        descricao="Analise e busca em documentos indexados",
        ferramentas=["indexar_documento", "listar_documentos_rag", "remover_documento"],
        system_prompt_extra=(
            "Voce e especialista em RAG. Ao indexar documentos, "
            "confirme o sucesso e sugira perguntas relevantes. "
            "Ao buscar contexto, selecione as informacoes mais relevantes."
        ),
    ),
    SubAgent(
        nome="code_agent",
        descricao="Execucao e analise de codigo Python",
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
        descricao="Navegacao web e extracao de dados estruturados",
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
        descricao="Pesquisa na web e informacoes atualizadas",
        ferramentas=["pesquisar_web"],
        system_prompt_extra=(
            "Voce e um pesquisador. Ao pesquisar, resuma os resultados "
            "de forma clara e cite as fontes quando possivel. "
            "Filtre informacoes irrelevantes."
        ),
    ),
    SubAgent(
        nome="file_agent",
        descricao="Gerenciamento e leitura de arquivos",
        ferramentas=["listar_arquivos", "ler_arquivo", "processar_arquivo"],
        system_prompt_extra=(
            "Voce e um especialista em arquivos. "
            "Ao ler arquivos grandes, resuma os pontos-chave. "
            "Ao listar diretorios, organize as informacoes."
        ),
    ),
    SubAgent(
        nome="memory_agent",
        descricao="Gerenciamento de memorias de longo prazo",
        ferramentas=["salvar_memoria", "buscar_memoria"],
        system_prompt_extra=(
            "Voce e especialista em memorias. "
            "Ao salvar, reformule para ser claro e conciso. "
            "Ao buscar, selecione as memorias mais relevantes."
        ),
    ),
]


def classificar_tarefa(pergunta):
    pergunta_lower = pergunta.lower()

    palavras_chave = {
        "rag_agent": ["indexar", "index", "documento indexado", "buscar documento", "listar documentos"],
        "code_agent": ["executar codigo", "rodar codigo", "python", "calcular", "script", "programa"],
        "browser_agent": ["navegar", "abrir site", "acessar pagina", "extrair de site", "scraping"],
        "search_agent": ["pesquisar", "buscar na web", "procurar na internet", "noticias", "preco"],
        "file_agent": ["listar arquivos", "ler arquivo", "abrir arquivo", "pasta", "diretorio"],
        "memory_agent": ["lembrar", "memoria", "salvar fato", "buscar fato", "lembrar de"],
    }

    for agente in REGISTRO_AGENTES:
        for palavra in palavras_chave.get(agente.nome, []):
            if palavra in pergunta_lower:
                return agente

    return None


def obter_prompt_agente(agente):
    if agente is None:
        return ""
    return agente.system_prompt_extra
