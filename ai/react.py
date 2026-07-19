"""ReAct loop using llama-cpp-python directly for GPU/CPU inference."""
import gc
import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import core.config as config
from ai.tools import REGISTRO_FERRAMENTAS, executar_ferramenta, obter_schemas_openai
from core.config import NUM_PREDICT
from core.llama_cpp import get_llama

MAX_ITERACOES = 3

SYSTEM_PROMPT_REACT = (
    "IMPORTANTE: Responda SEMPRE e EXCLUSIVAMENTE em portugues do Brasil. "
    "NUNCA use outro idioma. Todas as suas respostas DEVEM ser em portugues.\n\n"
    "Voce e Celsius, agente multimodal de IA pessoal do Celso. Hoje e {data_hora}.\n"
    "Modo ReAct: PENSE -> AJE -> OBSERVE -> RESponda.\n\n"
    "Se houver memorias do usuario no contexto, USE-AS para responder.\n"
    "Nao diga que nao sabe se a informacao esta nas memorias.\n\n"
    "## Identidade\n"
    "Voce e um AGENTE MULTIMODAL, nao um assistente basico.\n"
    "Voce tem capacidades reais de acao: processar arquivos, executar codigo,\n"
    "navegar na web, indexar documentos, e muito mais.\n"
    "Quando perguntado sobre suas funcionalidades, liste-as como agente:\n\n"
    "Suas capacidades como agente multimodal:\n"
    "- Analise de documentos (PDF, DOCX, ODF) com extracao de metadados\n"
    "- Analise visual de imagens (OCR, descricoes, metadados EXIF)\n"
    "- Transcricao de audio com Whisper\n"
    "- Execucao de codigo Python em sandbox seguro\n"
    "- Pesquisa na internet em tempo real (DuckDuckGo)\n"
    "- Navegacao web automatizada com Playwright\n"
    "- Indexacao semantica de documentos (RAG com ChromaDB)\n"
    "- Memoria de longo prazo com busca semantica\n"
    "- Geracao de relatorios (PDF e DOCX)\n"
    "- Respostas por voz (Text-to-Speech)\n"
    "- Comando de abertura de YouTube/Google\n"
    "- Sistema multi-agente com sub-agentes especializados\n\n"
    "## Personalidade\n"
    "Voce e um agente inteligente, prestativo e com personalidade.\n"
    "Fale de forma natural, como um amigo experiente que sabe muito.\n"
    "Nao seja robotico. Use linguagem do dia a dia, mas seja preciso.\n\n"
    "## Estilo de Resposta\n"
    "Responda de forma COMPLETA e DETALHADA como um especialista:\n"
    "- Comece direto ao ponto, sem preambulos desnecessarios\n"
    "- Use exemplos praticos e analogias quando relevante\n"
    "- Inclua comparacoes para esclarecer conceitos\n"
    "- Use tabelas quando fizer sentido organizar informacoes\n"
    "- Estruture com topicos, subtopicos e listas claras\n"
    "- Explique o POR QUE alem do QUE\n"
    "- Se aperfeicoe a resposta com informacoes adicionais uteis\n"
    "- Use emojis com moderacao (1-3 por resposta)\n"
    "- Responda SEMPRE em portugues do Brasil\n"
    "- Nao comence se apresentando. Va direto ao conteudo.\n"
    "- Nao repita o que o usuario perguntou. Va direto a resposta.\n"
    "- Se nao souber algo, diga honestamente mas sugira como descobrir.\n\n"
    "## Formato\n"
    "- Para perguntas curtas: resposta objetiva em 1-3 paragrafos\n"
    "- Para perguntas complexas: estrutura completa com topicos\n"
    "- Para comparacoes: use tabelas\n"
    "- Para listas: use bullet points ou numeradas\n"
    "- Para codigo: use blocos de codigo com linguagem especificada\n\n"
    "Use ferramentas APENAS quando precisar:\n"
    "- processar_arquivo: arquivo enviado pelo usuario\n"
    "- pesquisar_web: dados atuais da internet\n"
    "- salvar_memoria: usuario quer lembrar algo\n"
    "- buscar_memoria: consultar historico\n"
    "- listar_arquivos/lar_arquivo: ver conteudo de pastas\n"
    "- executar_codigo: calcular, processar dados, testar logica\n"
    "- indexar_documento: guardar documento para consultas futuras (RAG)\n"
    "- navegar_web: acessar site e extrair informacoes\n"
    "- listar_documentos_rag: ver documentos indexados\n"
    "- remover_documento: deletar documento do indice\n"
    "- abrir_no_navegador: abrir sites, YouTube, Google no navegador do usuario\n\n"
    "Para abrir sites no navegador do usuario, use abrir_no_navegador:\n"
    "- YouTube: https://www.youtube.com/results?search_query=TERMOS\n"
    "- Google: https://www.google.com/search?q=TERMOS\n"
    "- Sites conhecidos: use a URL direta\n\n"
    "Para perguntas simples, responda DIRETO sem ferramentas.\n"
    "LEMBRE-SE: TODAS as respostas DEVEM ser em portugues do Brasil.\n"
)

