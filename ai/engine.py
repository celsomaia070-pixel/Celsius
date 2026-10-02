import gc
import logging
from collections.abc import Callable
from datetime import datetime

from ai.interruption import marcar_interrompida
from ai.react import (
    INTERNAL_CHAT_MARKERS,
    _agenda_prompt_context,
    _first_internal_marker_index,
    loop_react,
)
from core.commands import executar_comando
from core.direct_actions import youtube_open_arguments
from core.inventory import get_inventory_service
from core.message_intent import classify_intent
from core.operation_control import check_control, propagate_control
from core.quick_response import quick_response
from core.settings import get_settings
from core.turn_metrics import phase, track_turn
from core.web_research import is_web_lookup

logger = logging.getLogger(__name__)

RESPOSTAS_OLA = [
    "Ola! Em que posso ajudar?",
    "Oi! Como posso ajudar?",
    "Ola! Precisa de algo?",
]

RESPOSTAS_OBRIGADO = [
    "De nada! Se precisar de algo, e so chamar.",
    "Por nada! Estou aqui se precisar.",
    "Disponha! Qualquer coisa, e so falar.",
]

RESPOSTAS_TUDO_BEM = [
    "Tudo bem! Em que posso ajudar?",
    "Tudo otimo! O que precisa?",
    "Beleza! Como posso ajudar?",
]

RESPOSTAS_FUNCOES = (
    "Sou um agente multimodal com capacidades reais de acao:\n"
    "- Analise de documentos (PDF, DOCX, ODF) com metadados\n"
    "- Analise visual de imagens\n"
    "- Transcricao de audio\n"
    "- Execucao de codigo Python em sandbox\n"
    "- Pesquisa na internet em tempo real\n"
    "- Navegacao web automatizada\n"
    "- Indexacao semantica de documentos (RAG)\n"
    "- Memoria de longo prazo\n"
    "- Geracao de relatorios (PDF/DOCX)\n"
    "- Respostas por voz\n"
    "- Sistema multi-agente\n"
    "- Gerenciamento de estoque com Kanban\n"
    "  - Consultar itens, quantidades, status\n"
    "  - Registrar entradas e saidas\n"
    "  - Cadastrar novos itens\n"
    "  - Alertas de estoque minimo\n\n"
    "O que precisa?"
)


def _assistant_name() -> str:
    return get_settings().assistant.name


def _assistant_profile() -> str:
    return get_settings().assistant.profile


COMANDOS_RAPIDOS = {
    "quem e voce": lambda: (
        f"Sou o {_assistant_name()}, {_assistant_profile()}. Tenho capacidades reais de acao: processar arquivos, executar codigo, navegar na web, indexar documentos e muito mais. O que precisa?"
    ),
    "qual seu nome": lambda: f"Meu nome e {_assistant_name()}.",
    "seu nome": lambda: _assistant_name(),
    "me ajuda": "Claro! Me mande um arquivo, pergunte algo, ou peca para pesquisar na web. Tenho varias capacidades como agente.",
    "ajuda": "Me mande um arquivo, pergunte algo, ou peca para pesquisar na web.",
    "help": "Me mande um arquivo, pergunte algo, ou peca para pesquisar na web.",
    "o que voce faz": RESPOSTAS_FUNCOES,
    "o que voce sabe fazer": RESPOSTAS_FUNCOES,
    "suas funcoes": RESPOSTAS_FUNCOES,
    "quais suas funcionalidades": RESPOSTAS_FUNCOES,
    "me diga suas capacidades": RESPOSTAS_FUNCOES,
    "me diga as suas capacidades": RESPOSTAS_FUNCOES,
    "suas capacidades": RESPOSTAS_FUNCOES,
    "quais sao suas capacidades": RESPOSTAS_FUNCOES,
    "o que voce e": lambda: (
        f"Sou o {_assistant_name()}, {_assistant_profile()}. Nao sou um assistente basico - tenho capacidades reais de acao como processar documentos, executar codigo, navegar na web e muito mais."
    ),
    "voce e um assistente": lambda: (
        f"Sou o {_assistant_name()}, {_assistant_profile()}, com capacidades reais de acao. Posso processar documentos, executar codigo, navegar na web, indexar informacoes e muito mais."
    ),
}

