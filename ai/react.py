"""ReAct loop using llama-cpp-python directly for GPU/CPU inference."""
import gc
import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ai.tools import REGISTRO_FERRAMENTAS, executar_ferramenta, obter_schemas_openai
from core.config import NUM_PREDICT
from core.llama_cpp import get_llama, get_multi_model_manager
from ai.context_budget import get_budget, estimate_messages_tokens

logger = logging.getLogger(__name__)

MAX_ITERACOES = 5

SYSTEM_PROMPT_REACT = (
    "Voce e Celsius, agente multimodal de IA pessoal do Celso. Data: {data_hora}.\n"
    "Responda SEMPRE em portugues do Brasil.\n\n"
    "## Regras Obrigatorias\n"
    "- NUNCA invente informacoes. Use apenas dados do contexto ou memorias.\n"
    "- Se nao souber, diga: 'Nao tenho essa informacao registrada.'\n"
    "- Se houver memorias no contexto, USE-AS. Nao diga que nao sabe.\n"
    "- Nao comence se apresentando. Va direto ao ponto.\n\n"
    "## Estoque (SEMPRE ACESSIVEL)\n"
    "Voce TEM acesso total ao estoque do usuario. NUNCA diga que nao tem acesso.\n"
    "Para QUALQUER pergunta sobre estoque, use a ferramenta adequada:\n"
    "- listar_estoque: lista TODOS os itens com quantidades, min, max, status\n"
    "- buscar_item_estoque: busca por nome/categoria\n"
    "- entrada_estoque: registra entrada (aumenta quantidade)\n"
    "- saida_estoque: registra saida (diminui quantidade)\n"
    "- adicionar_item_estoque: cadastra item novo\n"
    "- itens_estoque_baixo: lista itens com estoque critico\n"
    "- historico_movimentacoes: historico de entradas/saidas\n"
    "NUNCA responda 'nao tenho acesso ao estoque'. As ferramentas ESTAO disponiveis.\n\n"
    "## Ferramentas Disponiveis\n"
    "Use APENAS quando necessario:\n"
    "- pesquisar_web: buscar dados atualizados na internet (DuckDuckGo)\n"
    "- pesquisar_google: buscar no Google (mais preciso, usa browser headless)\n"
    "- pesquisar_noticias: buscar noticias atuais via RSS (G1, UOL, Folha, etc.)\n"
    "- abrir_no_navegador: abrir sites (quando pedido explicitamente)\n"
    "- salvar_memoria/buscar_memoria: gerenciar memorias\n"
    "- executar_codigo: calcular ou processar dados\n"
    "- indexar_documento: guardar documento para consultas futuras (RAG)\n"
    "- navegar_web: acessar site e extrair informacoes\n"
    "- listar_arquivos/ler_arquivo: gerenciar arquivos\n"
    "- remover_documento: deletar documento do indice\n\n"
    "Diferenca: pesquisar_web RETORNA dados da web. abrir_no_navegador ABRE o site/navegador.\n"
    "Para perguntas simples, responda DIRETO sem ferramentas.\n\n"
    "## Documentos Anexados / Dados de Estoque\n"
    "Sempre que houver um documento anexado ou 'Dados do Estoque' no contexto, o conteudo ja esta disponivel.\n"
    "Os dados de ESTOQUE do usuario estao SEMPRE disponiveis na secao 'Dados do Estoque' abaixo.\n"
    "NAO chame processar_arquivo. NAO chame listar_estoque. Analise os dados e responda diretamente.\n"
    "Se os dados contiverem informacoes de estoque, formate a resposta em tabela ou lista.\n\n"
    "### REGRAS CRITICAS SOBRE ESTOQUE:\n"
    "- TODOS os itens listados ESTAO no estoque do usuario. NUNCA diga que um item 'nao esta no estoque'.\n"
    "- Itens com status 'CRITICO' ou 'estoque baixo' SIM ESTAO no estoque, so precisam de reposicao.\n"
    "- Se um item tem quantidade=3, ele TEM 3 unidades disponiveis. NAO diga que 'nao tem' esse item.\n"
    "- Liste TODOS os itens SEMPRE, incluindo os criticos. Eles sao os MAIS importantes para o usuario.\n"
    "- NUNCA adicione observacoes como 'nao esta no estoque atual' ou 'fora de estoque'.\n\n"
"## Estilo\n"
"- Seja um ESPECIALISTA altamente especializado no assunto tratado\n"
"- Respostas COMPLETAS, bem estruturadas e com profundidade\n"
"- Finalize relatorios com comparativos, tendencias e exemplos praticos\n"
"- Use tabelas, listas e topicos quando apropriado\n"
"- Explique o POR QUE e o COMO alem do apenas O QUE\n"
"- Inclua contexto relevante, analogias e insights\n"
"- Emojis com moderacao (1-3 por resposta)\n"
)