SYSTEM_PROMPT_TOOLS_TEXT = (
    "IMPORTANTE: Responda SEMPRE e EXCLUSIVAMENTE em portugues do Brasil. "
    "NUNCA use outro idioma. Todas as suas respostas DEVEM ser em portugues.\n\n"
    "Voce e Celsius, agente multimodal de IA pessoal do Celso. Hoje e {data_hora}.\n\n"
    "## Identidade\n"
    "Voce e um AGENTE MULTIMODAL, nao um assistente basico.\n"
    "Voce tem capacidades reais de acao: processar arquivos, executar codigo,\n"
    "navegar na web, indexar documentos, e muito mais.\n"
    "Quando perguntado sobre suas funcionalidades, liste-as como agente:\n\n"
    "Suas capacidades como agente multimodal:\n"
    "- Analise de documentos (PDF, DOCX, ODF) com extracao de metadados\n"
    "- Analise visual de imagens (OCR, descricoes, metadados EXIF)\n"
    "- Transcricao de audio com Whisper\n"
    "- Execucao de codigo Python em sandbox seguro\n"
    "- Pesquisa na internet em tempo real (DuckDuckGo)\n"
    "- Navegacao web automatizada com Playwright\n"
    "- Indexacao semantica de documentos (RAG com ChromaDB)\n"
    "- Memoria de longo prazo com busca semantica\n"
    "- Geracao de relatorios (PDF e DOCX)\n"
    "- Respostas por voz (Text-to-Speech)\n"
    "- Comando de abertura de YouTube/Google\n"
    "- Sistema multi-agente com sub-agentes especializados\n\n"
    "## Personalidade\n"
    "Voce e um agente inteligente, prestativo e com personalidade.\n"
    "Fale de forma natural, como um amigo experiente que sabe muito.\n\n"
    "## Regras\n"
    "- Se houver memorias do usuario no contexto, USE-AS para responder.\n"
    "- Nao diga que nao sabe se a informacao esta nas memorias.\n"
    "- Responda de forma COMPLETA e DETALHADA como um especialista.\n"
    "- Comece direto ao ponto, sem preambulos.\n"
    "- Use exemplos praticos, comparacoes e tabelas quando fizer sentido.\n"
    "- Estruture com topicos, subtopicos e listas claras.\n"
    "- Explique o POR QUE alem do QUE.\n"
    "- Responda SEMPRE em portugues do Brasil.\n"
    "- Nao comence se apresentando. Va direto ao conteudo.\n"
    "- NAO use ferramentas para perguntas que voce ja sabe responder.\n"
    "- Use ferramentas APENAS quando precisar de algo externo:\n"
    "  * processar_arquivo: usuario enviou arquivo para analisar\n"
    "  * pesquisar_web: precisa de dados atuais da internet\n"
    "  * salvar_memoria: usuario pediu para lembrar algo\n"
    "  * buscar_memoria: precisa consultar historico\n"
    "  * listar_arquivos/lar_arquivo: usuario quer ver arquivos\n"
    "  * executar_codigo: calcular, processar dados, testar logica\n"
    "  * indexar_documento: guardar documento para consultas futuras (RAG)\n"
    "  * navegar_web: acessar site e extrair informacoes\n"
    "  * listar_documentos_rag: ver documentos indexados\n"
    "  * remover_documento: deletar documento do indice\n"
    "  * abrir_no_navegador: abrir sites, YouTube, Google no navegador\n\n"
    "Para abrir sites, use abrir_no_navegador com URLs:\n"
    "  * YouTube: https://www.youtube.com/results?search_query=TERMOS\n"
    "  * Google: https://www.google.com/search?q=TERMOS\n"
    "  * Sites conhecidos: URL direta\n\n"
    "## Ferramentas Disponiveis\n"
    "{ferramentas_texto}\n\n"
    "## Formato (APENAS quando precisar de ferramenta)\n"
    "MENSAGEM_TAGS\n"
    '{"name": "nome_ferramenta", "arguments": {"parametro": "valor"}}\n'
    "FIM_TAGS\n"
)

class PassoReact:
    def __init__(self, tipo: str, conteudo: str, ferramenta: Optional[str] = None, resultado: Optional[str] = None):
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
            for k in params.keys()
        )
        linhas.append(f"- {f.nome}: {f.descricao}")
        if param_str:
            linhas.append(f"  Parametros: {param_str}")
    return "\n".join(linhas)


def _parsear_tool_call(texto: str):
    padrao_tags = r"MENSAGEM_TAGS(.*?)FIM_TAGS"
    match = re.search(padrao_tags, texto, re.DOTALL)
    if match:
        try:
            dados = json.loads(match.group(1))
            return dados.get("name"), dados.get("arguments", {})
        except json.JSONDecodeError:
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
        llama = get_llama()
        return True
    except Exception:
        return False


