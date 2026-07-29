import gc
import logging
import random
from collections.abc import Callable
from datetime import datetime

from ai.react import INTERNAL_CHAT_MARKERS, _first_internal_marker_index, loop_react
from core.commands import executar_comando
from core.settings import get_settings

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


def _responder_rapido(pergunta: str) -> str | None:
    limpo = pergunta.lower().strip()
    for char in "?!.,":
        limpo = limpo.replace(char, "")
    limpo = limpo.strip()

    import re

    if limpo in HORAS_PADROES or re.search(r"\bhoras?\b|\bhorario\b", limpo):
        return f"Hora atual: {datetime.now().strftime('%H:%M')}"

    if limpo in DATA_PADROES or re.search(r"\bdata\b", limpo):
        return _formatar_data_atual()

    if limpo in COMANDOS_RAPIDOS:
        resposta = COMANDOS_RAPIDOS[limpo]
        return resposta() if callable(resposta) else resposta

    if limpo in {"ola", "oi", "bom dia", "boa tarde", "boa noite"}:
        return random.choice(RESPOSTAS_OLA)

    if limpo in {"obrigado", "obrigada", "valeu", "thanks"}:
        return random.choice(RESPOSTAS_OBRIGADO)

    if limpo in {"tudo bem", "como vai", "como esta", "como voce esta"}:
        return random.choice(RESPOSTAS_TUDO_BEM)

    return None


class ConversationContext:
    """Manages conversation history for a session with smart summarization."""

    def __init__(self, max_history: int | None = None):
        self.max_history = max_history or get_settings().max_history_session
        self.history: list[dict] = []

    def add_user(self, content: str) -> None:
        self.history.append({"role": "user", "content": content})
        self._trim()

    def add_assistant(self, content: str) -> None:
        self.history.append({"role": "assistant", "content": content})
        self._trim()

    def _trim(self) -> None:
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

    def get_history(self) -> list[dict]:
        return self.history.copy()

    def clear(self) -> None:
        self.history.clear()


def _detectar_intencao_estoque(pergunta: str) -> str | None:
    """Detecta se a intencao e entrada, saida ou adicionar item novo."""
    t = pergunta.lower()
    # Saida: rebaixa, baixa, diminui, saida, remove, usa, gasta, envia, vende
    saida_kw = [
        "dê baixa",
        "baixa",
        "diminui",
        " dê saida",
        "saida",
        "remove",
        "removeu",
        "usei",
        "usou",
        "gastei",
        "consumi",
        "enviei",
        "enviou",
        "vendi",
        "vendeu",
        "tirar",
        "tirou",
        "menos",
    ]
    if any(kw in t for kw in saida_kw):
        return "saida"
    # Entrada: entrada, adicione, adiciona, recebi, comprou, entrou, repor, mais, aumenta
    entrada_kw = [
        "entrada",
        "adicione",
        "adiciona",
        "recebi",
        "comprei",
        "comprou",
        "entrou",
        "repor",
        "reposicao",
        "aumenta",
        "mais",
        "plus",
    ]
    if any(kw in t for kw in entrada_kw):
        return "entrada"
    return None


def _extrair_quantidade(pergunta: str) -> int | None:
    """Extrai quantidade numerica da pergunta."""
    import re

    # Padroes: "5 unidades", "5 esticadores", "em 5", "5 pecas"
    m = re.search(r"(\d+)\s*(unidade|unidades|un|peça|pecas|estoque)?", pergunta)
    if m:
        return int(m.group(1))
    # Por extenso
    extenso = {
        "um": 1,
        "uma": 1,
        "dois": 2,
        "duas": 2,
        "tres": 3,
        "quatro": 4,
        "cinco": 5,
        "seis": 6,
        "sete": 7,
        "oito": 8,
        "nove": 9,
        "dez": 10,
        "vinte": 20,
        "trinta": 30,
        "cinquenta": 50,
    }
    pergunta_lower = pergunta.lower()
    for palavra, num in extenso.items():
        if re.search(rf"\b{palavra}\b", pergunta_lower):
            return num
    return None


