"""Cheap, shared routing. No model, embeddings, storage or network imports."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or "").casefold())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", folded).split())


def strip_task_prefix(text: str) -> str:
    return re.sub(r"^\s*TAREFA\s*:\s*", "", str(text or ""), flags=re.I).strip()


@dataclass(frozen=True)
class MessageIntent:
    kind: str
    text: str
    quick_key: str = ""
    explicit_task: bool = False
    needs_memory: bool = False
    needs_rag: bool = False

    @property
    def operational(self) -> bool:
        return self.kind in {"tools", "task"}


_SOCIAL = r"(?:ola|oi|bom dia|boa tarde|boa noite|e ai)(?: celsius)?"
_IDENTITY = r"(?:quem e (?:voce|vc)|qual (?:e )?(?:o )?seu nome|seu nome|o que (?:voce|vc) e|voce e um assistente)"
_CAPABILITIES = (
    r"(?:(?:me diga|diga|quais(?: sao)?) (?:as )?(?:suas )?"
    r"(?:capacidades|funcoes|funcionalidades|habilidades|ferramentas)|"
    r"(?:as )?suas (?:capacidades|funcoes|funcionalidades|habilidades|ferramentas)|"
    r"o que (?:voce |vc )?(?:faz|sabe fazer|pode (?:fazer|realizar))|ajuda|help|me ajuda)"
)
_DOMAIN = r"\b(?:estoque|inventario|pecas?|componentes?|itens?|quantidades?|movimentacoes|clientes?|fornecedores?|documentos?|arquivos?|pasta|agenda|compromissos?|orcamentos?|relatorios?|memorias?|lembretes?|reuniao|catalogo|produtos?|vendas?|contratos?|formularios?|planilhas?|anexos?|reposicao|prazos?|vencimentos?|cotad\w*|armazenad\w*|arquivad\w*|guardad\w*|pdf|docx|odt|word|pei|paee|pdi)\b"
_READ = r"\b(?:consulte|consultar|mostre|mostra|mostrar|liste|listar|leia|ler|busque|buscar|procure|procurar|verifique|verificar|pesquise|pesquisar|analise|analisar|resuma|resumir|inspecione|inspecionar|veja|ver)\b"
_WRITE = r"\b(?:gere|gerar|crie|criar|salve|salvar|preencha|preencher|edite|editar|execute|executar|rode|rodar|cadastre|cadastrar|registre|registrar|adicione|adicionar|remova|remover|exclua|excluir|apague|apagar|envie|enviar|mande|mandar|agende|agendar|organize|organizar|converta|converter|faca|exporte|exportar|implemente|implementar|atualize|atualizar|abra|abrir|entrada|baixa)\b"
_WEB = r"\b(?:pesquis\w*|noticias?|internet|web|google|previsao|meteorolog\w*|cotacao|clima|ultimas novidades)\b"


def has_local_source(text: str) -> bool:
    words = normalize_text(strip_task_prefix(text))
    return bool(
        re.search(
            r"\b(?:nas?|nos?|em|pelas?|pelos?|minhas?|meus?) "
            r"(?:(?:minhas?|meus?|nossas?|nossos?|suas?|seus?) )?"
            r"(?:memorias?|documentos?|arquivos?|anexos?|estoque|inventario|base)\b",
            words,
        )
    )


def is_local_memory_read(text: str) -> bool:
    words = normalize_text(strip_task_prefix(text))
    return (
        has_local_source(text)
        and bool(re.search(r"\bmemorias?\b", words))
        and not bool(re.search(_WRITE, words))
        and not bool(
            re.search(
                r"\b(?:web|internet|google|estoque|inventario|documentos?|arquivos?|anexos?)\b",
                words,
            )
        )
    )


def classify_intent(text: str, *, has_attachment: bool = False) -> MessageIntent:
    raw = str(text or "").strip()
    explicit = bool(re.match(r"^TAREFA\s*:", raw, re.I))
    body = strip_task_prefix(raw)
    words = normalize_text(body)
    if re.match(r"^(?:AUTORIZAR\s|CANCELAR\s|RETOMAR\s|TAREFAS\s*$)", raw, re.I):
        return MessageIntent("control", raw)
    # A greeting may precede a request; it never decides the rest of the sentence.
    remainder = re.sub(rf"^{_SOCIAL}\b\s*", "", words).strip()
    quick = ""
    if not has_attachment:
        if re.fullmatch(_SOCIAL, words) or re.fullmatch(
            r"(?:tudo bem(?: com voce)?|tudo bom|como vai|como (?:voce )?esta|obrigad[oa]|valeu|tchau|ate logo)",
            remainder or words,
        ):
            quick = "social"
        elif re.fullmatch(_IDENTITY, remainder or words):
            quick = "identity"
        elif (
            re.fullmatch(_CAPABILITIES, remainder or words)
            or re.fullmatch(rf"{_IDENTITY} e {_CAPABILITIES}", remainder or words)
            or re.fullmatch(rf"{_CAPABILITIES}(?: e)? {_CAPABILITIES}", remainder or words)
        ):
            quick = "capabilities"
        elif re.fullmatch(
            r"(?:que horas sao|qual (?:e )?(?:a )?hora|hora atual|horas|horario)", words
        ):
            quick = "time"
        elif re.fullmatch(
            r"(?:que dia e hoje|qual (?:e )?(?:a )?data(?: de hoje)?|data atual|dia atual)", words
        ):
            quick = "date"
    if quick:
        return MessageIntent("conversation", body, quick, explicit)
    own = bool(
        re.search(
            r"\b(?:meu|minha|meus|minhas|tenho|temos|guardei|guardado|indexad\w*|anexad\w*|lembre|lembrar)\b",
            words,
        )
    ) or words in {"quem sou eu", "o que voce sabe sobre mim"}
    conceptual = bool(
        re.match(
            r"^(?:(?:me |pode me )?explique|o que e|o que sao|qual (?:e )?a diferenca|como (?:funciona|organizar|criar|gerar|preencher))\b",
            remainder or words,
        )
    )
    domain = bool(re.search(_DOMAIN, words))
    read = bool(re.search(_READ, words))
    web = bool(re.search(_WEB, words)) and not conceptual
    write = bool(re.search(_WRITE, words)) and not conceptual
    code_request = (
        bool(re.search(r"\b(?:codigo|script|programa)\b", words))
        and bool(
            re.search(
                r"\b(?:monte|montar|desenvolva|construa|corrija|implemente|rode|execute|crie|gerar|gere)\b",
                words,
            )
        )
        and not conceptual
    )
    personal = words in {"quem sou eu", "o que voce sabe sobre mim"} or bool(
        re.search(
            r"\b(?:memorias?|ja conversamos|conversas anteriores|lembra|lembre|lembrar)\b", words
        )
    )
    system_query = bool(
        re.search(
            r"\b(?:informacoes (?:do )?sistema|ip desta maquina|processos em execucao)\b", words
        )
    )
    operational = (
        has_attachment
        or (domain and not conceptual)
        or (own and read)
        or web
        or code_request
        or personal
        or system_query
        or words in {"quem sou eu", "o que voce sabe sobre mim"}
    )
    kind = "task" if explicit or write or code_request else "tools" if operational else "general"
    if conceptual and not own and not explicit and not has_attachment:
        kind = "general"
    needs_rag = (
        kind in {"tools", "task"}
        and bool(
            re.search(
                r"\b(?:documentos?|base|indexad\w*|pei|paee|pdi|aluno|segundo o arquivo)\b", words
            )
        )
        and not has_attachment
    )
    return MessageIntent(kind, raw, "", explicit, kind in {"tools", "task"} and personal, needs_rag)