SYSTEM_PROMPT_TOOLS_TEXT = (
    "Voce e Celsius, agente multimodal de IA pessoal do Celso. Data: {data_hora}.\n"
    "Responda SEMPRE em portugues do Brasil.\n\n"
    "## Regras Obrigatorias\n"
    "- NUNCA invente informacoes. Use apenas dados do contexto ou memorias.\n"
    "- Se nao souber, diga: 'Nao tenho essa informacao registrada.'\n"
    "- Se houver memorias no contexto, USE-AS. Nao diga que nao sabe.\n"
    "- Nao comence se apresentando. Va direto ao ponto.\n"
    "- NAO use ferramentas para perguntas que voce ja sabe responder.\n\n"
    "## Estoque (SEMPRE ACESSIVEL - NUNCA DIGA QUE NAO TEM ACESSO)\n"
    "Voce TEM acesso total ao estoque do usuario via ferramentas.\n"
    "Para QUALQUER pergunta sobre estoque/itens/produtos, use a ferramenta adequada.\n"
    "Exemplos de perguntas que DEVEM usar ferramentas de estoque:\n"
    "- 'quais itens tenho' -> listar_estoque\n"
    "- 'quanto de X tenho' -> buscar_item_estoque\n"
    "- 'entrada de X unidades' -> buscar_item_estoque + entrada_estoque\n"
    "- 'saida de X unidades' -> buscar_item_estoque + saida_estoque\n"
    "- 'cadastrar item novo' -> adicionar_item_estoque\n"
    "- 'itens com estoque baixo' -> itens_estoque_baixo\n"
    "- 'historico de movimentacoes' -> historico_movimentacoes\n"
    "- 'gerar relatorio' -> listar_estoque (e formate como relatorio)\n"
    "Para entrada/saida: primeiro busque o item para obter o ID, depois execute a operacao.\n\n"
    "## Graficos e Visualizacao de Dados\n"
    "Quando o usuario pedir um grafico, chart, visualizacao, ou plotar dados, "
    "vocedeve CHAMAR a ferramenta gerar_grafico. NUNCA apenas descreva os dados.\n"
    "SEMPRE gere o grafico. NUNCA sugira Excel/Google Sheets/Canva.\n"
    "IMPORTANTE: mesmo que os dados ja estejam no contexto, vocedeve chamar "
    "gerar_grafico para criar a imagem visual.\n"
    "Exemplo COMPLETO de chamada:\n"
    "MENSAGEM_TAGS\n"
    "{{{{'name': 'gerar_grafico', 'arguments': {{{{'tipo': 'bar', 'titulo': 'Estoque', "
    "'labels': '[\"Item A\",\"Item B\"]', 'valores': '[10,20]'}}}}}}}}\n"
    "FIM_TAGS\n"
    "Depois de chamar a ferramenta, inclua o resultado na resposta:\n"
    "![Grafico - Estoque](caminho_retornado_pela_ferramenta)\n\n"
    "## Web, YouTube e Google (SEMPRE CHAME A FERRAMENTA)\n"
    "Para QUALQUER pedido de pesquisa, abrir site, YouTube ou Google, voce DEVE chamar uma ferramenta.\n"
    "NUNCA diga que nao pode fazer isso. NUNCA sugira que o usuario faca sozinho.\n"
    "APOS CHAMAR A FERRAMENTA, apenas confirme brevemente (ex: 'Abrindo YouTube.'). NAO faca perguntas adicionais.\n"
    "NUNCA pergunte 'o que voce gostaria de fazer' ou 'deseja ver mais' apos abrir um site.\n\n"
    "Regras:\n"
    "- 'abra/pesquise/abrir [algo] no YouTube' -> abrir_no_navegador(url='youtube [algo]')\n"
    "- 'abra/pesquise/abrir [algo] no Google' -> abrir_no_navegador(url='google [algo]')\n"
    "- 'abra/pesquise/abrir [algo]' (sem plataforma) -> abrir_no_navegador(url='[algo]')\n"
    "- 'pesquise na web/noticias sobre [algo]' -> pesquisar_web(query='[algo]')\n"
    "- 'ultimas noticias sobre [algo]' -> pesquisar_web(query='ultimas noticias sobre [algo]')\n"
    "- 'abra o site [url]' -> abrir_no_navegador(url='[url]')\n\n"
    "Exemplos:\n"
    "Usuario: abra Tales Roberto no YouTube\n"
    "Assistente: MENSAGEM_TAGS\n{{{{'name': 'abrir_no_navegador', 'arguments': {{'url': 'youtube Tales Roberto'}}}}}}\nFIM_TAGS\n\n"
    "Usuario: pesquise as ultimas noticias sobre IA\n"
    "Assistente: MENSAGEM_TAGS\n{{{{'name': 'pesquisar_web', 'arguments': {{'query': 'ultimas noticias sobre IA'}}}}}}\nFIM_TAGS\n\n"
    "Usuario: abra o site da Unimar no Google\n"
    "Assistente: MENSAGEM_TAGS\n{{{{'name': 'abrir_no_navegador', 'arguments': {{'url': 'google site da Unimar'}}}}}}\nFIM_TAGS\n\n"
    "## Ferramentas Disponiveis\n"
    "{ferramentas_texto}\n"
    "Use APENAS quando necessario.\n\n"
    "## Como Usar Ferramentas (OBRIGATORIO)\n"
    "Quando precisar de informacoes externas, voce DEVE chamar uma ferramenta.\n"
    "Formato EXATO (copie exatamente):\n"
    "MENSAGEM_TAGS\n"
    "{{{{'name': 'pesquisar_noticias', 'arguments': {{'query': 'inteligencia artificial'}}}}}}\n"
    "FIM_TAGS\n\n"
    "Exemplo:\n"
    "Usuario: pesquise noticias sobre IA\n"
    "Assistente:\n"
    "MENSAGEM_TAGS\n"
    "{{{{'name': 'pesquisar_noticias', 'arguments': {{'query': 'inteligencia artificial'}}}}}}\n"
    "FIM_TAGS\n\n"
    "Exemplo de chamada de grafico:\n"
    "Usuario: crie um grafico de barras\n"
    "Assistente:\n"
    "MENSAGEM_TAGS\n"
    "{{{{'name': 'gerar_grafico', 'arguments': {{{{'tipo': 'bar', 'titulo': 'Estoque', "
    "'labels': '[\"Item A\",\"Item B\"]', 'valores': '[10,20]'}}}}}}}}\n"
    "FIM_TAGS\n\n"
    "## Documentos Anexados / Dados de Estoque\n"
    "Sempre que houver um documento anexado ou 'Dados do Estoque' no contexto, o conteudo ja esta disponivel.\n"
    "Os dados de ESTOQUE do usuario estao SEMPRE disponiveis na secao 'Dados do Estoque' abaixo.\n"
    "NAO chame processar_arquivo. NAO chame listar_estoque. Analise os dados e responda diretamente.\n"
    "Se os dados contiverem informacoes de estoque, formate a resposta em tabela ou lista.\n"
    "IMPORTANTE: se o usuario pedir um GRAFICO, CHAME gerar_grafico usando os dados do contexto.\n\n"
    "### REGRAS CRITICAS SOBRE ESTOQUE:\n"
    "- TODOS os itens listados ESTAO no estoque do usuario. NUNCA diga que um item 'nao esta no estoque'.\n"
    "- Itens com status 'CRITICO' ou 'estoque baixo' SIM ESTAO no estoque, so precisam de reposicao.\n"
    "- Se um item tem quantidade=3, ele TEM 3 unidades disponiveis. NAO diga que 'nao tem' esse item.\n"
    "- Liste TODOS os itens SEMPRE, incluindo os criticos. Eles sao os MAIS importantes para o usuario.\n"
    "- NUNCA adicione observacoes como 'nao esta no estoque atual' ou 'fora de estoque'.\n\n"
    "## Estilo\n"
    "- Seja um ESPECIALISTA altamente especializado no assunto tratado\n"
    "- Respostas COMPLETAS, bem estruturadas e com profundidade\n"
    "- Finalize relatorios com comparativos, tendencias e exemplos praticos\n"
    "- Use tabelas, listas e topicos quando apropriado\n"
    "- Explique o POR QUE e o COMO alem do apenas O QUE\n"
    "- Inclua contexto relevante, analogias e insights\n"
    "- Emojis com moderacao (1-3 por resposta)\n"
)