def _processar_operacao_estoque(pergunta: str) -> str | None:
    """Detecta e executa operacoes de entrada/saida no estoque. Retorna resultado ou None."""
    from core.inventory import get_inventory_service

    intencao = _detectar_intencao_estoque(pergunta)
    if not intencao:
        return None

    quantidade = _extrair_quantidade(pergunta)
    if not quantidade or quantidade <= 0:
        return None

    service = get_inventory_service()
    itens = service.get_all_items()
    if not itens:
        return None

    # Buscar item por nome na pergunta
    pergunta_lower = pergunta.lower()
    item_encontrado = None
    for item in itens:
        palavras_nome = item.nome.lower().split()
        for p in palavras_nome:
            if len(p) > 2 and p in pergunta_lower:
                item_encontrado = item
                break
        if item_encontrado:
            break

    if not item_encontrado:
        return None  # Nao conseguiu identificar o item, deixa o LLM tentar

    if intencao == "entrada":
        mov = service.entrada(item_encontrado.id, quantidade)
        if mov:
            return (
                f"Entrada registrada com sucesso!\n"
                f"Item: {mov.item_nome}\n"
                f"Quantidade adicionada: +{mov.quantidade} un.\n"
                f"Estoque anterior: {mov.quantidade_anterior} | Estoque atual: {mov.quantidade_nova}"
            )
    elif intencao == "saida":
        if quantidade > item_encontrado.quantidade:
            return (
                f"OPERACAO NEGADA: Saida de {quantidade} un. de '{item_encontrado.nome}' impossivel.\n"
                f"Estoque disponivel: {item_encontrado.quantidade} un."
            )
        mov = service.saida(item_encontrado.id, quantidade)
        if mov:
            alerta = ""
            if item_encontrado.precisa_repor:
                alerta = f"\n**ALERTA: Estoque do item '{item_encontrado.nome}' esta no minimo ({item_encontrado.estoque_min})!**"
            return (
                f"Saida registrada com sucesso!\n"
                f"Item: {mov.item_nome}\n"
                f"Quantidade removida: -{mov.quantidade} un.\n"
                f"Estoque anterior: {mov.quantidade_anterior} | Estoque atual: {mov.quantidade_nova}{alerta}"
            )

    return None


def _is_inventory_general_query(pergunta: str) -> bool:
    pergunta_lower = pergunta.lower()
    general_terms = {
        "estoque",
        "inventario",
        "inventário",
        "itens",
        "item",
        "produtos",
        "produto",
        "mercadorias",
        "mercadoria",
        "insumos",
    }
    list_terms = {
        "quais",
        "qual",
        "listar",
        "lista",
        "liste",
        "mostrar",
        "mostra",
        "mostre",
        "ver",
        "todos",
        "todas",
        "completo",
        "completa",
        "geral",
        "resumo",
        "relacao",
        "relação",
        "meu estoque",
        "todo estoque",
        "estoque completo",
    }
    specific_terms = {
        "quanto de",
        "quantos",
        "quantas",
        "tem de",
        "tenho de",
        "tenho do",
        "tenho da",
        "quantidade de",
    }
    if any(term in pergunta_lower for term in specific_terms):
        return False
    return any(term in pergunta_lower for term in general_terms) and any(
        term in pergunta_lower for term in list_terms
    )


def _formatar_contexto_estoque_completo(itens, coluna_kanban) -> str:
    by_coluna = {}
    for item in itens:
        by_coluna.setdefault(item.localizacao, []).append(item)

    linhas = []
    for col in coluna_kanban:
        group = sorted(by_coluna.get(col.value, []), key=lambda item: item.nome.lower())
        if group:
            linhas.append(f"\n[{col.label}]")
            for item in group:
                status = "CRITICO" if item.precisa_repor else "OK"
                linhas.append(
                    f"  - {item.nome} (ID:{item.id}) | {item.categoria} | "
                    f"{item.quantidade} un. | min:{item.estoque_min} max:{item.estoque_max} | {status}"
                )
    return "\n".join(linhas)


