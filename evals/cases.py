"""Golden set: prompts with the tool and mode each one *should* reach.

This is a labelled dataset, not a test file. Each case states the capability
required, and the harness in ``harness.py`` measures what the system actually
offers. That separation is the whole point: a regression is a *number moving*,
not a test flipping.

Categories follow the specification:

* ``A`` tool selection, including deliberate paraphrases;
* ``B`` mode routing;
* ``C`` multi-step, where no single tool is sufficient;
* ``D`` error recovery, where the first call is expected to fail;
* ``E`` natural language / paraphrase, the sharpest test of semantic retrieval;
* ``F`` requests that must reach the model with **no** tool;
* ``G`` context, where the answer depends on earlier turns;
* ``H`` loop, where a tool keeps returning the same error.

The ``expect_tools`` labels are *capabilities*, and a hit only counts when the
offered tool is in ``required_tools`` — the tools that genuinely satisfy the
request. A case may list several, because "encontre o documento X" is satisfied
by any tool that can retrieve documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Capability labels ───────────────────────────────────────────
# Grouped so a metric can also be reported per capability, which is more
# actionable than one flat recall number.
DOCS = "docs"
FILES = "files"
STOCK = "stock"
WEB = "web"
CODE = "code"
MEMORY = "memory"
BUSINESS = "business"
AGENDA = "agenda"
CHART = "chart"
REPORT = "report"
NONE = "none"


@dataclass(frozen=True)
class Case:
    """One labelled prompt.

    ``required_tools`` are the tools that genuinely satisfy the request. A tool
    from this set being offered counts as a hit; anything else is a false
    positive for precision.

    ``expect_mode`` is the mode the router should land on, or ``None`` when the
    prompt has no strong mode signal and any mode is acceptable.
    """

    id: str
    prompt: str
    category: str
    capability: str = NONE
    required_tools: frozenset[str] = field(default_factory=frozenset)
    expect_mode: str | None = None
    #: Prompts that must not trigger a tool at all.
    expect_no_tool: bool = False
    #: For ``C``: the capabilities a complete solution has to touch.
    expected_steps: tuple[str, ...] = ()
    note: str = ""


def _c(
    id: str,
    prompt: str,
    category: str,
    *,
    capability: str = NONE,
    tools: tuple[str, ...] = (),
    mode: str | None = None,
    no_tool: bool = False,
    steps: tuple[str, ...] = (),
    note: str = "",
) -> Case:
    return Case(
        id=id,
        prompt=prompt,
        category=category,
        capability=capability,
        required_tools=frozenset(tools),
        expect_mode=mode,
        expect_no_tool=no_tool,
        expected_steps=steps,
        note=note,
    )


CASES: tuple[Case, ...] = (
    # ── A. Tool selection: the same capability, different words ──
    _c("A01", "quais documentos eu tenho?", "A", capability=DOCS,
       tools=("listar_documentos_rag",)),
    _c("A02", "liste meus documentos", "A", capability=DOCS,
       tools=("listar_documentos_rag",), mode="documentos"),
    _c("A03", "tem algum relatório salvo?", "A", capability=DOCS,
       tools=("listar_documentos_rag", "listar_arquivos")),
    _c("A04", "procure os arquivos relacionados a estoque", "A", capability=FILES,
       tools=("listar_arquivos", "buscar_item_estoque", "ler_arquivo")),
    _c("A05", "o que já está armazenado aqui?", "A", capability=FILES,
       tools=("listar_arquivos", "listar_documentos_rag")),
    _c("A06", "liste os documentos disponíveis", "A", capability=DOCS,
       tools=("listar_documentos_rag",)),
    _c("A07", "quantos itens de parafuso tem no estoque?", "A", capability=STOCK,
       tools=("buscar_item_estoque", "listar_estoque")),
    _c("A08", "quais produtos estão com estoque baixo?", "A", capability=STOCK,
       tools=("itens_estoque_baixo",)),
    _c("A09", "quais clientes estão cadastrados?", "A", capability=BUSINESS,
       tools=("listar_clientes",)),
    _c("A10", "liste os orçamentos abertos", "A", capability=BUSINESS,
       tools=("listar_orcamentos",)),
    _c("A11", "quais compromissos tenho esta semana?", "A", capability=AGENDA,
       tools=("listar_agenda",)),
    _c("A12", "quais processos têm prazo vencendo?", "A", capability=BUSINESS,
       tools=("listar_processos_prazos",)),
    _c("A13", "gere um gráfico de vendas", "A", capability=CHART,
       tools=("gerar_grafico",)),
    _c("A14", "gere um relatório PDF do estoque", "A", capability=REPORT,
       tools=("gerar_relatorio_local",)),
    _c("A15", "crie um arquivo chamado notas.txt", "A", capability=FILES,
       tools=("criar_editar_arquivo",)),
    _c("A16", "execute este script python e me diga o resultado", "A", capability=CODE,
       tools=("executar_codigo",)),
    _c("A17", "quais fornecedores estão cadastrados?", "A", capability=BUSINESS,
       tools=("listar_fornecedores",)),
    _c("A18", "liste o catálogo de produtos e serviços", "A", capability=BUSINESS,
       tools=("listar_produtos_servicos",)),
    _c("A19", "registre a entrada de 10 unidades de parafuso", "A", capability=STOCK,
       tools=("entrada_estoque",)),
    _c("A20", "quais são as últimas movimentações do estoque?", "A", capability=STOCK,
       tools=("historico_movimentacoes",)),
    _c("A21", "liste as pastas do diretório de trabalho", "A", capability=FILES,
       tools=("listar_arquivos",)),
    _c("A22", "quais informações o sistema tem sobre esta máquina?", "A",
       capability="system", tools=("informacoes_sistema",)),
    _c("A23", "abra esse site no navegador", "A", capability=WEB,
       tools=("abrir_no_navegador", "navegar_web")),
    _c("A24", "indexe o contrato para busca", "A", capability=DOCS,
       tools=("indexar_documento",)),
    _c("A25", "remova o documento antigo do índice", "A", capability=DOCS,
       tools=("remover_documento",)),
    _c("A26", "crie um cliente novo chamado Maria", "A", capability=BUSINESS,
       tools=("cadastrar_cliente",)),
    _c("A27", "agende uma reunião amanhã às 14h", "A", capability=AGENDA,
       tools=("criar_compromisso_agenda",)),
    _c("A28", "o que você lembra sobre o cliente Ana?", "A", capability=MEMORY,
       tools=("buscar_memoria",)),
    _c("A29", "lembre que a Ana prefere pagamento à vista", "A", capability=MEMORY,
       tools=("salvar_memoria",)),
    _c("A30", "liste os fornecedores", "A", capability=BUSINESS,
       tools=("listar_fornecedores",)),
    _c("A31", "qual o catálogo de serviços?", "A", capability=BUSINESS,
       tools=("listar_produtos_servicos",)),
    _c("A32", "quais itens estão no estoque?", "A", capability=STOCK,
       tools=("listar_estoque",)),
    _c("A33", "mostre os produtos da loja", "A", capability=BUSINESS,
       tools=("listar_produtos_servicos", "listar_estoque")),
    _c("A34", "abrir o arquivo contrato.pdf", "A", capability=FILES,
       tools=("ler_arquivo", "processar_arquivo", "inspecionar_formulario_documento")),
    _c("A35", "quais campos tem o formulário da ficha de emprego?", "A",
       capability=DOCS, tools=("inspecionar_formulario_documento",)),

    # ── B. Mode routing ──
    _c("B01", "pesquise na internet as últimas notícias sobre lítio", "B",
       capability=WEB, tools=("pesquisar_web", "pesquisar_noticias"), mode="pesquisador"),
    _c("B02", "descubra informações atuais sobre o mercado de energia solar", "B",
       capability=WEB, tools=("pesquisar_web", "navegar_web", "pesquisar_noticias"),
       mode="pesquisador", note="sem a palavra 'pesquise'"),
    _c("B03", "escreva uma função python que inverte uma string", "B",
       capability=CODE, tools=("executar_codigo", "criar_editar_arquivo"), mode="desenvolvedor"),
    _c("B04", "me ajude a refatorar este código", "B", capability=CODE,
       tools=("executar_codigo", "ler_arquivo"), mode="desenvolvedor"),
    _c("B05", "modo estoque", "B", capability=STOCK, tools=("listar_estoque",),
       mode="estoque", note="comando explícito"),
    _c("B06", "modo pesquisador", "B", capability=WEB, tools=("pesquisar_web",),
       mode="pesquisador", note="comando explícito"),
    _c("B07", "quero preencher um formulário em PDF", "B", capability=DOCS,
       tools=("preencher_documento", "inspecionar_formulario_documento"), mode="documentos"),
    _c("B08", "qual o dia da semana?", "B", capability="none", no_tool=True,
       mode="assistente"),
    _c("B09", "trocar modo estoque", "B", capability=STOCK, tools=("listar_estoque",),
       mode="estoque", note="comando explícito"),
    _c("B10", "quero saber o histórico de movimentações do armazém", "B",
       capability=STOCK, tools=("historico_movimentacoes",), mode="estoque"),

    # ── C. Multi-step: no single tool is enough ──
    _c("C01",
       "encontre o documento contrato, leia, faça um resumo e salve como resumo_contrato",
       "C", capability=DOCS,
       tools=("listar_documentos_rag", "ler_arquivo", "processar_arquivo",
              "criar_editar_arquivo", "gerar_documento_local"),
       mode="documentos",
       steps=("locate", "read", "summarize", "write")),
    _c("C02",
       "Leia o relatório X, faça um resumo e salve em outro arquivo",
       "C", capability=DOCS,
       tools=("listar_documentos_rag", "ler_arquivo", "processar_arquivo",
              "criar_editar_arquivo", "gerar_documento_local"),
       mode="documentos",
       steps=("locate", "read", "summarize", "write")),
    _c("C03",
       "pegue os dados de estoque, gere um gráfico e salve o gráfico como PNG",
       "C", capability=STOCK,
       tools=("listar_estoque", "gerar_grafico", "criar_editar_arquivo"),
       mode="estoque",
       steps=("read", "chart", "write")),
    _c("C04",
       "consulte os clientes, gere um relatório PDF e salve o arquivo",
       "C", capability=BUSINESS,
       tools=("listar_clientes", "gerar_relatorio_local", "criar_editar_arquivo"),
       mode="executor",
       steps=("read", "report", "write")),

    # ── D. Error recovery: the first attempt is expected to fail ──
    _c("D01", "leia o arquivo nao_existe_12345.txt", "D", capability=FILES,
       tools=("ler_arquivo", "listar_arquivos"),
       note="arquivo inexistente: deve procurar em vez de desistir"),
    _c("D02", "gere o relatório do arquivo que você não sabe qual é", "D",
       capability=FILES,
       tools=("listar_arquivos", "listar_documentos_rag", "gerar_relatorio_local"),
       note="deve descobrir o arquivo antes de gerar"),
    _c("D03", "consulte o estoque de um produto que não existe", "D", capability=STOCK,
       tools=("buscar_item_estoque", "listar_estoque"),
       note="produto inexistente: deve listar ou reformular"),
    _c("D04", "preencha o formulário em /caminho/inexistente/formulario.pdf", "D",
       capability=DOCS,
       tools=("inspecionar_formulario_documento", "preencher_documento", "listar_arquivos"),
       note="caminho inválido: deve recuperar"),
    _c("D05", "pesquise na internet e se falhar tente novamente", "D", capability=WEB,
       tools=("pesquisar_web", "navegar_web", "pesquisar_noticias", "pesquisar_google"),
       note="falha transitória: retry é justificável"),

    # ── E. Paraphrase: deliberately avoids registered keywords ──
    # These are the cases that separate lexical from semantic retrieval. If
    # every one of them passes on keywords alone, the semantic layer is not
    # being exercised and the metric is measuring the wrong thing.
    _c("E01", "o que já está armazenado aqui?", "E", capability=FILES,
       tools=("listar_arquivos", "listar_documentos_rag"),
       note="paráfrase: 'armazenado' não é keyword"),
    _c("E02", "me mostra o que tem guardado no sistema", "E", capability=FILES,
       tools=("listar_arquivos", "listar_documentos_rag"),
       note="paráfrase: 'guardado' não é keyword"),
    _c("E03", "tem alguma coisa arquivada que eu possa ver?", "E", capability=DOCS,
       tools=("listar_documentos_rag",),
       note="paráfrase: 'arquivada' não é keyword"),
    _c("E04", "quais peças de reposição estão disponíveis?", "E", capability=STOCK,
       tools=("buscar_item_estoque", "listar_estoque"),
       note="paráfrase: 'disponíveis' não é keyword de estoque"),
    _c("E05", "pode me passar o que foi cotado este mês?", "E", capability=BUSINESS,
       tools=("listar_orcamentos",),
       note="paráfrase: 'cotado' não é keyword"),
    _c("E06", "quando é o meu próximo compromisso?", "E", capability=AGENDA,
       tools=("listar_agenda",),
       note="paráfrase: 'próximo' não é keyword"),
    _c("E07", "me ajuda a montar um código que resolva X", "E", capability=CODE,
       tools=("executar_codigo", "criar_editar_arquivo"),
       note="paráfrase: 'montar' não é keyword de código"),
    _c("E08", "quero ver o panorama das vendas", "E", capability=CHART,
       tools=("gerar_grafico", "listar_estoque", "gerar_relatorio_local"),
       note="paráfrase: 'panorama' não é keyword"),
    _c("E09", "o que você sabe sobre o que já conversamos?", "E", capability=MEMORY,
       tools=("buscar_memoria",),
       note="paráfrase: 'já conversamos' não é keyword"),
    _c("E10", "preciso do material guardado no computador", "E", capability=FILES,
       tools=("listar_arquivos",),
       note="paráfrase: 'guardado' não é keyword"),

    # ── F. Must not call a tool ──
    _c("F01", "o que é computação quântica?", "F", capability=NONE, no_tool=True),
    _c("F02", "explique o que é aprendizado de máquina", "F", capability=NONE, no_tool=True),
    _c("F03", "Explique energia solar", "F", capability=NONE, no_tool=True),
    _c("F04", "qual a diferença entre lista e tupla em Python?", "F", capability=NONE,
       no_tool=True, note="conhecimento geral, não tarefa local"),
    _c("F05", "me explique a teoria da relatividade", "F", capability=NONE, no_tool=True),
    _c("F06", "como funciona a fotosíntese?", "F", capability=NONE, no_tool=True),
    _c("F07", "obrigado, muito útil!", "F", capability=NONE, no_tool=True),
    _c("F08", "bom dia", "F", capability=NONE, no_tool=True, note="greeting"),
    _c("F09", "o que você sabe sobre oeuvres de arte?", "F", capability=NONE, no_tool=True),
    _c("F10", "resuma o conceito de entropia", "F", capability=NONE, no_tool=True),

    # ── G. Context: the answer depends on an earlier turn ──
    _c("G01", "e o preço dele?", "G", capability="context",
       tools=("buscar_item_estoque", "listar_estoque"),
       note="depende do turno anterior: 'dele'"),
    _c("G02", "cadastre esse também", "G", capability="context",
       tools=("cadastrar_cliente", "cadastrar_produto_servico", "cadastrar_fornecedor"),
       note="depende do turno anterior: 'esse'"),
    _c("G03", "salve isso no mesmo lugar", "G", capability="context",
       tools=("criar_editar_arquivo", "gerar_relatorio_local"),
       note="depende do turno anterior: 'mesmo lugar'"),
    _c("G04", "agende para o próximo dia útil", "G", capability="context",
       tools=("criar_compromisso_agenda", "listar_agenda"),
       note="depende do turno anterior: 'próximo dia útil'"),
    _c("G05", "agora gere o relatório", "G", capability="context",
       tools=("gerar_relatorio_local",),
       note="depende do turno anterior: 'agora'"),

# ── H. Loop: the same error keeps coming back ──
    _c("H01", "tente ler esse arquivo até conseguir", "H", capability=FILES,
       tools=("ler_arquivo", "listar_arquivos"),
       note="loop: repetir a mesma chamada não resolve"),
    _c("H02", "insista no mesmo formulário até preencher", "H", capability=DOCS,
       tools=("inspecionar_formulario_documento", "preencher_documento",
             "listar_arquivos"),
       note="loop: deve mudar de estratégia, não repetir"),
    _c("H03", "continue tentando o mesmo caminho", "H", capability=FILES,
       tools=("ler_arquivo", "listar_arquivos", "informacoes_sistema"),
       note="loop: caminho inválido repetido"),
    _c("H04", "preencha o campo obrigatório até aceitar", "H", capability=DOCS,
       tools=("preencher_documento", "inspecionar_formulario_documento"),
       note="loop: validação rejeita repetidamente"),
    _c("H05", "tente consultar o webhook que sempre falha", "H", capability=WEB,
       tools=("pesquisar_web", "navegar_web"),
       note="loop: serviço indisponível"),
    _c("H06", "gere o gráfico com dados que não existem", "H", capability=CHART,
       tools=("gerar_grafico", "listar_estoque"),
       note="loop: dados insuficientes"),

    # ── Additional A: more tool selection cases ──
    _c("A36", "quantos parafusos temos?", "A", capability=STOCK,
       tools=("buscar_item_estoque", "listar_estoque")),
    _c("A37", "verifique a disponibilidade do produto ABC", "A", capability=STOCK,
       tools=("buscar_item_estoque", "listar_estoque")),
    _c("A38", "mostre os clientes com nome João", "A", capability=BUSINESS,
       tools=("listar_clientes",)),
    _c("A39", "liste os orçamentos do mês passado", "A", capability=BUSINESS,
       tools=("listar_orcamentos",)),
    _c("A40", "quais fornecedores de parafusos?", "A", capability=BUSINESS,
       tools=("listar_fornecedores",)),
    _c("A41", "qual o saldo do item 123?", "A", capability=STOCK,
       tools=("buscar_item_estoque",)),
    _c("A42", "exportar lista de produtos para CSV", "A", capability=BUSINESS,
       tools=("listar_produtos_servicos", "gerar_relatorio_local")),
    _c("A43", "crie um lembrete para amanhã cedo", "A", capability=AGENDA,
       tools=("criar_compromisso_agenda",)),
    _c("A44", "qual a próxima reunião?", "A", capability=AGENDA,
       tools=("listar_agenda",)),
    _c("A45", "abra o YouTube no vídeo X", "A", capability=WEB,
       tools=("abrir_no_navegador",)),
    _c("A46", "pesquise no Google por Python", "A", capability=WEB,
       tools=("pesquisar_web", "navegar_web", "pesquisar_google")),
    _c("A47", "qual o IP desta máquina?", "A", capability="system",
       tools=("informacoes_sistema",)),
    _c("A48", "liste os processos em execução", "A", capability="system",
       tools=("informacoes_sistema",)),
    _c("A49", "salve que o cliente prefere email", "A", capability=MEMORY,
       tools=("salvar_memoria",)),
    _c("A50", "o que eu disse sobre o João?", "A", capability=MEMORY,
       tools=("buscar_memoria",)),

    # ── Additional C: more multi-step ──
    _c("C05",
       "busque o contrato do cliente X, extraia as cláusulas de pagamento e salve num arquivo",
       "C", capability=DOCS,
       tools=("listar_documentos_rag", "ler_arquivo", "processar_arquivo",
             "criar_editar_arquivo", "gerar_documento_local"),
       mode="documentos",
       steps=("locate", "read", "extract", "write")),
    _c("C06",
       "faça um inventário do estoque, crie um gráfico de itens baixos e gere relatório",
       "C", capability=STOCK,
       tools=("listar_estoque", "itens_estoque_baixo", "gerar_grafico", "gerar_relatorio_local"),
       mode="executor",
       steps=("read", "filter", "chart", "report")),
    _c("C07",
       "pesquise tendências de mercado, resuma e salve como relatório",
       "C", capability=WEB,
       tools=("pesquisar_web", "pesquisar_noticias", "processar_arquivo",
             "criar_editar_arquivo", "gerar_documento_local"),
       mode="pesquisador",
       steps=("search", "read", "summarize", "write")),
    _c("C08",
       "leia o log de erros, identifique o padrão e crie um ticket",
       "C", capability=CODE,
       tools=("ler_arquivo", "processar_arquivo", "criar_editar_arquivo"),
       mode="desenvolvedor",
       steps=("read", "analyze", "write")),

    # ── Additional D: more error recovery ──
    _c("D06", "tente acessar o banco de dados que está offline", "D", capability=CODE,
       tools=("executar_codigo", "informacoes_sistema"),
       note="falha de conexão: deve reportar indisponibilidade"),
    _c("D07", "preencha o formulário com campo obrigatório vazio", "D", capability=DOCS,
       tools=("preencher_documento", "inspecionar_formulario_documento"),
       note="validação falha: deve informar campo faltante"),
    _c("D08", "gere relatório com filtro que não retorna nada", "D", capability=REPORT,
       tools=("gerar_relatorio_local", "listar_estoque"),
       note="resultado vazio: deve informar, não falhar silenciosamente"),

    # ── Additional E: more paraphrases ──
    _c("E11", "cadastre isso aí pra mim", "E", capability=BUSINESS,
       tools=("cadastrar_cliente", "cadastrar_produto_servico"),
       note="paráfrase: 'cadastre isso'"),
    _c("E12", "joga pro sistema o orçamento novo", "E", capability=BUSINESS,
       tools=("cadastrar_orcamento",),
       note="paráfrase: 'joga pro sistema'"),
    _c("E13", "preciso ver o que tem pendente", "E", capability=AGENDA,
       tools=("listar_agenda", "listar_processos_prazos"),
       note="paráfrase: 'pendente'"),
    _c("E14", "me passa o resumo do que tá guardado", "E", capability=FILES,
       tools=("listar_arquivos", "listar_documentos_rag"),
       note="paráfrase: 'tá guardado', 'me passa'"),
    _c("E15", "bota um lembrete pra semana que vem", "E", capability=AGENDA,
       tools=("criar_compromisso_agenda",),
       note="paráfrase: 'bota um lembrete'"),

    # ── Additional G: more context-dependent ──
    _c("G06", "mande para ele também", "G", capability="context",
       tools=("criar_compromisso_agenda",),
       note="depende do turno anterior: 'ele'"),
    _c("G07", "faça o mesmo pro outro", "G", capability="context",
       tools=("cadastrar_cliente", "cadastrar_produto_servico"),
       note="depende do turno anterior: 'o outro'"),
    _c("G08", "agora faz o oposto", "G", capability="context",
       tools=("saida_estoque", "entrada_estoque"),
       note="depende do turno anterior: operação inversa"),
)


def by_category(category: str) -> tuple[Case, ...]:
    return tuple(c for c in CASES if c.category == category)


def case_by_id(case_id: str) -> Case:
    for c in CASES:
        if c.id == case_id:
            return c
    raise KeyError(case_id)