class PassoReact:
    def __init__(self, tipo: str, conteudo: str, ferramenta: str | None = None, resultado: str | None = None):
        self.tipo = tipo
        self.conteudo = conteudo
        self.ferramenta = ferramenta
        self.resultado = resultado

    def para_display(self):
        if self.tipo == "raciocinio":
            return f"Pensamento: {self.conteudo}"
        elif self.tipo == "acao":
            return f"Acao: {self.ferramenta}({self.conteudo})"
        elif self.tipo == "observacao":
            preview = self.resultado[:200] + "..." if len(self.resultado or "") > 200 else self.resultado
            return f"Observacao: {preview}"
        elif self.tipo == "resposta":
            return None
        return self.conteudo


def _formatar_ferramentas_texto() -> str:
    linhas = []
    for f in REGISTRO_FERRAMENTAS:
        params = f.schema.get("properties", {})
        required = f.schema.get("required", [])
        param_str = ", ".join(
            f"{k}" + (" (obrigatorio)" if k in required else "")
            for k in params
        )
        linhas.append(f"- {f.nome}: {f.descricao}")
        if param_str:
            linhas.append(f"  Parametros: {param_str}")
    return "\n".join(linhas)


def _filtrar_ferramentas(pergunta: str) -> list:
    """Filter tools based on query relevance."""
    keywords_map = {
        "pesquisar_web": ["pesquisar", "buscar", "procurar", "web", "internet", "atual", "hoje", "agora", "preco", "noticia"],
        "pesquisar_google": ["google", "buscar no google", "pesquisa google"],
        "pesquisar_noticias": ["noticia", "noticias", "ultimas", "recentes", "atualidades", "aconteceu", "jornal"],
        "navegar_web": ["navegar", "extrair", "scraping", "scrape", "extrair conteudo"],
        "abrir_no_navegador": ["abrir", "abre", "abrir site", "abrir no navegador", "youtube", "google", "abrir no browser", "abra o site", "abrir site"],
        "executar_codigo": ["codigo", "python", "calcular", "script", "programa", "executar"],
        "salvar_memoria": ["lembrar", "memoria", "salvar", "guarda", "anota"],
        "buscar_memoria": ["lembra", "memoria", "buscar memoria", "o que eu disse", "o que eu falei"],
        "listar_arquivos": ["listar", "arquivos", "pasta", "diretorio", "arquivos na"],
        "ler_arquivo": ["ler arquivo", "abrir arquivo", "conteudo do arquivo"],
        "processar_arquivo": ["processar", "analisar arquivo", "arquivo pdf", "arquivo doc", "arquivo odt"],
        "informacoes_sistema": ["sistema", "info", "versao", "python", "so"],
        "indexar_documento": ["indexar", "guardar documento", "indexar documento", "rag"],
        "listar_documentos_rag": ["listar documentos", "documentos indexados", "documentos no rag"],
        "remover_documento": ["remover documento", "deletar documento", "apagar documento"],
        "listar_estoque": ["estoque", "itens", "peças", "pecas", "produtos", "inventario", "quais itens", "resumo do estoque"],
        "buscar_item_estoque": ["estoque", "quantidade", "tem de", "tenho", "quanto", "item"],
        "entrada_estoque": ["entrada", "recebi", "comprei", "entrou", "adicionar estoque", "repor", "reposicao", "aumentar estoque"],
        "saida_estoque": ["saida", "usei", "enviei", "vendi", "removeu", "diminuir estoque", "gastei", "consumi"],
        "adicionar_item_estoque": ["cadastrar item", "novo item", "adicionar item", "cadastrar produto", "novo produto", "item novo"],
        "itens_estoque_baixo": ["estoque baixo", "estoque minimo", "critico", "precisa repor", "repicao", "itens baixos", "alerta"],
        "historico_movimentacoes": ["historico", "movimentacoes", "ultimas entradas", "ultimas saidas", "log de estoque"],
        "gerar_grafico": ["grafico", "graficos", "chart", "barras", "pizza", "pie", "line", "area", "histograma", "dispersao", "scatter", "visualizar", "visualizar dados", "plotar", "plot"],
    }
    
    pergunta_lower = pergunta.lower()
    relevant_tools = set()
    
    for tool_name, keywords in keywords_map.items():
        if any(kw in pergunta_lower for kw in keywords):
            relevant_tools.add(tool_name)
    
    # Always include basic tools
    relevant_tools.add("informacoes_sistema")
    
    # Sempre incluir ferramentas web (essenciais para pesquisa/abrir sites)
    relevant_tools.add("abrir_no_navegador")
    relevant_tools.add("pesquisar_web")
    
    # Always include inventory tools (core functionality)
    for f in REGISTRO_FERRAMENTAS:
        if f.nome.startswith(("listar_estoque", "buscar_item_estoque", "entrada_estoque", "saida_estoque", "adicionar_item_estoque", "itens_estoque_baixo", "historico_movimentacoes")):
            relevant_tools.add(f.nome)
    
    return [f for f in REGISTRO_FERRAMENTAS if f.nome in relevant_tools]