def _responder_lista_estoque_direta(pergunta: str) -> str | None:
    """Return a deterministic full inventory list for broad listing requests."""

    if not _is_inventory_general_query(pergunta):
        return None

    from core.inventory import ColunaKanban, get_inventory_service

    service = get_inventory_service()
    itens = service.get_all_items()
    if not itens:
        return "O estoque esta vazio. Nenhum item cadastrado."

    total = len(itens)
    total_unidades = sum(item.quantidade for item in itens)
    criticos = sum(1 for item in itens if item.precisa_repor)
    contexto = _formatar_contexto_estoque_completo(itens, ColunaKanban)
    return (
        f"Estoque completo: {total} item(ns), {total_unidades} unidade(s) no total, "
        f"{criticos} item(ns) em alerta.\n"
        "Segue a lista completa cadastrada:\n"
        f"{contexto}"
    )


def _obter_contexto_estoque(pergunta: str) -> str:
    """Obtem dados relevantes do estoque para injetar no contexto."""
    from core.inventory import ColunaKanban, get_inventory_service

    service = get_inventory_service()
    pergunta_lower = pergunta.lower()

    itens = service.get_all_items()
    if not itens:
        return "Estoque: Nenhum item cadastrado."

    is_general_query = _is_inventory_general_query(pergunta)

    # Palavras genericas que NAO indicam busca especifica
    palavras_genericas = {
        "quais",
        "nome",
        "nomes",
        "itens",
        "item",
        "estoque",
        "tenho",
        "listar",
        "lista",
        "mostrar",
        "mostra",
        "ver",
        "todos",
        "todas",
        "completo",
        "completa",
        "total",
        "resumo",
        "produto",
        "produtos",
        "sao",
        "são",
        "dos",
        "das",
        "meu",
        "minha",
        "aqui",
    }

    # Busca especifica por nome (ex: "martelo", "arame").
    # Para perguntas gerais ("quais produtos tenho?", "meu estoque completo"),
    # nao deixe categorias genericas filtrarem o inventario por acidente.
    termos_busca = []
    if not is_general_query:
        for item in itens:
            palavras = item.nome.lower().split()
            matched = False
            for p in palavras:
                if len(p) > 2 and p in pergunta_lower and p not in palavras_genericas:
                    termos_busca.append(item)
                    matched = True
                    break
            categoria = item.categoria.lower().strip()
            if (
                not matched
                and categoria
                and categoria not in palavras_genericas
                and categoria in pergunta_lower
            ):
                termos_busca.append(item)

    # Se achou match ESPECIFICO (nome de item real), retorna so esses
    if termos_busca:
        linhas = []
        for item in termos_busca:
            status = "CRITICO" if item.precisa_repor else "OK"
            linhas.append(
                f"- {item.nome} (ID:{item.id}) | {item.categoria} | "
                f"{item.quantidade} un. | min:{item.estoque_min} max:{item.estoque_max} | {status}"
            )
        return "Dados do estoque (itens encontrados):\n" + "\n".join(linhas)

    # Caso geral: lista COMPLETA (nenhum nome especifico detectado)
    total = len(itens)
    criticos = sum(1 for i in itens if i.precisa_repor)
    return (
        f"Dados do estoque do usuario ({total} itens, {criticos} em estoque critico).\n"
        f"IMPORTANTE: Listar TODOS os itens, incluindo os em estoque critico/abaixo do minimo.\n"
        + _formatar_contexto_estoque_completo(itens, ColunaKanban)
    )


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


