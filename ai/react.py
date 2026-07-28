"""ReAct loop using native OpenAI tool calling via llama-cpp-python."""

import gc
import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ai.context_budget import get_budget
from ai.tools import REGISTRO_FERRAMENTAS, executar_ferramenta
from core.config import get_settings
from core.llama_cpp import get_multi_model_manager
from core.telemetry import trace_span

logger = logging.getLogger(__name__)

MAX_ITERACOES = 5

SYSTEM_PROMPT_REACT = (
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
    "CHAME a ferramenta gerar_grafico. NUNCA apenas descreva os dados.\n"
    "SEMPRE gere o grafico. NUNCA sugira Excel/Google Sheets/Canva.\n"
    "Mesmo que os dados ja estejam no contexto, CHAME gerar_grafico para criar a imagem visual.\n"
    "Apos chamar a ferramenta, inclua o resultado na resposta:\n"
    "![Grafico - Titulo](caminho_retornado_pela_ferramenta)\n\n"
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
    "- 'ultimas noticias sobre [algo]' -> pesquisar_noticias(query='ultimas noticias sobre [algo]')\n"
    "- 'abra o site [url]' -> abrir_no_navegador(url='[url]')\n\n"
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
    def __init__(
        self, tipo: str, conteudo: str, ferramenta: str | None = None, resultado: str | None = None
    ):
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
            preview = (
                self.resultado[:200] + "..." if len(self.resultado or "") > 200 else self.resultado
            )
            return f"Observacao: {preview}"
        elif self.tipo == "resposta":
            return None
        return self.conteudo


def _formatar_ferramentas_texto() -> str:
    linhas = []
    for f in REGISTRO_FERRAMENTAS:
        params = f.schema.get("properties", {})
        required = f.schema.get("required", [])
        param_str = ", ".join(f"{k}" + (" (obrigatorio)" if k in required else "") for k in params)
        linhas.append(f"- {f.nome}: {f.descricao}")
        if param_str:
            linhas.append(f"  Parametros: {param_str}")
    return "\n".join(linhas)


def _filtrar_ferramentas(pergunta: str) -> list:
    """Filter tools based on query relevance."""
    keywords_map = {
        "pesquisar_web": [
            "pesquisar",
            "buscar",
            "procurar",
            "web",
            "internet",
            "atual",
            "hoje",
            "agora",
            "preco",
            "noticia",
        ],
        "pesquisar_google": ["google", "buscar no google", "pesquisa google"],
        "pesquisar_noticias": [
            "noticia",
            "noticias",
            "ultimas",
            "recentes",
            "atualidades",
            "aconteceu",
            "jornal",
        ],
        "navegar_web": ["navegar", "extrair", "scraping", "scrape", "extrair conteudo"],
        "abrir_no_navegador": [
            "abrir",
            "abre",
            "abrir site",
            "abrir no navegador",
            "youtube",
            "google",
            "abrir no browser",
            "abra o site",
            "abrir site",
        ],
        "executar_codigo": ["codigo", "python", "calcular", "script", "programa", "executar"],
        "salvar_memoria": ["lembrar", "memoria", "salvar", "guarda", "anota"],
        "buscar_memoria": [
            "lembra",
            "memoria",
            "buscar memoria",
            "o que eu disse",
            "o que eu falei",
        ],
        "listar_arquivos": ["listar", "arquivos", "pasta", "diretorio", "arquivos na"],
        "ler_arquivo": ["ler arquivo", "abrir arquivo", "conteudo do arquivo"],
        "processar_arquivo": [
            "processar",
            "analisar arquivo",
            "arquivo pdf",
            "arquivo doc",
            "arquivo odt",
        ],
        "informacoes_sistema": ["sistema", "info", "versao", "python", "so"],
        "indexar_documento": ["indexar", "guardar documento", "indexar documento", "rag"],
        "listar_documentos_rag": ["listar documentos", "documentos indexados", "documentos no rag"],
        "remover_documento": ["remover documento", "deletar documento", "apagar documento"],
        "listar_estoque": [
            "estoque",
            "itens",
            "peças",
            "pecas",
            "produtos",
            "inventario",
            "quais itens",
            "resumo do estoque",
        ],
        "buscar_item_estoque": ["estoque", "quantidade", "tem de", "tenho", "quanto", "item"],
        "entrada_estoque": [
            "entrada",
            "recebi",
            "comprei",
            "entrou",
            "adicionar estoque",
            "repor",
            "reposicao",
            "aumentar estoque",
        ],
        "saida_estoque": [
            "saida",
            "usei",
            "enviei",
            "vendi",
            "removeu",
            "diminuir estoque",
            "gastei",
            "consumi",
        ],
        "adicionar_item_estoque": [
            "cadastrar item",
            "novo item",
            "adicionar item",
            "cadastrar produto",
            "novo produto",
            "item novo",
        ],
        "itens_estoque_baixo": [
            "estoque baixo",
            "estoque minimo",
            "critico",
            "precisa repor",
            "repicao",
            "itens baixos",
            "alerta",
        ],
        "historico_movimentacoes": [
            "historico",
            "movimentacoes",
            "ultimas entradas",
            "ultimas saidas",
            "log de estoque",
        ],
        "gerar_grafico": [
            "grafico",
            "graficos",
            "chart",
            "barras",
            "pizza",
            "pie",
            "line",
            "area",
            "histograma",
            "dispersao",
            "scatter",
            "visualizar",
            "visualizar dados",
            "plotar",
            "plot",
        ],
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
        if f.nome.startswith(
            (
                "listar_estoque",
                "buscar_item_estoque",
                "entrada_estoque",
                "saida_estoque",
                "adicionar_item_estoque",
                "itens_estoque_baixo",
                "historico_movimentacoes",
            )
        ):
            relevant_tools.add(f.nome)

    return [f for f in REGISTRO_FERRAMENTAS if f.nome in relevant_tools]


def _formatar_ferramentas_texto_filtrado(ferramentas: list) -> str:
    """Format only the given list of tools."""
    linhas = []
    for f in ferramentas:
        params = f.schema.get("properties", {})
        required = f.schema.get("required", [])
        param_str = ", ".join(f"{k}" + (" (obrigatorio)" if k in required else "") for k in params)
        linhas.append(f"- {f.nome}: {f.descricao}")
        if param_str:
            linhas.append(f"  Parametros: {param_str}")
    return "\n".join(linhas)


def loop_react(
    prompt_dict: dict[str, Any],
    fn_status: Callable[[str], None] | None = None,
    fn_passo: Callable[[Any], None] | None = None,
    fn_chunk: Callable[[str], None] | None = None,
    history: list[dict] | None = None,
) -> tuple[str, list[PassoReact]]:
    """Main ReAct loop using native OpenAI tool calling."""
    pergunta = prompt_dict.get("pergunta", "").strip()
    texto_doc = prompt_dict.get("documento", "").strip()
    nome_doc = prompt_dict.get("nome_documento", "").strip()
    caminho_doc = prompt_dict.get("caminho_documento", "").strip()
    memorias_ativas = prompt_dict.get("memorias_ativas", True)

    from core.memory import buscar_memorias

    memorias_relevantes = buscar_memorias(pergunta) if pergunta and memorias_ativas else []

    data_hora = datetime.now().strftime("%d/%m/%Y as %H:%M")

    ferramentas_relevantes = _filtrar_ferramentas(pergunta)
    ferramentas_openai = [f.para_openai() for f in ferramentas_relevantes]
    system_content = SYSTEM_PROMPT_REACT.format(data_hora=data_hora)

    if texto_doc:
        budget = get_budget()
        max_doc_chars = int(budget.document_max * 3.5)
        max_doc_chars = min(max_doc_chars, 12000)

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
            f"\n## Memorias do Usuario (INFORMACOES CONFIRMADAS PELO USUARIO)\n{memorias_texto}\n"
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
        budget_info = budget.analyze_messages(mensagens)
        if budget_info["utilization"] > 0.70:
            pct = int(budget_info["utilization"] * 100)
            logger.info(
                "Context budget usage: %s%% (%s/%s tokens)",
                pct,
                budget_info["total_used"],
                budget_info["available"],
            )

    if memorias_section:
        mensagens.append({"role": "system", "content": memorias_section})

    pergunta_final = pergunta if pergunta else "Faca um resumo direto do arquivo anexado."
    mensagens.append({"role": "user", "content": pergunta_final})

    passos = []

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

        with trace_span("react.llm_call", {"model": model_id, "iteration": i}) as span:
            try:
                kwargs = {
                    "messages": mensagens,
                    "temperature": 0.3,
                    "max_tokens": min(get_settings().num_predict, 4096),
                    "stream": True,
                    "repeat_penalty": 1.05 if memorias_relevantes else 1.2,
                    "frequency_penalty": 0.1 if memorias_relevantes else 0.3,
                    "presence_penalty": 0.1 if memorias_relevantes else 0.3,
                    "tools": ferramentas_openai,
                    "tool_choice": "auto",
                }

                stream = llama.create_chat_completion(**kwargs)
            except Exception as e:
                span.set_attribute("error", str(e))
                return f"Erro ao conectar com o LLM: {e}", passos

            conteudo_acumulado = ""
            tool_calls_buffer: dict[int, dict[str, str]] = {}
            tokens_repetidos = 0
            ultimo_token = ""
            thinking_emitted = False

            for chunk in stream:
                choice = chunk["choices"][0]
                delta = choice.get("delta", {})
                content = delta.get("content") or ""
                if content:
                    if content == ultimo_token:
                        tokens_repetidos += 1
                        if tokens_repetidos > 10:
                            break
                    else:
                        tokens_repetidos = 0
                        ultimo_token = content
                    conteudo_acumulado += content

                    if not thinking_emitted and conteudo_acumulado.strip():
                        thinking_emitted = True
                        passo_pensamento = PassoReact("raciocinio", conteudo_acumulado)
                        passos.append(passo_pensamento)
                        if fn_passo:
                            fn_passo(passo_pensamento)

                    if fn_chunk:
                        fn_chunk(content)

                if delta.get("tool_calls"):
                    for call in delta["tool_calls"]:
                        idx = call.get("index", 0)
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {"name": "", "arguments": ""}
                        fn_data = call.get("function", {})
                        if fn_data.get("name"):
                            tool_calls_buffer[idx]["name"] = fn_data["name"]
                        if fn_data.get("arguments"):
                            tool_calls_buffer[idx]["arguments"] += fn_data["arguments"]

            span.set_attribute("content_length", len(conteudo_acumulado))
            span.set_attribute("tool_calls_count", len(tool_calls_buffer))

        tool_calls_acumulados = []
        if tool_calls_buffer:
            for idx in sorted(tool_calls_buffer.keys()):
                tc = tool_calls_buffer[idx]
                if tc["name"]:
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse tool call arguments for %s", tc["name"])
                        args = {}
                    tool_calls_acumulados.append(
                        {"function": {"name": tc["name"], "arguments": args}}
                    )

        if conteudo_acumulado or tool_calls_acumulados:
            tool_calls_msg = None
            if tool_calls_acumulados:
                tool_calls_msg = []
                for j, call in enumerate(tool_calls_acumulados):
                    tool_calls_msg.append(
                        {
                            "id": f"call_{j}",
                            "type": "function",
                            "function": call["function"],
                        }
                    )
            mensagens.append(
                {
                    "role": "assistant",
                    "content": conteudo_acumulado or "",
                    "tool_calls": tool_calls_msg,
                }
            )

        if not tool_calls_acumulados:
            if conteudo_acumulado:
                passos.append(PassoReact("resposta", conteudo_acumulado))
                if fn_passo:
                    fn_passo(passos[-1])
                resposta_final = _limpar_resposta(conteudo_acumulado)
                resposta_final = _fallback_grafico(pergunta, resposta_final)
                return resposta_final, passos
            continue

        for j, call in enumerate(tool_calls_acumulados):
            nome_func = call["function"]["name"]
            args = call["function"]["arguments"]

            passo_acao = PassoReact("acao", str(args), ferramenta=nome_func)
            passos.append(passo_acao)
            if fn_passo:
                fn_passo(passo_acao)

            if fn_status:
                fn_status(f"Executando: {nome_func}...")

            with trace_span(
                "react.tool_execution",
                {"tool": nome_func, "args": json.dumps(args, ensure_ascii=False)[:200]},
            ) as tool_span:
                resultado = executar_ferramenta(nome_func, args)
                tool_span.set_attribute("result_length", len(str(resultado)))

            passo_obs = PassoReact("observacao", "", resultado=resultado)
            passos.append(passo_obs)
            if fn_passo:
                fn_passo(passo_obs)

            mensagens.append(
                {
                    "role": "tool",
                    "tool_call_id": f"call_{j}",
                    "content": str(resultado),
                }
            )

            gc.collect()

    resposta_fallback = (
        "Analisei a solicitacao mas nao consegui gerar uma resposta completa "
        "nas iteracoes disponiveis. Tente reformular a pergunta."
    )
    resposta_fallback = _fallback_grafico(pergunta, resposta_fallback)
    passos.append(PassoReact("resposta", resposta_fallback))
    return resposta_fallback, passos


def _limpar_resposta(texto: str) -> str:
    texto = re.sub(r"^[sS]ou o [cC]elsius,?\s*(seu\s+)?(assistente\s+)?(de\s+)?IA\.?\s*", "", texto)
    texto = re.sub(r"\(Nota:.*?\)", "", texto, flags=re.DOTALL)
    texto = re.sub(r"([\U0001F300-\U0001F9FF])\1{3,}$", "", texto)
    texto = re.sub(r"[\.]{5,}$", "...", texto)
    texto = re.sub(r"[-]{5,}$", "", texto)
    texto = re.sub(r"[=]{5,}$", "", texto)
    return texto.strip()


def _fallback_grafico(pergunta: str, resposta: str) -> str:
    """Detect chart requests that the LLM failed to generate and auto-generate."""
    import json
    import logging

    _log = logging.getLogger(__name__)

    grafico_keywords = [
        "grafico",
        "gráfico",
        "chart",
        "barras",
        "pizza",
        "pie",
        "line",
        "area",
        "histograma",
        "dispersao",
        "scatter",
        "plotar",
        "plot",
        "visualizar",
    ]
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