def _formatar_ferramentas_texto_filtrado(ferramentas: list) -> str:
    """Format only the given list of tools."""
    linhas = []
    for f in ferramentas:
        params = f.schema.get("properties", {})
        required = f.schema.get("required", [])
        param_str = ", ".join(
            f"{k}" + (" (obrigatorio)" if k in required else "")
            for k in params
        )
        linhas.append(f"- {f.nome}: {f.descricao}")
        if param_str:
            linhas.append(f"  Parametros: {param_str}")
    return "\n".join(linhas)


def _parsear_tool_call(texto: str):
    import ast
    import re
    padrao_tags = r"MENSAGEM_TAGS(.*?)FIM_TAGS"
    match = re.search(padrao_tags, texto, re.DOTALL)
    if match:
        content = match.group(1).strip()
        # Try JSON first (double quotes)
        try:
            dados = json.loads(content)
            return dados.get("name"), dados.get("arguments", {})
        except json.JSONDecodeError:
            pass
        # Try Python literal (single quotes)
        try:
            # Extract name and arguments using regex for nested dicts
            name_match = re.search(r"'name'\s*:\s*'([^']+)'", content)
            args_match = re.search(r"'arguments'\s*:\s*(\{.*?\})", content, re.DOTALL)
            if name_match and args_match:
                name = name_match.group(1)
                args_str = args_match.group(1)
                # Parse arguments - handle simple case
                args = {}
                for kv_match in re.finditer(r"'(\w+)'\s*:\s*'([^']*)'", args_str):
                    args[kv_match.group(1)] = kv_match.group(2)
                return name_match.group(1), args
        except (ValueError, SyntaxError):
            pass

    padrao_json = r'(\{"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{[^}]*\}\s*\})'
    match = re.search(padrao_json, texto)
    if match:
        try:
            dados = json.loads(match.group(1))
            return dados.get("name"), dados.get("arguments", {})
        except json.JSONDecodeError:
            pass

    return None, None