def gerar_resposta(
    prompt_dict: dict,
    fn_status: Callable[[str], None] | None = None,
    fn_passo: Callable[[object], None] | None = None,
    fn_chunk: Callable[[str], None] | None = None,
) -> str:
    pergunta_direta = prompt_dict.get("pergunta", "").strip()
    texto_doc = prompt_dict.get("documento", "").strip()
    nome_doc = prompt_dict.get("nome_documento", "").strip()

    if fn_status:
        if texto_doc and nome_doc and nome_doc != "Dados do Estoque":
            fn_status("Analisando documentos anexados...")
        else:
            fn_status("Elaborando a melhor resposta...")

    # Comandos diretos sempre rodam (independente do historico)
    comando = executar_comando(pergunta_direta)
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

    # Processar operacoes de estoque (entrada/saida) direto
    if pergunta_direta:
        resultado_estoque = _processar_operacao_estoque(pergunta_direta)
        if resultado_estoque:
            if fn_chunk:
                fn_chunk(resultado_estoque)
            return resultado_estoque

    resposta_estoque_direta = _responder_lista_estoque_direta(pergunta_direta)
    if resposta_estoque_direta:
        if fn_chunk:
            fn_chunk(resposta_estoque_direta)
        return resposta_estoque_direta

    # Sempre injetar dados do estoque no contexto para que o assistente
    # tenha acesso total ao inventário em qualquer pergunta
    try:
        if fn_status:
            fn_status("Consultando dados do estoque...")
        contexto_estoque = _obter_contexto_estoque(pergunta_direta or "")
        if contexto_estoque:
            prompt_dict = dict(prompt_dict)
            doc_existente = prompt_dict.get("documento", "")
            prompt_dict["documento"] = (
                doc_existente + "\n\n### Dados do Estoque (SEMPRE DISPONIVEL)\n" + contexto_estoque
            ).strip()
            if not nome_doc:
                prompt_dict["nome_documento"] = "Dados do Estoque"
    except Exception as e:
        logger.warning("Falha ao injetar contexto de estoque: %s", e)

    history = _normalizar_historico_recente(prompt_dict.get("historico", []), pergunta_direta)

    resposta, _ = loop_react(
        prompt_dict,
        fn_status=fn_status,
        fn_passo=fn_passo,
        fn_chunk=fn_chunk,
        history=history,
    )

    gc.collect()
    return resposta


def gerar_resposta_com_imagem(
    caminho_imagem: str,
    pergunta: str,
    fn_status: Callable[[str], None] | None = None,
    fn_chunk: Callable[[str], None] | None = None,
) -> str:
    import base64

    from core.llama_cpp import get_llama

    if fn_status:
        fn_status("Analisando imagem...")

    with open(caminho_imagem, "rb") as f:
        imagem_b64 = base64.b64encode(f.read()).decode("utf-8")

    if fn_status:
        fn_status("Interpretando conteudo visual...")

    pergunta_final = (
        pergunta if pergunta else "Descreva esta imagem em detalhes. Se houver texto, transcreva-o."
    )

    data_e_hora = datetime.now().strftime("%d/%m/%Y as %H:%M")
    settings = get_settings()
    customer_context = settings.customer_prompt_context
    response_style_context = settings.response_style_prompt_context

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
        from core.llama_cpp import get_llama_manager

        mgr = get_llama_manager()
        if not mgr._chat_handler:
            return "Erro: O modelo carregado não possui suporte a visão (handler não inicializado). Verifique se o modelo é multimodal (ex: Qwen2.5-VL) e se o arquivo mmproj existe na pasta resources/."

        llama = get_llama()
        stream = llama.chat_completion(
            messages=mensagens,
            temperature=settings.response.temperature,
            max_tokens=2048,
            top_p=settings.response.top_p,
            stream=True,
            stop=list(INTERNAL_CHAT_MARKERS),
        )

        resposta = ""
        for chunk in stream:
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
        resultado = resposta.strip()
        return resultado
    except Exception as e:
        import traceback

        traceback.print_exc()
        return f"Erro ao analisar imagem: {e}. Nota: O modelo atual pode nao suportar visao. Use um modelo multimodal (ex: Qwen2.5-VL, LLaVA) com arquivo mmproj para suporte a imagens."
