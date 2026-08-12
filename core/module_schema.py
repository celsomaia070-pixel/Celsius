from dataclasses import dataclass
from typing import Literal

from core.modules import (
    MODULE_AGENDA,
    MODULE_CASES_DEADLINES,
    MODULE_CUSTOMERS,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_NOTIFICATIONS,
    MODULE_PRODUCTS_SERVICES,
    MODULE_QUOTES,
    MODULE_REPORTS,
    MODULE_SUPPLIERS,
)

FieldKind = Literal["text", "textarea", "date", "currency", "number", "select"]


@dataclass(frozen=True)
class ModuleField:
    key: str
    label: str
    kind: FieldKind = "text"
    required: bool = False
    placeholder: str = ""
    options: tuple[str, ...] = ()
    summary: bool = False


@dataclass(frozen=True)
class ModuleWorkflow:
    statuses: tuple[str, ...]
    default_status: str
    next_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModuleRecordSchema:
    module_id: str
    title: str
    subtitle: str
    primary_field: str
    fields: tuple[ModuleField, ...]
    workflow: ModuleWorkflow

    @property
    def summary_fields(self) -> tuple[ModuleField, ...]:
        return tuple(field for field in self.fields if field.summary)


MODULE_RECORD_SCHEMAS: dict[str, ModuleRecordSchema] = {
    MODULE_KNOWLEDGE: ModuleRecordSchema(
        module_id=MODULE_KNOWLEDGE,
        title="Documentos e base de conhecimento",
        subtitle="Controle documentos, origem, responsavel e situacao da base local.",
        primary_field="titulo",
        fields=(
            ModuleField("titulo", "Titulo", required=True, summary=True),
            ModuleField(
                "tipo",
                "Tipo",
                "select",
                options=("Contrato", "Manual", "Nota", "Laudo", "Outro"),
                summary=True,
            ),
            ModuleField("origem", "Origem"),
            ModuleField("categoria", "Categoria"),
            ModuleField("responsavel", "Responsavel"),
            ModuleField("validade", "Validade/Revisao", "date"),
            ModuleField(
                "status",
                "Status",
                "select",
                options=("Pendente", "Indexado", "Revisar", "Arquivado"),
                summary=True,
            ),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=("Pendente", "Indexado", "Revisar", "Arquivado"),
            default_status="Pendente",
            next_actions=("Anexar arquivo", "Indexar conteudo", "Revisar permissao"),
        ),
    ),
    MODULE_CUSTOMERS: ModuleRecordSchema(
        module_id=MODULE_CUSTOMERS,
        title="Clientes",
        subtitle="Cadastro de clientes, pacientes ou empresas atendidas, com status e responsavel.",
        primary_field="nome",
        fields=(
            ModuleField("nome", "Nome", required=True, summary=True),
            ModuleField(
                "tipo",
                "Tipo",
                "select",
                options=("Pessoa fisica", "Empresa", "Paciente", "Lead", "Outro"),
            ),
            ModuleField("documento", "CPF/CNPJ/Registro"),
            ModuleField("contato", "Contato"),
            ModuleField("telefone", "Telefone"),
            ModuleField("email", "E-mail"),
            ModuleField("endereco", "Endereco"),
            ModuleField("segmento", "Segmento/Perfil"),
            ModuleField("responsavel", "Responsavel interno"),
            ModuleField(
                "status",
                "Status",
                "select",
                options=("Lead", "Ativo", "Em atendimento", "Inativo"),
                summary=True,
            ),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=("Lead", "Ativo", "Em atendimento", "Inativo"),
            default_status="Ativo",
            next_actions=("Registrar contato", "Vincular documentos", "Criar orcamento"),
        ),
    ),
    MODULE_SUPPLIERS: ModuleRecordSchema(
        module_id=MODULE_SUPPLIERS,
        title="Fornecedores",
        subtitle="Cadastro de fornecedores com categoria, prazos, contato e itens fornecidos.",
        primary_field="nome",
        fields=(
            ModuleField("nome", "Nome", required=True, summary=True),
            ModuleField("categoria", "Categoria", summary=True),
            ModuleField("contato", "Contato"),
            ModuleField("telefone", "Telefone"),
            ModuleField("email", "E-mail"),
            ModuleField("documento", "CNPJ/Documento"),
            ModuleField("produtos", "Produtos fornecidos"),
            ModuleField("prazo_pagamento", "Prazo de pagamento"),
            ModuleField("lead_time_dias", "Prazo entrega (dias)", "number"),
            ModuleField(
                "status",
                "Status",
                "select",
                options=("Ativo", "Preferencial", "Cotacao", "Inativo"),
                summary=True,
            ),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=("Ativo", "Preferencial", "Cotacao", "Inativo"),
            default_status="Ativo",
            next_actions=("Cotacao", "Pedido de compra", "Atualizar tabela"),
        ),
    ),
    MODULE_PRODUCTS_SERVICES: ModuleRecordSchema(
        module_id=MODULE_PRODUCTS_SERVICES,
        title="Produtos e servicos",
        subtitle="Catalogo comercial com codigo, preco, custo, unidade e status.",
        primary_field="nome",
        fields=(
            ModuleField("codigo", "Codigo/SKU", summary=True),
            ModuleField("nome", "Nome", required=True, summary=True),
            ModuleField(
                "tipo", "Tipo", "select", options=("Produto", "Servico", "Pacote", "Assinatura")
            ),
            ModuleField("categoria", "Categoria"),
            ModuleField("unidade", "Unidade"),
            ModuleField("preco", "Preco de venda", "currency", summary=True),
            ModuleField("custo", "Custo"),
            ModuleField("fornecedor_padrao", "Fornecedor padrao"),
            ModuleField(
                "status",
                "Status",
                "select",
                options=("Ativo", "Pausado", "Sob encomenda", "Inativo"),
                summary=True,
            ),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=("Ativo", "Pausado", "Sob encomenda", "Inativo"),
            default_status="Ativo",
            next_actions=("Atualizar preco", "Gerar orcamento", "Revisar margem"),
        ),
    ),
    MODULE_QUOTES: ModuleRecordSchema(
        module_id=MODULE_QUOTES,
        title="Orcamentos",
        subtitle="Propostas comerciais com cliente, valor, validade, margem e etapa.",
        primary_field="titulo",
        fields=(
            ModuleField("numero", "Numero"),
            ModuleField("titulo", "Titulo", required=True, summary=True),
            ModuleField("cliente", "Cliente", summary=True),
            ModuleField("validade", "Validade", "date"),
            ModuleField("valor", "Valor total", "currency", summary=True),
            ModuleField("margem", "Margem estimada"),
            ModuleField("responsavel", "Responsavel"),
            ModuleField(
                "status",
                "Status",
                "select",
                options=("Rascunho", "Enviado", "Aprovado", "Recusado", "Expirado"),
                summary=True,
            ),
            ModuleField("itens", "Itens/servicos", "textarea"),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=("Rascunho", "Enviado", "Aprovado", "Recusado", "Expirado"),
            default_status="Rascunho",
            next_actions=("Enviar proposta", "Converter em pedido", "Registrar follow-up"),
        ),
    ),
    MODULE_FINANCE: ModuleRecordSchema(
        module_id=MODULE_FINANCE,
        title="Financeiro",
        subtitle="Lancamentos simples para contas a pagar, receber, caixa e centros de custo.",
        primary_field="descricao",
        fields=(
            ModuleField("descricao", "Descricao", required=True, summary=True),
            ModuleField("tipo", "Tipo", "select", options=("Receita", "Despesa", "Transferencia")),
            ModuleField("categoria", "Categoria"),
            ModuleField("valor", "Valor", "currency", summary=True),
            ModuleField("vencimento", "Vencimento", "date", summary=True),
            ModuleField("cliente_fornecedor", "Cliente/Fornecedor"),
            ModuleField("conta", "Conta/Caixa"),
            ModuleField("centro_custo", "Centro de custo"),
            ModuleField(
                "status",
                "Status",
                "select",
                options=("Aberto", "Pago", "Recebido", "Atrasado", "Cancelado"),
                summary=True,
            ),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=("Aberto", "Pago", "Recebido", "Atrasado", "Cancelado"),
            default_status="Aberto",
            next_actions=("Baixar lancamento", "Gerar relatorio", "Anexar comprovante"),
        ),
    ),
    MODULE_REPORTS: ModuleRecordSchema(
        module_id=MODULE_REPORTS,
        title="Relatorios",
        subtitle="Modelos e rotinas de relatorio por area, periodo, fonte de dados e indicador.",
        primary_field="titulo",
        fields=(
            ModuleField("titulo", "Relatorio", required=True, summary=True),
            ModuleField(
                "tipo",
                "Tipo",
                "select",
                options=("Operacional", "Financeiro", "Estoque", "Vendas", "Clientes", "Executivo"),
                summary=True,
            ),
            ModuleField("periodo", "Periodo"),
            ModuleField("fonte_dados", "Fonte de dados"),
            ModuleField("indicador", "Indicador principal"),
            ModuleField(
                "periodicidade",
                "Periodicidade",
                "select",
                options=("Diario", "Semanal", "Mensal", "Sob demanda"),
            ),
            ModuleField("responsavel", "Responsavel"),
            ModuleField(
                "status",
                "Status",
                "select",
                options=("Modelo", "Agendado", "Gerado", "Revisar"),
                summary=True,
            ),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=("Modelo", "Agendado", "Gerado", "Revisar"),
            default_status="Modelo",
            next_actions=("Gerar PDF", "Comparar periodo", "Enviar resumo"),
        ),
    ),
    MODULE_AGENDA: ModuleRecordSchema(
        module_id=MODULE_AGENDA,
        title="Agenda",
        subtitle="Compromissos, visitas, consultas e lembretes com responsavel e status.",
        primary_field="titulo",
        fields=(
            ModuleField("titulo", "Titulo", required=True, summary=True),
            ModuleField(
                "tipo",
                "Tipo",
                "select",
                options=("Consulta", "Reuniao", "Entrega", "Visita", "Prazo", "Outro"),
            ),
            ModuleField("data_hora", "Data/Hora", "date", summary=True),
            ModuleField("cliente", "Cliente/Paciente"),
            ModuleField("responsavel", "Responsavel", summary=True),
            ModuleField("local", "Local"),
            ModuleField("lembrete_minutos", "Lembrete antes (min)", "number"),
            ModuleField(
                "status",
                "Status",
                "select",
                options=("Agendado", "Confirmado", "Concluido", "Remarcar", "Cancelado"),
                summary=True,
            ),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=("Agendado", "Confirmado", "Concluido", "Remarcar", "Cancelado"),
            default_status="Agendado",
            next_actions=("Confirmar", "Reagendar", "Registrar resultado"),
        ),
    ),
    MODULE_CASES_DEADLINES: ModuleRecordSchema(
        module_id=MODULE_CASES_DEADLINES,
        title="Processos e prazos",
        subtitle="Controle de processos, prazos, prioridade, responsavel e proximo passo.",
        primary_field="processo",
        fields=(
            ModuleField("cliente", "Cliente", summary=True),
            ModuleField("processo", "Processo/Caso", required=True, summary=True),
            ModuleField("tipo", "Tipo"),
            ModuleField("prazo", "Prazo", "date", summary=True),
            ModuleField(
                "prioridade",
                "Prioridade",
                "select",
                options=("Baixa", "Normal", "Alta", "Critica"),
                summary=True,
            ),
            ModuleField("responsavel", "Responsavel"),
            ModuleField(
                "status",
                "Status",
                "select",
                options=("Novo", "Em andamento", "Aguardando terceiro", "Concluido", "Arquivado"),
                summary=True,
            ),
            ModuleField("proximo_passo", "Proximo passo"),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=("Novo", "Em andamento", "Aguardando terceiro", "Concluido", "Arquivado"),
            default_status="Novo",
            next_actions=("Criar alerta", "Anexar documento", "Atualizar andamento"),
        ),
    ),
    MODULE_NOTIFICATIONS: ModuleRecordSchema(
        module_id=MODULE_NOTIFICATIONS,
        title="Canais e notificacoes",
        subtitle=(
            "Prepare mensagens por WhatsApp, e-mail ou SMS. Envios reais dependem de internet "
            "e servico externo configurado."
        ),
        primary_field="titulo",
        fields=(
            ModuleField("titulo", "Titulo", required=True, summary=True),
            ModuleField(
                "canal",
                "Canal",
                "select",
                options=("WhatsApp", "E-mail", "SMS"),
                summary=True,
            ),
            ModuleField("destinatario", "Destinatario", required=True, summary=True),
            ModuleField(
                "origem",
                "Modulo origem",
                "select",
                options=(
                    "Manual",
                    "Agenda",
                    "Estoque",
                    "Orcamentos",
                    "Financeiro",
                    "Processos e prazos",
                    "Relatorios",
                ),
            ),
            ModuleField("template", "Template"),
            ModuleField("mensagem", "Mensagem", "textarea", required=True),
            ModuleField(
                "consentimento",
                "Consentimento",
                "select",
                options=("Confirmado", "Pendente", "Nao aplicavel"),
            ),
            ModuleField(
                "requer_internet",
                "Usa internet/servico externo",
                "select",
                options=("Sim", "Nao"),
            ),
            ModuleField(
                "status",
                "Status",
                "select",
                options=(
                    "Rascunho",
                    "Pronto",
                    "Pendente configuracao",
                    "Enviado manualmente",
                    "Falhou",
                ),
                summary=True,
            ),
            ModuleField("observacoes", "Observacoes", "textarea"),
        ),
        workflow=ModuleWorkflow(
            statuses=(
                "Rascunho",
                "Pronto",
                "Pendente configuracao",
                "Enviado manualmente",
                "Falhou",
            ),
            default_status="Rascunho",
            next_actions=("Revisar mensagem", "Confirmar consentimento", "Enviar pelo canal"),
        ),
    ),
}


def get_record_schema(module_id: str) -> ModuleRecordSchema | None:
    return MODULE_RECORD_SCHEMAS.get(module_id)


def module_fields(module_id: str) -> tuple[ModuleField, ...]:
    schema = get_record_schema(module_id)
    if schema:
        return schema.fields
    return (ModuleField("titulo", "Titulo", required=True, summary=True),)


def module_primary_field(module_id: str) -> str:
    schema = get_record_schema(module_id)
    return schema.primary_field if schema else "titulo"


def module_summary(record_fields: dict[str, str], module_id: str) -> str:
    schema = get_record_schema(module_id)
    fields = schema.summary_fields if schema else ()
    values = [record_fields.get(field.key, "").strip() for field in fields]
    values = [value for value in values if value]
    if values:
        return " | ".join(values[:3])
    return next((value for value in record_fields.values() if value), "Sem detalhes")