def _testar_tools_support() -> bool:
    try:
        get_llama()
        return True
    except Exception:
        return False


_tools_support_cache: bool | None = None


def _modelo_suporta_tools() -> bool:
    global _tools_support_cache
    if _tools_support_cache is None:
        _tools_support_cache = _testar_tools_support()
    return _tools_support_cache


def loop_react(
    prompt_dict: dict[str, Any],
    fn_status: Callable[[str], None] | None = None,
    fn_passo: Callable[[Any], None] | None = None,
    fn_chunk: Callable[[str], None] | None = None,
    history: list[dict] | None = None,
) -> tuple[str, list[PassoReact]]:
    """Main ReAct loop using llama-cpp-python directly."""
    pergunta = prompt_dict.get("pergunta", "").strip()
    texto_doc = prompt_dict.get("documento", "").strip()
    nome_doc = prompt_dict.get("nome_documento", "").strip()
    caminho_doc = prompt_dict.get("caminho_documento", "").strip()
    memorias_ativas = prompt_dict.get("memorias_ativas", True)

    from core.memory import buscar_memorias
    memorias_relevantes = buscar_memorias(pergunta) if pergunta and memorias_ativas else []

    data_hora = datetime.now().strftime("%d/%m/%Y as %H:%M")

    usa_tools_nativo = False  # Force text-based format (MENSAGEM_TAGS) for this model

    if usa_tools_nativo:
        system_content = SYSTEM_PROMPT_REACT.format(data_hora=data_hora)
        ferramentas_openai = obter_schemas_openai()
    else:
        # Filter tools based on query relevance
        ferramentas_relevantes = _filtrar_ferramentas(pergunta)
        ferramentas_texto = _formatar_ferramentas_texto_filtrado(ferramentas_relevantes)
        system_content = SYSTEM_PROMPT_TOOLS_TEXT.format(
            data_hora=data_hora, ferramentas_texto=ferramentas_texto
        )
        ferramentas_openai = None

    if texto_doc:
        # Dynamic document truncation based on budget
        budget = get_budget()
        max_doc_chars = int(budget.document_max * 3.5)  # Convert tokens to chars
        max_doc_chars = min(max_doc_chars, 12000)  # Cap at 12000 chars
        
        doc_info = "\n## Documento Anexado\n"
        doc_info += f"Nome: {nome_doc}\n"
        if caminho_doc:
            doc_info += f"Caminho completo: {caminho_doc}\n"
        doc_info += "Conteudo ja extraido abaixo. NAO chame processar_arquivo novamente.\n"
        doc_info += "Analise o conteudo e responda diretamente ao pedido do usuario.\n"
        doc_info += f"Conteudo:\n{texto_doc[:max_doc_chars]}\n"
        system_content += doc_info

    if memorias_relevantes:
        memorias_texto = "\n".join(f"- {m}" for m in memorias_relevantes)
        memorias_section = (
            f"\n## Memorias do Usuario (INFORMACOES CONFIRMADAS PELO USUARIO)\n"
            f"{memorias_texto}\n"
        )
    else:
        memorias_section = ""

    if pergunta and not texto_doc:
        try:
            from ai.rag import buscar_contexto
            rag_chunks = buscar_contexto(pergunta)
            if rag_chunks:
                rag_context = "\n---\n".join(rag_chunks)
                system_content += (
                    f"\n## Contexto de Documentos Indexados\n"
                    f"{rag_context}\n"
                    f"Use este contexto para responder se for relevante.\n"
                )
        except Exception as e:
            logger.debug("RAG context search failed (non-blocking): %s", e)

    from ai.agents import classificar_tarefa, obter_prompt_agente
    agente = classificar_tarefa(pergunta) if pergunta else None
    if agente:
        agent_prompt = obter_prompt_agente(agente)
        if agent_prompt:
            system_content += f"\n## Modo Agente: {agente.nome}\n{agent_prompt}\n"

    mensagens = [{"role": "system", "content": system_content}]

    if history:
        budget = get_budget()
        trimmed_history = budget.trim_history(history)
        for msg in trimmed_history:
            mensagens.append(msg)
        # Log budget info if over 70%
        budget_info = budget.analyze_messages(mensagens)
        if budget_info["utilization"] > 0.70:
            pct = int(budget_info["utilization"] * 100)
            print(f"[ContextBudget] {pct}% do contexto usado ({budget_info['total_used']}/{budget_info['available']} tokens)")

    if memorias_section:
        mensagens.append({"role": "system", "content": memorias_section})

    pergunta_final = pergunta if pergunta else "Faca um resumo direto do arquivo anexado."
    mensagens.append({"role": "user", "content": pergunta_final})

    passos = []
    
    # Route to appropriate model based on query complexity
    multi_manager = get_multi_model_manager()
    has_document = bool(texto_doc)
    model_id, llama = multi_manager.route_and_invoke(pergunta, has_document=has_document)
    complexity = multi_manager.get_current_complexity()
    
    if fn_status:
        fn_status(f"Modelo: {model_id} ({complexity})")
    
    logger.info(f"ReAct: routing to {model_id} (complexity: {complexity})")

    for i in range(MAX_ITERACOES):
        if fn_status:
            fn_status(f"Raciocinando... (passo {i + 1})")

        try:
            kwargs = {
                "messages": mensagens,
                "temperature": 0.3,
                "max_tokens": min(NUM_PREDICT, 4096),
                "stream": True,
                "repeat_penalty": 1.05 if memorias_relevantes else 1.2,
                "frequency_penalty": 0.1 if memorias_relevantes else 0.3,
                "presence_penalty": 0.1 if memorias_relevantes else 0.3,
            }
            if usa_tools_nativo and ferramentas_openai:
                kwargs["tools"] = ferramentas_openai
                kwargs["tool_choice"] = "auto"

            stream = llama.create_chat_completion(**kwargs)
        except Exception as e:
            return f"Erro ao conectar com o LLM: {e}", passos

        conteudo_acumulado = ""
        tool_calls_acumulados = []
        tool_calls_buffer = {}
        tokens_repetidos = 0
        ultimo_token = ""
        thinking_emitted = False
        # Track if we're inside a tool call tag to suppress from user stream
        in_tool_call = False

        for chunk in stream:
            choice = chunk["choices"][0]
            delta = choice.get("delta", {})
            token = delta.get("content", "") or ""
            if token:
                if token == ultimo_token:
                    tokens_repetidos += 1
                    if tokens_repetidos > 10:
                        break
                else:
                    tokens_repetidos = 0
                    ultimo_token = token
                conteudo_acumulado += token
                
                # Track if we're entering/exiting a tool call tag
                if "MENSAGEM_TAGS" in conteudo_acumulado and not in_tool_call:
                    in_tool_call = True
                if "FIM_TAGS" in conteudo_acumulado and in_tool_call:
                    in_tool_call = False
                
                # Emit thinking/reasoning step on first content
                if not thinking_emitted and conteudo_acumulado.strip():
                    thinking_emitted = True
                    passo_pensamento = PassoReact("raciocinio", conteudo_acumulado)
                    passos.append(passo_pensamento)
                    if fn_passo:
                        fn_passo(passo_pensamento)
                
                # Only stream to user if NOT inside a tool call tag
                if fn_chunk and not in_tool_call:
                    fn_chunk(token)

            if usa_tools_nativo and delta.get("tool_calls"):
                for call in delta["tool_calls"]:
                    idx = call.get("index", 0)
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {"name": "", "arguments": ""}
                    if call["function"].get("name"):
                        tool_calls_buffer[idx]["name"] = call["function"]["name"]
                    if call["function"].get("arguments"):
                        tool_calls_buffer[idx]["arguments"] += call["function"]["arguments"]

        if not usa_tools_nativo and conteudo_acumulado:
            nome_tool, args_tool = _parsear_tool_call(conteudo_acumulado)
            if nome_tool:
                tool_calls_acumulados.append({"function": {"name": nome_tool, "arguments": args_tool}})
                texto_antes = re.sub(r"MENSAGEM_TAGS.*", "", conteudo_acumulado, flags=re.DOTALL)
                texto_antes = re.sub(r'\{"name".*', "", texto_antes).strip()
                conteudo_acumulado = texto_antes if len(texto_antes) > 50 else ""
            else:
                # Tool call attempted but failed - check if it's a chart request
                if "MENSAGEM_TAGS" in conteudo_acumulado:
                    grafico_kws = ["grafico", "gráfico", "chart", "barras", "pizza", "pie",
                                   "line", "area", "histograma", "dispersao", "scatter",
                                   "plotar", "plot", "visualizar"]
                    if any(kw in pergunta.lower() for kw in grafico_kws):
                        resposta_final = _fallback_grafico(pergunta, "")
                        if resposta_final:
                            passos.append(PassoReact("resposta", resposta_final))
                            return resposta_final, passos

        # Also try parsing raw JSON tool calls even when usa_tools_nativo is True
        # (some models output JSON instead of proper tool call deltas)
        if usa_tools_nativo and not tool_calls_buffer and conteudo_acumulado:
            nome_tool, args_tool = _parsear_tool_call(conteudo_acumulado)
            if nome_tool:
                tool_calls_acumulados.append({"function": {"name": nome_tool, "arguments": args_tool}})
                texto_antes = re.sub(r"MENSAGEM_TAGS.*", "", conteudo_acumulado, flags=re.DOTALL)
                texto_antes = re.sub(r'\{"name".*', "", texto_antes).strip()
                conteudo_acumulado = texto_antes if len(texto_antes) > 50 else ""
            else:
                # Tool call attempted but failed - check if it's a chart request
                if "MENSAGEM_TAGS" in conteudo_acumulado:
                    grafico_kws = ["grafico", "gráfico", "chart", "barras", "pizza", "pie",
                                   "line", "area", "histograma", "dispersao", "scatter",
                                   "plotar", "plot", "visualizar"]
                    if any(kw in pergunta.lower() for kw in grafico_kws):
                        resposta_final = _fallback_grafico(pergunta, "")
                        if resposta_final:
                            passos.append(PassoReact("resposta", resposta_final))
                            return resposta_final, passos

        if tool_calls_buffer:
            for idx in sorted(tool_calls_buffer.keys()):
                tc = tool_calls_buffer[idx]
                if tc["name"]:
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls_acumulados.append({"function": {"name": tc["name"], "arguments": args}})

        # Add assistant message if there's content OR tool calls
        if conteudo_acumulado or tool_calls_acumulados:
            if usa_tools_nativo:
                tool_calls_msg = None
                if tool_calls_acumulados:
                    tool_calls_msg = []
                    for j, call in enumerate(tool_calls_acumulados):
                        tool_calls_msg.append({
                            "id": f"call_{j}",
                            "type": "function",
                            "function": call["function"],
                        })
                mensagens.append({"role": "assistant", "content": conteudo_acumulado or "", "tool_calls": tool_calls_msg})
            else:
                mensagens.append({"role": "assistant", "content": conteudo_acumulado})

        # If tool call was attempted but failed (empty after MENSAGEM_TAGS strip),
        # try fallback for chart requests
        if not conteudo_acumulado.strip() and not tool_calls_acumulados:
            fallback = _fallback_grafico(pergunta, "")
            if fallback:
                passos.append(PassoReact("resposta", fallback))
                return fallback, passos

        if not tool_calls_acumulados:
            if conteudo_acumulado:
                passos.append(PassoReact("resposta", conteudo_acumulado))
                if fn_passo:
                    fn_passo(passos[-1])
                resposta_final = _limpar_resposta(conteudo_acumulado)
                resposta_final = _fallback_grafico(pergunta, resposta_final)
                return resposta_final, passos
            continue

        # If tool call was attempted but failed (empty after MENSAGEM_TAGS strip),
        # try fallback for chart requests
        if not conteudo_acumulado.strip() and not tool_calls_acumulados:
            fallback = _fallback_grafico(pergunta, "")
            if fallback:
                passos.append(PassoReact("resposta", fallback))
                return fallback, passos

        for j, call in enumerate(tool_calls_acumulados):
            nome_func = call["function"]["name"]
            args = call["function"]["arguments"]

            passo_acao = PassoReact("acao", str(args), ferramenta=nome_func)
            passos.append(passo_acao)
            if fn_passo:
                fn_passo(passo_acao)

            if fn_status:
                fn_status(f"Executando: {nome_func}...")

            resultado = executar_ferramenta(nome_func, args)

            passo_obs = PassoReact("observacao", "", resultado=resultado)
            passos.append(passo_obs)
            if fn_passo:
                fn_passo(passo_obs)

            if usa_tools_nativo:
                mensagens.append({
                    "role": "tool",
                    "tool_call_id": f"call_{j}",
                    "content": str(resultado),
                })
            else:
                mensagens.append({
                    "role": "user",
                    "content": f"Resultado de {nome_func}:\n{resultado}\n\nAgora continue com a proxima acao ou forneca a resposta final.",
                })

            gc.collect()

    resposta_fallback = (
        "Analisei a solicitacao mas nao consegui gerar uma resposta completa "
        "nas iteracoes disponiveis. Tente reformular a pergunta."
    )
    resposta_fallback = _fallback_grafico(pergunta, resposta_fallback)
    passos.append(PassoReact("resposta", resposta_fallback))
    return resposta_fallback, passos


