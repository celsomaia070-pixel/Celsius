from dataclasses import dataclass, field
from typing import Any, Literal
from unicodedata import category, normalize

ModuleStatus = Literal["ready", "preparing"]

MODULE_CHAT = "chat"
MODULE_KNOWLEDGE = "knowledge"
MODULE_CUSTOMERS = "customers"
MODULE_SUPPLIERS = "suppliers"
MODULE_INVENTORY = "inventory"
MODULE_PRODUCTS_SERVICES = "products_services"
MODULE_QUOTES = "quotes"
MODULE_FINANCE = "finance"
MODULE_REPORTS = "reports"
MODULE_AGENDA = "agenda"
MODULE_CASES_DEADLINES = "cases_deadlines"
MODULE_SETTINGS = "settings"

MANDATORY_MODULE_IDS = (MODULE_CHAT, MODULE_SETTINGS)


@dataclass(frozen=True)
class ModuleDefinition:
    id: str
    name: str
    icon: str
    description: str
    default_active: bool = False
    mandatory: bool = False
    show_in_sidebar: bool = True
    status: ModuleStatus = "preparing"
    route: str = ""
    sensitive_domains: tuple[str, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"


MODULE_CATALOG: tuple[ModuleDefinition, ...] = (
    ModuleDefinition(
        id=MODULE_CHAT,
        name="Chat",
        icon="brain",
        description="Assistente local para conversa, arquivos e raciocinio geral.",
        default_active=True,
        mandatory=True,
        status="ready",
        route="chat",
    ),
    ModuleDefinition(
        id=MODULE_KNOWLEDGE,
        name="Documentos",
        icon="database",
        description="Base de conhecimento, documentos indexados e busca local.",
        default_active=True,
        status="ready",
        route="knowledge",
    ),
    ModuleDefinition(
        id=MODULE_CUSTOMERS,
        name="Clientes",
        icon="list",
        description="Cadastro e historico de clientes.",
        status="ready",
        route="customers",
        sensitive_domains=("health", "legal"),
    ),
    ModuleDefinition(
        id=MODULE_SUPPLIERS,
        name="Fornecedores",
        icon="cube",
        description="Cadastro local de fornecedores e contatos de compra.",
        default_active=True,
        status="ready",
        route="suppliers",
    ),
    ModuleDefinition(
        id=MODULE_INVENTORY,
        name="Estoque",
        icon="cube",
        description="Controle de itens, entradas, saidas e reposicao.",
        default_active=True,
        status="ready",
        route="inventory",
    ),
    ModuleDefinition(
        id=MODULE_PRODUCTS_SERVICES,
        name="Produtos e servicos",
        icon="list",
        description="Catalogo comercial da empresa.",
        status="ready",
        route="products_services",
    ),
    ModuleDefinition(
        id=MODULE_QUOTES,
        name="Orcamentos",
        icon="file-alt",
        description="Preparacao de propostas, orcamentos e pedidos.",
        status="ready",
        route="quotes",
    ),
    ModuleDefinition(
        id=MODULE_FINANCE,
        name="Financeiro",
        icon="database",
        description="Base para contas, recebimentos, pagamentos e indicadores.",
        status="ready",
        route="finance",
        sensitive_domains=("finance",),
    ),
    ModuleDefinition(
        id=MODULE_REPORTS,
        name="Relatorios",
        icon="print",
        description="Relatorios em PDF/DOCX e resumos operacionais.",
        default_active=True,
        status="ready",
        route="reports",
    ),
    ModuleDefinition(
        id=MODULE_AGENDA,
        name="Agenda",
        icon="list",
        description="Compromissos, atendimentos, visitas e lembretes.",
        status="ready",
        route="agenda",
        sensitive_domains=("health", "legal"),
    ),
    ModuleDefinition(
        id=MODULE_CASES_DEADLINES,
        name="Processos e prazos",
        icon="file-alt",
        description="Base para prazos, processos e acompanhamentos sensiveis.",
        status="ready",
        route="cases_deadlines",
        sensitive_domains=("legal",),
    ),
    ModuleDefinition(
        id=MODULE_SETTINGS,
        name="Configuracoes",
        icon="cog",
        description="Perfil da empresa, privacidade, modelo, voz e modulos.",
        default_active=True,
        mandatory=True,
        status="ready",
        route="settings",
    ),
)

_CATALOG_BY_ID = {module.id: module for module in MODULE_CATALOG}


SEGMENT_MODULE_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "oficina": (
        MODULE_INVENTORY,
        MODULE_SUPPLIERS,
        MODULE_CUSTOMERS,
        MODULE_KNOWLEDGE,
        MODULE_QUOTES,
        MODULE_REPORTS,
    ),
    "autopecas": (
        MODULE_INVENTORY,
        MODULE_SUPPLIERS,
        MODULE_CUSTOMERS,
        MODULE_PRODUCTS_SERVICES,
        MODULE_FINANCE,
        MODULE_REPORTS,
    ),
    "manutencao": (
        MODULE_INVENTORY,
        MODULE_SUPPLIERS,
        MODULE_CUSTOMERS,
        MODULE_KNOWLEDGE,
        MODULE_QUOTES,
        MODULE_REPORTS,
    ),
    "comercio": (
        MODULE_INVENTORY,
        MODULE_SUPPLIERS,
        MODULE_PRODUCTS_SERVICES,
        MODULE_CUSTOMERS,
        MODULE_FINANCE,
        MODULE_REPORTS,
    ),
    "padaria": (
        MODULE_INVENTORY,
        MODULE_SUPPLIERS,
        MODULE_PRODUCTS_SERVICES,
        MODULE_CUSTOMERS,
        MODULE_FINANCE,
        MODULE_REPORTS,
    ),
    "advocacia": (
        MODULE_CUSTOMERS,
        MODULE_KNOWLEDGE,
        MODULE_CASES_DEADLINES,
        MODULE_AGENDA,
        MODULE_REPORTS,
    ),
    "dentista": (
        MODULE_CUSTOMERS,
        MODULE_AGENDA,
        MODULE_KNOWLEDGE,
        MODULE_FINANCE,
        MODULE_REPORTS,
    ),
    "clinica": (
        MODULE_CUSTOMERS,
        MODULE_AGENDA,
        MODULE_KNOWLEDGE,
        MODULE_FINANCE,
        MODULE_REPORTS,
    ),
    "consultorio": (
        MODULE_CUSTOMERS,
        MODULE_AGENDA,
        MODULE_KNOWLEDGE,
        MODULE_FINANCE,
        MODULE_REPORTS,
    ),
    "servicos": (
        MODULE_CUSTOMERS,
        MODULE_KNOWLEDGE,
        MODULE_QUOTES,
        MODULE_AGENDA,
        MODULE_FINANCE,
        MODULE_REPORTS,
    ),
}


