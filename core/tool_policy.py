"""Deterministic tool-risk policy that complements the Jev/Kev decision layer.

The probabilistic guard (``core.decisions.decide_tool_guard``) can only *raise*
the risk of a tool call. It can never lower it. This module owns the mandatory
part of the rule set so sensitive actions never depend on a 0.5B model:

* **read** — consultations and readings run without confirmation;
* **write** — creation/update of persisted data requires confirmation;
* **destructive** — deletion, stock write-off, file removal require confirmation;
* **external** — anything that leaves this machine requires confirmation;
* **irreversible** — actions that cannot be undone require confirmation;
* **unknown** — a tool with no declared policy fails *closed* (confirm).

The policy is intentionally data-driven (a small table) so it is cheap, testable
and stable across decision-provider outages.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.tool_approval import SENSITIVE_TOOLS

logger = logging.getLogger(__name__)

#: Arguments longer than this are truncated before being logged/audited.
ARGS_PREVIEW_LIMIT = 240


class Risk(str, Enum):
    """How much damage a call can do if it is wrong."""

    READ = "read"
    DERIVED = "derived"  # creates a brand-new file, never overwrites
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


#: Risk classes that always need an explicit, one-time user confirmation.
CONFIRMING_RISKS: frozenset[Risk] = frozenset(
    {Risk.WRITE, Risk.DESTRUCTIVE, Risk.EXTERNAL, Risk.IRREVERSIBLE}
)

#: Human (pt-BR) label per risk class, used in the approval cards.
RISK_LABELS: dict[Risk, str] = {
    Risk.READ: "Somente leitura",
    Risk.DERIVED: "Geracao de novo arquivo",
    Risk.WRITE: "Alteracao de dados",
    Risk.DESTRUCTIVE: "Acao destrutiva",
    Risk.EXTERNAL: "Acao externa",
    Risk.IRREVERSIBLE: "Acao irreversivel",
    Risk.UNKNOWN: "Sem politica definida",
}


@dataclass(frozen=True)
class ToolPolicy:
    """Declarative rule for one tool."""

    risk: Risk
    reason: str
    #: Extra argument names that, when truthy, escalate the call by one level.
    escalating_arguments: tuple[str, ...] = ()
    #: Optional callable-ish check name; kept declarative so the table stays
    #: serializable and trivially testable.
    requires_confirmation: bool | None = None

    def resolve(self, arguments: Mapping[str, Any]) -> bool:
        if self.requires_confirmation is not None:
            return self.requires_confirmation
        return self.risk in CONFIRMING_RISKS


# ── The policy table ───────────────────────────────────────────
#
# Only *current* Celsius tools are listed. Anything missing is Risk.UNKNOWN and
# therefore fails closed. Extend this table when a tool is added to ai/tools.py.

_POLICIES: dict[str, ToolPolicy] = {
    # ── Leitura pura ───────────────────────────────────────────
    "buscar_item_estoque": ToolPolicy(Risk.READ, "Consulta de estoque, apenas leitura."),
    "buscar_memoria": ToolPolicy(Risk.READ, "Consulta a memorias do usuario."),
    "historico_movimentacoes": ToolPolicy(Risk.READ, "Consulta do historico de estoque."),
    "informacoes_sistema": ToolPolicy(Risk.READ, "Informacoes do sistema, apenas leitura."),
    "itens_estoque_baixo": ToolPolicy(Risk.READ, "Consulta de itens abaixo do minimo."),
    "ler_arquivo": ToolPolicy(Risk.READ, "Leitura de arquivo do disco."),
    "listar_agenda": ToolPolicy(Risk.READ, "Consulta da agenda local."),
    "listar_arquivos": ToolPolicy(Risk.READ, "Listagem de diretorios, apenas leitura."),
    "listar_clientes": ToolPolicy(Risk.READ, "Consulta de clientes cadastrados."),
    "listar_documentos_rag": ToolPolicy(Risk.READ, "Consulta de documentos indexados."),
    "listar_estoque": ToolPolicy(Risk.READ, "Consulta de estoque, apenas leitura."),
    "listar_fornecedores": ToolPolicy(Risk.READ, "Consulta de fornecedores cadastrados."),
    "listar_orcamentos": ToolPolicy(Risk.READ, "Consulta de orcamentos cadastrados."),
    "listar_processos_prazos": ToolPolicy(Risk.READ, "Consulta de processos e prazos."),
    "listar_produtos_servicos": ToolPolicy(Risk.READ, "Consulta do catalogo comercial."),
    "processar_arquivo": ToolPolicy(Risk.READ, "Processamento de arquivo em memoria."),
    "inspecionar_formulario_documento": ToolPolicy(
        Risk.READ, "Inspeciona campos de um documento local sem altera-lo."
    ),
    # ── Gera arquivo novo, nunca sobrescreve ───────────────────
    "gerar_grafico": ToolPolicy(
        Risk.DERIVED, "Gera um PNG novo na pasta de graficos; nao sobrescreve nada."
    ),
    "gerar_relatorio_local": ToolPolicy(
        Risk.DERIVED, "Gera um relatorio novo na pasta de relatorios; nao sobrescreve nada."
    ),
    "gerar_documento_local": ToolPolicy(
        Risk.DERIVED, "Gera um documento novo sem sobrescrever o arquivo de origem."
    ),
    # ── Escrita / cadastro ─────────────────────────────────────
    "adicionar_item_estoque": ToolPolicy(Risk.WRITE, "Cadastra um novo item de estoque."),
    "cadastrar_cliente": ToolPolicy(Risk.WRITE, "Cadastra cliente na base local."),
    "cadastrar_fornecedor": ToolPolicy(Risk.WRITE, "Cadastra fornecedor na base local."),
    "cadastrar_orcamento": ToolPolicy(Risk.WRITE, "Cadastra orcamento na base local."),
    "cadastrar_produto_servico": ToolPolicy(Risk.WRITE, "Cadastra produto ou servico."),
    "cadastrar_processo_prazo": ToolPolicy(Risk.WRITE, "Cadastra processo ou prazo."),
    "criar_compromisso_agenda": ToolPolicy(Risk.WRITE, "Cria compromisso na agenda."),
    "entrada_estoque": ToolPolicy(Risk.WRITE, "Entrada de estoque altera a quantidade persistida."),
    "excluir_arquivo": ToolPolicy(
        Risk.DESTRUCTIVE, "Exclusao de arquivo e irreversivel.", ("caminho",)
    ),
    "excluir_documento": ToolPolicy(Risk.DESTRUCTIVE, "Exclusao de documento e irreversivel."),
    "indexar_documento": ToolPolicy(Risk.WRITE, "Indexa documento na base RAG."),
    "marcar_lembrete_agenda": ToolPolicy(Risk.WRITE, "Marca lembrete como avisado."),
    "remover_documento": ToolPolicy(
        Risk.DESTRUCTIVE, "Remove documento indexado; remocao e destrutiva."
    ),
    "salvar_memoria": ToolPolicy(Risk.WRITE, "Persiste memoria do usuario."),
    "saida_estoque": ToolPolicy(Risk.WRITE, "Baixa de estoque altera a quantidade persistida."),
    # ── Escrita de arquivo ─────────────────────────────────────
    "criar_editar_arquivo": ToolPolicy(
        Risk.IRREVERSIBLE,
        "Cria ou sobrescreve arquivo no disco; sobrescrita nao e reversivel.",
        ("modo",),
    ),
    "preencher_documento": ToolPolicy(
        Risk.WRITE,
        "Cria uma copia preenchida com dados possivelmente pessoais; exige revisao e confirmacao.",
    ),
    "preencher_documento_com_fontes": ToolPolicy(
        Risk.WRITE,
        "Cria uma copia preenchida a partir de outros documentos, com dados pessoais; "
        "exige revisao e confirmacao antes de entregar o arquivo.",
    ),
    # ── Execucao de codigo ─────────────────────────────────────
    "executar_codigo": ToolPolicy(
        Risk.IRREVERSIBLE, "Executa codigo local; efeitos colaterais nao sao reversiveis."
    ),
    # ── Rede / externo ─────────────────────────────────────────
    "abrir_no_navegador": ToolPolicy(
        Risk.EXTERNAL, "Abre site externo e expoe a sessao do navegador."
    ),
    # Selecting Research mode or asking for current information is explicit
    # consent for read-only public HTTP requests. The network validator still
    # blocks credentials, private addresses and non-HTTP schemes.
    "navegar_web": ToolPolicy(Risk.READ, "Leitura de pagina publica validada."),
    "pesquisar_google": ToolPolicy(Risk.READ, "Pesquisa publica somente leitura."),
    "pesquisar_noticias": ToolPolicy(Risk.READ, "Consulta RSS publica somente leitura."),
    "pesquisar_web": ToolPolicy(Risk.READ, "Pesquisa publica somente leitura."),
    # Ferramentas de envio mensagens/financeiras: nunca existem hoje, mas a
    # politica precisa estar pronta caso sejam adicionadas.
    "enviar_mensagem": ToolPolicy(
        Risk.EXTERNAL, "Envia mensagem para fora do computador.", ("destinatario",)
    ),
    "enviar_notificacao": ToolPolicy(
        Risk.EXTERNAL, "Envia notificacao por canal externo.", ("destinatario",)
    ),
    "registrar_pagamento": ToolPolicy(
        Risk.IRREVERSIBLE, "Operacao financeira; nao pode ser desfeita."
    ),
}

#: Modes that mean "the argument list is destructive" for tools that are dual-use.
_ESCALATION_TOKENS: dict[str, tuple[str, ...]] = {
    # cÃ³digo local que apaga coisas continua sendo sensÃ­vel
    "executar_codigo": ("codigo",),
    "criar_editar_arquivo": ("caminho",),
}


@dataclass(frozen=True)
class ToolRiskAssessment:
    """Deterministic verdict for one tool call."""

    tool: str
    risk: Risk
    requires_confirmation: bool
    reason: str
    escalated_by: tuple[str, ...] = ()
    policy_known: bool = True

    @property
    def risk_label(self) -> str:
        return RISK_LABELS.get(self.risk, RISK_LABELS[Risk.UNKNOWN])


@dataclass
class ToolGuardDecision:
    """Final verdict: deterministic policy + (optional) probabilistic suggestion.

    ``source`` records which layer produced the *binding* decision so the audit
    log can tell a policy-mandated confirmation from a Jev suggestion:

    * ``"policy"`` — the deterministic table (or the SENSITIVE_TOOLS allowlist)
      demanded the confirmation;
    * ``"jev"`` — the decision model raised the risk on top of the policy;
    * ``"fallback"`` — the decision layer was unavailable; only policy applied.
    """

    tool: str
    requires_confirmation: bool
    risk: Risk
    reason: str
    source: str
    probability: float = 0.0
    args_summary: str = ""
    assessment: ToolRiskAssessment | None = None
    policy_requires_confirmation: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "requires_confirmation": self.requires_confirmation,
            "risk": self.risk.value,
            "risk_label": self.risk_label,
            "reason": self.reason,
            "source": self.source,
            "probability": round(self.probability, 4),
            "args_summary": self.args_summary,
            "policy_requires_confirmation": self.policy_requires_confirmation,
        }

    @property
    def risk_label(self) -> str:
        return RISK_LABELS.get(self.risk, RISK_LABELS[Risk.UNKNOWN])


def summarize_arguments(arguments: Mapping[str, Any] | None) -> str:
    """Short, log-safe preview of tool arguments."""
    if not arguments:
        return "{}"
    try:
        rendered = json.dumps(dict(arguments), ensure_ascii=False, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        rendered = ", ".join(sorted(map(str, arguments)))
    if len(rendered) > ARGS_PREVIEW_LIMIT:
        return f"{rendered[:ARGS_PREVIEW_LIMIT]}..."
    return rendered


def get_policy(tool: str) -> ToolPolicy | None:
    return _POLICIES.get(tool)


def _escalation_tokens(tool: str) -> tuple[str, ...]:
    return _ESCALATION_TOKENS.get(tool, ())


def assess_tool(tool: str, arguments: Mapping[str, Any] | None = None) -> ToolRiskAssessment:
    """Evaluate one tool call against the deterministic policy.

    Never raises: an unexpected failure returns the fail-closed UNKNOWN verdict.
    """
    args = dict(arguments or {})
    if tool == "preencher_documento_com_fontes" and args.get("somente_analisar") is True:
        return ToolRiskAssessment(
            tool=tool, risk=Risk.READ, requires_confirmation=False,
            reason="Planeja preenchimento com fontes sem criar ou alterar arquivos.",
        )
    policy = get_policy(tool)
    if policy is None:
        return ToolRiskAssessment(
            tool=tool,
            risk=Risk.UNKNOWN,
            requires_confirmation=True,
            reason="Ferramenta sem politica definida (falha fechada).",
            policy_known=False,
        )

    risk = policy.risk
    escalated_by: tuple[str, ...] = ()
    # Dual-use tools: the declared risk escalates when the call carries the
    # arguments that make it irreversible.
    tokens = _escalation_tokens(tool) or policy.escalating_arguments
    present = tuple(name for name in tokens if args.get(name))
    if present and risk in {Risk.READ, Risk.DERIVED, Risk.WRITE}:
        risk = Risk.IRREVERSIBLE
        escalated_by = present
    # External send always escalates to "external" when it names a recipient.
    if risk is Risk.WRITE and args.get("destinatario"):
        risk = Risk.EXTERNAL
        escalated_by = present or ("destinatario",)

    requires = policy.resolve(args) or risk in CONFIRMING_RISKS
    # The pre-existing allowlist can only make things stricter, never looser.
    if tool in SENSITIVE_TOOLS:
        requires = True
    reason = policy.reason
    if escalated_by:
        reason = f"{reason} Escalado por argumento(s): {', '.join(escalated_by)}."
    return ToolRiskAssessment(
        tool=tool,
        risk=risk,
        requires_confirmation=requires,
        reason=reason,
        escalated_by=escalated_by,
    )


def allowed_tools_without_confirmation() -> frozenset[str]:
    """Tools the policy lets run straight away (read-only + derived files)."""
    return frozenset(name for name in _POLICIES if not assess_tool(name).requires_confirmation)


def is_read_only(tool: str) -> bool:
    return assess_tool(tool).risk in {Risk.READ, Risk.DERIVED}


@dataclass(frozen=True)
class ToolPolicyTable:
    """Serializable view of the policy, for the API/UI."""

    entries: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def as_list(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self.entries]


def policy_table(tools: Iterable[str] | None = None) -> ToolPolicyTable:
    """Return the (optionally filtered) policy table sorted by tool name."""
    names = sorted(tools) if tools is not None else sorted(_POLICIES)
    entries: list[dict[str, Any]] = []
    for name in names:
        assessment = assess_tool(name)
        entries.append(
            {
                "tool": name,
                "risk": assessment.risk.value,
                "risk_label": assessment.risk_label,
                "requires_confirmation": assessment.requires_confirmation,
                "reason": assessment.reason,
                "known": assessment.policy_known,
            }
        )
    return ToolPolicyTable(entries=tuple(entries))