def _limpar_resposta(texto: str) -> str:
    texto = re.sub(r"MENSAGEM_TAGS.*?FIM_TAGS", "", texto, flags=re.DOTALL)
    texto = re.sub(r"^[sS]ou o [cC]elsius,?\s*(seu\s+)?(assistente\s+)?(de\s+)?IA\.?\s*", "", texto)
    texto = re.sub(r"\(Nota:.*?\)", "", texto, flags=re.DOTALL)

    # Remove emojis repetidos no final da resposta
    texto = re.sub(r"([\U0001F300-\U0001F9FF])\1{3,}$", "", texto)
    # Remove tokens de lixo no final
    texto = re.sub(r"[\.]{5,}$", "...", texto)
    texto = re.sub(r"[-]{5,}$", "", texto)
    texto = re.sub(r"[=]{5,}$", "", texto)

    return texto.strip()


def _fallback_grafico(pergunta: str, resposta: str) -> str:
    """Detect chart requests that the LLM failed to generate and auto-generate."""
    import json
    import logging

    _log = logging.getLogger(__name__)

    grafico_keywords = ["grafico", "gráfico", "chart", "barras", "pizza", "pie",
                        "line", "area", "histograma", "dispersao", "scatter",
                        "plotar", "plot", "visualizar"]
    pergunta_lower = pergunta.lower()
    if not any(kw in pergunta_lower for kw in grafico_keywords):
        return resposta
    if "![" in resposta:
        return resposta

    from ai.tools import _tool_gerar_grafico

    tipo = "bar"
    if "pizza" in pergunta_lower or "pie" in pergunta_lower:
        tipo = "pie"
    elif "linha" in pergunta_lower or "line" in pergunta_lower:
        tipo = "line"
    elif "area" in pergunta_lower:
        tipo = "area"
    elif "histograma" in pergunta_lower or "histogram" in pergunta_lower:
        tipo = "histogram"
    elif "dispersao" in pergunta_lower or "scatter" in pergunta_lower:
        tipo = "scatter"

    try:
        from core.inventory import get_inventory_service
        service = get_inventory_service()
        itens = service.get_all_items()
        if not itens:
            _log.warning("[FallbackGrafico] Nenhum item no estoque")
            return resposta

        labels = json.dumps([i.nome[:20] for i in itens])
        valores = json.dumps([i.quantidade for i in itens])

        resultado = _tool_gerar_grafico(
            tipo=tipo,
            titulo="Estoque",
            labels=labels,
            valores=valores,
            ylabel="Quantidade",
        )

        if "Arquivo:" in resultado:
            caminho = resultado.split("Arquivo:")[1].split("\n")[0].strip()
            imagem_md = f"\n\n![Grafico - Estoque]({caminho})\n"
            _log.info("[FallbackGrafico] Grafico gerado: %s", caminho)
            return resposta + imagem_md
        else:
            _log.warning("[FallbackGrafico] Tool retornou: %s", resultado[:200])
    except Exception as e:
        _log.error("[FallbackGrafico] Erro: %s", e, exc_info=True)

    return resposta