NEED_MODULE_KEYWORDS: dict[str, tuple[str, ...]] = {
    MODULE_INVENTORY: ("estoque", "reposicao", "pecas", "insumos", "mercadorias"),
    MODULE_SUPPLIERS: ("fornecedor", "compra", "compras"),
    MODULE_CUSTOMERS: ("cliente", "paciente", "atendimento"),
    MODULE_KNOWLEDGE: ("documento", "base", "contrato", "arquivo", "conhecimento"),
    MODULE_QUOTES: ("orcamento", "proposta", "pedido"),
    MODULE_FINANCE: ("financeiro", "contas", "pagamento", "recebimento", "caixa"),
    MODULE_REPORTS: ("relatorio", "indicador", "resumo"),
    MODULE_AGENDA: ("agenda", "consulta", "prazo", "visita", "horario"),
    MODULE_CASES_DEADLINES: ("processo", "prazo", "juridico", "audiencia"),
    MODULE_PRODUCTS_SERVICES: ("produto", "servico", "catalogo"),
}

SENSITIVE_SEGMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "legal": ("advocacia", "advogado", "juridico", "processo"),
    "health": ("dentista", "clinica", "consultorio", "saude", "medico", "paciente"),
}


def module_catalog() -> tuple[ModuleDefinition, ...]:
    return MODULE_CATALOG


def get_module_definition(module_id: str) -> ModuleDefinition | None:
    return _CATALOG_BY_ID.get(module_id)


def default_enabled_module_ids() -> list[str]:
    return normalize_module_ids(module.id for module in MODULE_CATALOG if module.default_active)


def normalize_module_ids(module_ids) -> list[str]:
    known = []
    seen = set()
    for module_id in module_ids or ():
        if module_id in _CATALOG_BY_ID and module_id not in seen:
            known.append(module_id)
            seen.add(module_id)
    for module in MODULE_CATALOG:
        if module.mandatory and module.id not in seen:
            known.append(module.id)
            seen.add(module.id)
    return known


def sidebar_modules(module_ids) -> list[ModuleDefinition]:
    enabled = set(normalize_module_ids(module_ids))
    return [
        module
        for module in MODULE_CATALOG
        if module.id in enabled and module.show_in_sidebar and module.is_ready
    ]


def suggest_modules_for_company(
    segment: str = "", needs: list[str] | str | None = None
) -> list[str]:
    normalized_segment = _normalize_text(segment)
    suggested: list[str] = list(MANDATORY_MODULE_IDS)

    for keyword, module_ids in SEGMENT_MODULE_SUGGESTIONS.items():
        if keyword in normalized_segment:
            suggested.extend(module_ids)
            break

    needs_text = _normalize_text(" ".join(needs) if isinstance(needs, list) else needs or "")
    for module_id, keywords in NEED_MODULE_KEYWORDS.items():
        if any(keyword in needs_text for keyword in keywords):
            suggested.append(module_id)

    if not normalized_segment and not needs_text:
        suggested.extend(default_enabled_module_ids())

    return normalize_module_ids(suggested)


def privacy_domains_for_segment(segment: str = "") -> list[str]:
    normalized_segment = _normalize_text(segment)
    return [
        domain
        for domain, keywords in SENSITIVE_SEGMENT_KEYWORDS.items()
        if any(keyword in normalized_segment for keyword in keywords)
    ]


def _normalize_text(value: str) -> str:
    decomposed = normalize("NFD", (value or "").strip().lower())
    return "".join(char for char in decomposed if category(char) != "Mn")