HORAS_PADROES = [
    "que horas sao",
    "horas",
    "hora",
    "qual a hora",
    "que hora e",
    "hora atual",
    "horario",
    "qual o horario",
]

DATA_PADROES = [
    "que dia e hoje",
    "qual a data",
    "que data",
    "dia atual",
    "data atual",
]


def _formatar_data_atual() -> str:
    now = datetime.now()
    dias_semana = {
        0: "segunda-feira",
        1: "terca-feira",
        2: "quarta-feira",
        3: "quinta-feira",
        4: "sexta-feira",
        5: "sabado",
        6: "domingo",
    }
    return f"Data atual: {now.strftime('%d/%m/%Y')} ({dias_semana[now.weekday()]})"


def _is_lista_estoque_query(pergunta: str) -> bool:
    palavras = pergunta.lower().strip().split()
    if not palavras:
        return False
    verbos_lista = {
        "quais",
        "liste",
        "lista",
        "listar",
        "mostre",
        "mostrar",
        "exiba",
        "exibir",
        "quero",
        "preciso",
        "todos",
        "todas",
        "tudo",
    }
    alvos_estoque = {
        "pecas",
        "componentes",
        "itens",
        "estoque",
        "inventario",
        "produtos",
        "materiais",
        "peca",
        "componente",
        "item",
        "produto",
    }
    return bool(palavras[0] in verbos_lista or any(v in palavras for v in verbos_lista)) and any(
        a in palavras for a in alvos_estoque
    )


def _responder_lista_estoque_direta(pergunta: str) -> str | None:
    if not _is_lista_estoque_query(pergunta):
        return None
    try:
        itens = get_inventory_service().get_all_items()
    except Exception:
        return "Nao foi possivel ler os dados de estoque."
    if not itens:
        return "Nao ha dados de estoque registrados."

    linhas = ["Item | Quantidade | Categoria"]
    linhas.append("-" * 40)
    for item in itens:
        linhas.append(f"{item.nome} | {item.quantidade} | {item.categoria}")
    return "\n".join(linhas)


def _obter_contexto_estoque(pergunta: str) -> str:
    try:
        itens = get_inventory_service().get_all_items()
    except Exception:
        return ""
    if not itens:
        return ""

    linhas = [f"Dados do estoque do usuario ({len(itens)} itens):"]
    for item in itens[:50]:
        status = item.coluna.label
        extra = f" | Status: {status}" if status else ""
        linhas.append(f"- {item.nome}: {item.quantidade} unidades ({item.categoria}){extra}")
    if len(itens) > 50:
        linhas.append(f"... e mais {len(itens) - 50} itens.")
    return "\n".join(linhas)


def _responder_rapido(pergunta: str) -> str | None:
    return quick_response(pergunta)


