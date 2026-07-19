import gc
import random
from collections.abc import Callable
from datetime import datetime

import core.config as config
from ai.react import loop_react
from core.commands import executar_comando
from core.config import get_settings
from core.memory import get_memory_service

MAX_HISTORICO_SESSION = get_settings().max_history_session

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
    "- Sistema multi-agente\n\n"
    "O que precisa?"
)

COMANDOS_RAPIDOS = {
    "quem e voce": "Sou o Celsius, um agente multimodal de IA. Tenho capacidades reais de acao: processar arquivos, executar codigo, navegar na web, indexar documentos e muito mais. O que precisa?",
    "quem sou eu": "Voce e o Celso, meu criador!",
    "qual seu nome": "Meu nome e Celsius.",
    "seu nome": "Celsius.",
    "me ajuda": "Claro! Me mande um arquivo, pergunte algo, ou peca para pesquisar na web. Tenho varias capacidades como agente.",
    "ajuda": "Me mande um arquivo, pergunte algo, ou peca para pesquisar na web.",
    "help": "Me mande um arquivo, pergunte algo, ou peca para pesquisar na web.",
    "o que voce faz": RESPOSTAS_FUNCOES,
    "o que voce sabe fazer": RESPOSTAS_FUNCOES,
    "suas funcoes": RESPOSTAS_FUNCOES,
    "quais suas funcionalidades": RESPOSTAS_FUNCOES,
    "o que voce e": "Sou o Celsius, um agente multimodal de IA. Nao sou um assistente basico — tenho capacidades reais de acao como processar documentos, executar codigo, navegar na web e muito mais.",
    "voce e um assistente": "Nao sou um mero assistente. Sou um agente multimodal de IA com capacidades reais de acao. Posso processar documentos, executar codigo, navegar na web, indexar informacoes e muito mais.",
}

HORAS_PADROES = [
    "que horas sao", "horas", "hora", "qual a hora",
    "que hora e", "hora atual", "horario", "qual o horario",
]


def _eh_pergunta_simples(texto: str) -> bool:
    limpo = texto.lower().strip()
    for char in "?!.,":
        limpo = limpo.replace(char, "")
    limpo = limpo.strip()
    return (
        limpo in COMANDOS_RAPIDOS
        or limpo in {"ola", "oi", "bom dia", "boa tarde", "boa noite"}
        or limpo in {"obrigado", "obrigada", "valeu", "thanks"}
        or limpo in {"tudo bem", "como vai", "como esta", "como voce esta"}
        or limpo in HORAS_PADROES
    )


def _responder_rapido(pergunta: str) -> str | None:
    limpo = pergunta.lower().strip()
    for char in "?!.,":
        limpo = limpo.replace(char, "")
    limpo = limpo.strip()

    if limpo in HORAS_PADROES or any(h in limpo for h in ["hora", "horario"]):
        return f"Hora atual: {datetime.now().strftime('%H:%M')}"

    if limpo in COMANDOS_RAPIDOS:
        return COMANDOS_RAPIDOS[limpo]

    if limpo in {"ola", "oi", "bom dia", "boa tarde", "boa noite"}:
        return random.choice(RESPOSTAS_OLA)

    if limpo in {"obrigado", "obrigada", "valeu", "thanks"}:
        return random.choice(RESPOSTAS_OBRIGADO)

    if limpo in {"tudo bem", "como vai", "como esta", "como voce esta"}:
        return random.choice(RESPOSTAS_TUDO_BEM)

    return None


class ConversationContext:
    """Manages conversation history for a session."""

    def __init__(self, max_history: int = MAX_HISTORICO_SESSION):
        self.max_history = max_history
        self.history: list[dict] = []

    def add_user(self, content: str) -> None:
        self.history.append({"role": "user", "content": content})
        self._trim()

    def add_assistant(self, content: str) -> None:
        self.history.append({"role": "assistant", "content": content})
        self._trim()

    def _trim(self) -> None:
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_history(self) -> list[dict]:
        return self.history.copy()

    def clear(self) -> None:
        self.history.clear()


# Global session context (could be per-window in future)
_session_context = ConversationContext()


def gerar_resposta(
    prompt_dict: dict,
    fn_status: Callable[[str], None] | None = None,
    fn_passo: Callable[[object], None] | None = None,
    fn_chunk: Callable[[str], None] | None = None,
) -> str:
    settings = get_settings()
    pergunta_direta = prompt_dict.get("pergunta", "").strip()
    texto_doc = prompt_dict.get("documento", "").strip()
    memoriasativas = prompt_dict.get("memorias_ativas", True)

    if not texto_doc:
        comando = executar_comando(pergunta_direta)
        if comando:
            if fn_chunk:
                fn_chunk(comando)
            return comando

        resposta_rapida = _responder_rapido(pergunta_direta)
        if resposta_rapida:
            if fn_chunk:
                fn_chunk(resposta_rapida)
            return resposta_rapida

    # Get relevant memories
    memory_service = get_memory_service()
    memorias = memory_service.search(pergunta_direta) if pergunta_direta and memoriasativas else []

    # Inject memories into prompt if available
    if memorias:
        prompt_dict["_memorias"] = memorias

    # Get conversation history for context
    history = _session_context.get_history()

    resposta, passos = loop_react(
        prompt_dict,
        fn_status=fn_status,
        fn_passo=fn_passo,
        fn_chunk=fn_chunk,
        history=history,
    )

    _session_context.add_user(pergunta_direta if pergunta_direta else "[Analise de arquivo]")
    _session_context.add_assistant(resposta)

    gc.collect()
    return resposta


def gerar_resposta_com_imagem(
    caminho_imagem: str,
    pergunta: str,
    fn_status: Callable[[str], None] | None = None,
    fn_chunk: Callable[[str], None] | None = None,
) -> str:
    import base64
    from openai import OpenAI

    settings = get_settings()

    if fn_status:
        fn_status("Analisando imagem...")

    with open(caminho_imagem, "rb") as f:
        imagem_b64 = base64.b64encode(f.read()).decode("utf-8")

    pergunta_final = pergunta if pergunta else "Descreva esta imagem em detalhes. Se houver texto, transcreva-o."

    data_e_hora = datetime.now().strftime("%d/%m/%Y as %H:%M")

    mensagens_api = [
        {
            "role": "system",
            "content": (
                f"Hoje e dia/horario {data_e_hora}.\n"
                "IMPORTANTE: Responda SEMPRE e EXCLUSIVAMENTE em portugues do Brasil.\n"
                "NUNCA use outro idioma. Todas as suas respostas DEVEM ser em portugues.\n\n"
                "Voce e Celsius, um agente de IA especialista.\n"
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
        client_config = get_llama_client_config()
        client = OpenAI(**client_config)
        stream = client.chat.completions.create(
            model=config.MODELO_LLM,
            messages=mensagens_api,
            temperature=0.7,
            max_tokens=settings.num_predict,
            stream=True,
        )

        resposta = ""
        for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            resposta += token
            if fn_chunk:
                fn_chunk(token)
        return resposta.strip()
    except Exception as e:
        return f"Erro ao analisar imagem: {e}"


def get_session_context() -> ConversationContext:
    return _session_context


def clear_session_context() -> None:
    _session_context.clear()