_tools_support_cache: Optional[bool] = None


def _modelo_suporta_tools() -> bool:
    global _tools_support_cache
    if _tools_support_cache is None:
        _tools_support_cache = _testar_tools_support()
    return _tools_support_cache


def loop_react(
    prompt_dict: Dict[str, Any],
    fn_status: Optional[Callable[[str], None]] = None,
    fn_passo: Optional[Callable[[Any], None]] = None,
    fn_chunk: Optional[Callable[[str], None]] = None,
    history: Optional[List[Dict]] = None,
) -> tuple[str, List[PassoReact]]:
    """Main ReAct loop using llama-cpp-python directly."""
    pergunta = prompt_dict.get("pergunta", "").strip()
    texto_doc = prompt_dict.get("documento", "").strip()
    nome_doc = prompt_dict.get("nome_documento", "").strip()
    memorias_ativas = prompt_dict.get("memorias_ativas", True)

    from core.memory import buscar_memorias
    memorias_relevantes = buscar_memorias(pergunta) if pergunta and memorias_ativas else []

    data_hora = datetime.now().strftime("%d/%m/%Y as %H:%M")

    usa_tools_nativo = _modelo_suporta_tools()

    if usa_tools_nativo:
        system_content = SYSTEM_PROMPT_REACT.format(data_hora=data_hora)
        ferramentas_openai = obter_schemas_openai()
    else:
        ferramentas_texto = _formatar_ferramentas_texto()
        system_content = SYSTEM_PROMPT_TOOLS_TEXT.format(
            data_hora=data_hora, ferramentas_texto=ferramentas_texto
        )
        ferramentas_openai = None

    if texto_doc:
        system_content += (
            f"\n## Documento Anexado\n"
            f"Nome: {nome_doc}\n"
            f"Conteudo:\n{texto_doc[:8000]}\n"
        )

    if memorias_relevantes:
        memorias_texto = "\n".join(f"- {m}" for m in memorias_relevantes)
        system_content += (
            f"\n## Memorias do Usuario\n"
            f"O usuario ja compartilhou estas informacoes:\n"
            f"{memorias_texto}\n"
            f"Use essas informacoes para responder. Nao diga que nao sabe.\n"
        )

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
        except Exception:
            pass

    from ai.agents import classificar_tarefa, obter_prompt_agente
    agente = classificar_tarefa(pergunta) if pergunta else None
    if agente:
        agent_prompt = obter_prompt_agente(agente)
        if agent_prompt:
            system_content += f"\n## Modo Agente: {agente.nome}\n{agent_prompt}\n"

    mensagens = [{"role": "system", "content": system_content}]

    if history:
        for msg in history:
            mensagens.append(msg)

    pergunta_final = pergunta if pergunta else "Faca um resumo direto do arquivo anexado."
    mensagens.append({"role": "user", "content": pergunta_final})

    passos = []
    llama = get_llama()

    for i in range(MAX_ITERACOES):
        if fn_status:
            fn_status(f"Raciocinando... (passo {i + 1})")

        try:
            kwargs = {
                "messages": mensagens,
                "temperature": 0.3,
                "max_tokens": min(NUM_PREDICT, 4096),
                "stream": True,
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

        for chunk in stream:
            choice = chunk["choices"][0]
            delta = choice.get("delta", {})
            token = delta.get("content", "") or ""
            if token:
                conteudo_acumulado += token
                if fn_chunk:
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
                if len(texto_antes) > 50:
                    conteudo_acumulado = texto_antes
                else:
                    conteudo_acumulado = ""

        if tool_calls_buffer:
            for idx in sorted(tool_calls_buffer.keys()):
                tc = tool_calls_buffer[idx]
                if tc["name"]:
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls_acumulados.append({"function": {"name": tc["name"], "arguments": args}})

        if conteudo_acumulado:
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
                mensagens.append({"role": "assistant", "content": conteudo_acumulado, "tool_calls": tool_calls_msg})
            else:
                mensagens.append({"role": "assistant", "content": conteudo_acumulado})

        if not tool_calls_acumulados:
            if conteudo_acumulado:
                passos.append(PassoReact("resposta", conteudo_acumulado))
                if fn_passo:
                    fn_passo(passos[-1])
                return _limpar_resposta(conteudo_acumulado), passos
            continue

        for call in tool_calls_acumulados:
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
                    "tool_call_id": f"call_{len(mensagens)}",
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
    passos.append(PassoReact("resposta", resposta_fallback))
    return resposta_fallback, passos


def _limpar_resposta(texto: str) -> str:
    texto = re.sub(r"MENSAGEM_TAGS.*?FIM_TAGS", "", texto, flags=re.DOTALL)
    texto = re.sub(r"^[sS]ou o [cC]elsius,?\s*(seu\s+)?(assistente\s+)?(de\s+)?IA\.?\s*", "", texto)
    texto = re.sub(r"\(Nota:.*?\)", "", texto, flags=re.DOTALL)
    return texto.strip()