def _normalizar_historico_recente(history: object, pergunta_atual: str) -> list[dict]:
    """Prepare recent chat history for the LLM without duplicating the current user turn."""
    if not isinstance(history, list):
        return []

    normalized = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = str(msg.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            normalized.append({"role": role, "content": content})

    if (
        normalized
        and pergunta_atual
        and normalized[-1]["role"] == "user"
        and normalized[-1]["content"].strip() == pergunta_atual.strip()
    ):
        normalized.pop()

    return normalized


@track_turn
@propagate_control
def gerar_resposta(
    prompt_dict: dict,
    fn_status: Callable[[str], None] | None = None,
    fn_passo: Callable[[object], None] | None = None,
    fn_chunk: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> str:
    check_control(should_cancel, prompt_dict.get("deadline"))
    pergunta_direta = prompt_dict.get("pergunta", "").strip()
    has_attachment = bool(
        prompt_dict.get("documento")
        or prompt_dict.get("anexos")
        or prompt_dict.get("caminho_imagem")
    )
    with phase("routing"):
        intent = classify_intent(pergunta_direta, has_attachment=has_attachment)
        response = quick_response(pergunta_direta, has_attachment=has_attachment)
    if response is not None:
        check_control(should_cancel, prompt_dict.get("deadline"))
        if fn_chunk:
            fn_chunk(response)
        return response
    from ai.task_runtime import handle_task_command

    task_response = handle_task_command(
        prompt_dict,
        settings=get_settings(),
        loop=loop_react,
        fn_status=fn_status,
        fn_passo=fn_passo,
        fn_chunk=fn_chunk,
        should_cancel=should_cancel,
    )
    if task_response is not None:
        return task_response
    texto_doc = prompt_dict.get("documento", "").strip()
    nome_doc = prompt_dict.get("nome_documento", "").strip()

    from core.tool_approval import get_tool_approval_store

    approval_store = get_tool_approval_store()
    approval_scope = str(prompt_dict.get("approval_scope", "")).strip()
    approval_command = approval_store.parse_command(pergunta_direta)
    if approval_command:
        action, code = approval_command
        if action == "CANCELAR":
            response = (
                "Acao cancelada. Nenhuma ferramenta foi executada."
                if approval_store.cancel(code, scope=approval_scope)
                else "Essa autorizacao nao existe ou ja expirou."
            )
        else:
            pending = approval_store.consume(code, scope=approval_scope)
            if pending is None:
                response = "Essa autorizacao nao existe, ja foi usada ou expirou."
            else:
                from ai.tools import executar_ferramenta

                if fn_status:
                    fn_status(f"Executando acao autorizada: {pending.tool}...")
                response = str(executar_ferramenta(pending.tool, pending.arguments))
        if fn_chunk:
            fn_chunk(response)
        return response

    if fn_status:
        if texto_doc and nome_doc:
            fn_status("Analisando documentos anexados...")
        else:
            fn_status("Elaborando a melhor resposta...")

    check_control(should_cancel, prompt_dict.get("deadline"))
    # Web searches need synthesis and source checks, rather than returning a
    # command shortcut's raw search-engine results as the assistant's answer.
    command_allowed = not is_web_lookup(pergunta_direta) or any(
        word in pergunta_direta.casefold() for word in ("abra ", "abrir ", "acesse ")
    )
    comando = (
        executar_comando(pergunta_direta)
        if intent.operational
        and command_allowed
        and not intent.needs_memory
        and not intent.needs_rag
        and not has_attachment
        and not youtube_open_arguments(pergunta_direta)
        else None
    )
    check_control(should_cancel, prompt_dict.get("deadline"))
    if comando:
        if fn_chunk:
            fn_chunk(comando)
        return comando

    if not texto_doc:
        resposta_rapida = _responder_rapido(pergunta_direta)
        if resposta_rapida:
            if fn_chunk:
                fn_chunk(resposta_rapida)
            return resposta_rapida

        resposta_estoque = (
            _responder_lista_estoque_direta(pergunta_direta) if intent.operational else None
        )
        check_control(should_cancel, prompt_dict.get("deadline"))
        if resposta_estoque:
            if fn_chunk:
                fn_chunk(resposta_estoque)
            return resposta_estoque

        # Inventory is retrieved by deterministic handlers or an inventory tool.
        # Injecting the complete JSON here made every unrelated prompt slower.

    history = _normalizar_historico_recente(prompt_dict.get("historico", []), pergunta_direta)

    resposta, _ = loop_react(
        prompt_dict,
        fn_status=fn_status,
        fn_passo=fn_passo,
        fn_chunk=fn_chunk,
        history=history,
        should_cancel=should_cancel,
    )

    gc.collect()
    return resposta


def _ensure_vision_manager(settings):
    """Return a manager with a loaded multimodal model and vision projector."""
    from core.llama_cpp import get_llama_manager

    manager = get_llama_manager()
    if manager._chat_handler:
        return manager

    vision_model_id = settings.model.vision_llm_model
    model_path = settings.get_model_path(vision_model_id)
    mmproj_path = settings.get_mmproj_path(vision_model_id)
    if not model_path.exists():
        raise FileNotFoundError(f"Modelo visual nao encontrado: {model_path}")
    if mmproj_path is None:
        raise FileNotFoundError(
            f"Projetor visual do modelo {vision_model_id} nao encontrado em resources/."
        )

    manager.switch_model(
        vision_model_id,
        n_gpu_layers=settings.model.n_gpu_layers,
        n_ctx=settings.model.num_ctx,
        n_batch=settings.model.n_batch,
        n_threads=settings.model.n_threads,
        use_mmap=settings.model.use_mmap,
        use_mlock=settings.model.use_mlock,
    )
    if not manager._chat_handler:
        raise RuntimeError(f"O modelo {vision_model_id} nao iniciou o suporte visual.")
    return manager


@track_turn
@propagate_control
def gerar_resposta_com_imagem(
    caminho_imagem: str,
    pergunta: str,
    fn_status: Callable[[str], None] | None = None,
    fn_chunk: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> str:
    import base64

    check_control(should_cancel)
    if fn_status:
        fn_status("Analisando imagem...")

    with open(caminho_imagem, "rb") as f:
        imagem_b64 = base64.b64encode(f.read()).decode("utf-8")
    check_control(should_cancel)

    if fn_status:
        fn_status("Interpretando conteudo visual...")

    pergunta_final = (
        pergunta if pergunta else "Descreva esta imagem em detalhes. Se houver texto, transcreva-o."
    )

    data_e_hora = datetime.now().strftime("%d/%m/%Y as %H:%M")
    settings = get_settings()
    customer_context = settings.customer_prompt_context
    response_style_context = settings.response_style_prompt_context
    agenda_context = _agenda_prompt_context()

    mensagens = [
        {
            "role": "system",
            "content": (
                f"Hoje e dia/horario {data_e_hora}.\n"
                "IMPORTANTE: Responda SEMPRE e EXCLUSIVAMENTE em portugues do Brasil.\n"
                "NUNCA use outro idioma. Todas as suas respostas DEVEM ser em portugues.\n\n"
                f"Voce e {settings.assistant.name}, {settings.assistant.profile}.\n"
                "Essa identidade e fixa: voce e Celsius.\n"
                f"{customer_context}\n\n"
                f"{agenda_context}\n\n"
                f"{response_style_context}\n\n"
                "Analise a imagem enviada e responda a pergunta do usuario.\n"
                "Se houver texto na imagem, transcreva-o.\n"
                "Nao comence se apresentando. Va direto ao assunto."
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": pergunta_final},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{imagem_b64}"}},
            ],
        },
    ]

    try:
        if fn_status:
            fn_status("Ativando modelo visual local...")
        llama = _ensure_vision_manager(settings)
        check_control(should_cancel)
        stream = llama.chat_completion(
            messages=mensagens,
            temperature=settings.response.temperature,
            max_tokens=2048,
            top_p=settings.response.top_p,
            stream=True,
            stop=list(INTERNAL_CHAT_MARKERS),
            should_cancel=should_cancel,
        )

        resposta = ""
        cancelado = False

        def _fechar_stream() -> None:
            close = getattr(stream, "close", None)
            if close is not None:
                import contextlib

                with contextlib.suppress(Exception):
                    close()

        try:
            for chunk in stream:
                check_control(should_cancel)
                token = chunk["choices"][0]["delta"].get("content", "") or ""
                combined = resposta + token
                marker_idx = _first_internal_marker_index(combined)
                if marker_idx >= 0:
                    token = combined[len(resposta) : marker_idx]
                    resposta = combined[:marker_idx]
                    if token and fn_chunk:
                        fn_chunk(token)
                    break
                resposta += token
                if fn_chunk:
                    fn_chunk(token)
        finally:
            _fechar_stream()
        check_control(should_cancel)
        if cancelado:
            if fn_status:
                fn_status("Resposta interrompida.")
            return marcar_interrompida(resposta)
        resultado = resposta.strip()
        return resultado
    except Exception as e:
        import traceback

        traceback.print_exc()
        return f"Erro ao analisar imagem: {e}. Nota: O modelo atual pode nao suportar visao. Use um modelo multimodal (ex: Qwen2.5-VL, LLaVA) com arquivo mmproj para suporte a imagens."
