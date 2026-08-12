import hashlib
import json
import logging
import os
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from core.circuit_breaker import (
    CircuitBreakerOpenError,
    get_circuit_breaker,
)
from core.metrics import MetricNames, get_metrics
from core.settings import get_settings
from core.tool_approval import SENSITIVE_TOOLS, approval_message, get_tool_approval_store

logger = logging.getLogger(__name__)


class Ferramenta:
    def __init__(self, nome, descricao, schema, funcao):
        self.nome = nome
        self.descricao = descricao
        self.schema = schema
        self.funcao = funcao

    def para_openai(self):
        return {
            "type": "function",
            "function": {
                "name": self.nome,
                "description": self.descricao,
                "parameters": self.schema,
            },
        }


def _allowed_file_roots() -> tuple[Path, ...]:
    settings = get_settings()
    configured_roots = settings.security.allowed_file_roots
    roots = [Path(root) for root in configured_roots] if configured_roots else [settings.base_dir]
    return tuple(root.expanduser().resolve() for root in roots)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_path(path: str) -> Path:
    """Validate path exists and stays inside an authorized file root."""
    raw_path = Path(path).expanduser()
    if not raw_path.is_absolute():
        raw_path = get_settings().base_dir / raw_path
    path = raw_path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {path}")
    allowed_roots = _allowed_file_roots()
    if not any(_is_relative_to(path, root) for root in allowed_roots):
        roots = ", ".join(str(root) for root in allowed_roots)
        raise PermissionError(f"Acesso negado: '{path}' esta fora das pastas autorizadas ({roots})")
    return path


def _tool_processar_arquivo(caminho: str) -> str:
    from processors import processar_arquivo

    path = _validate_path(caminho)
    return processar_arquivo(str(path), base_dir=path.parent)


def _tool_pesquisar_web(query: str) -> str:
    from core.commands import pesquisar_web

    return pesquisar_web(query)


def _tool_pesquisar_google(query: str) -> str:
    """Busca no Google usando o browser headless e extrai resultados."""
    from ai.browser import navegar_web

    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    resultado = navegar_web(url)

    # Extrai resultados da árvore de acessibilidade
    linhas = resultado.split("\n")
    resultados = []
    for linha in linhas:
        if (
            any(kw in linha.lower() for kw in ["link:", "heading:", "text:"])
            and len(linha.strip()) > 20
        ):
            resultados.append(linha.strip())

    if resultados:
        return "Resultados do Google:\n" + "\n".join(resultados[:10])
    return f"Busca realizada: {query}\n\n{resultado[:2000]}"


def _tool_pesquisar_noticias(query: str) -> str:
    """Busca notícias via RSS feeds de sites brasileiros (mais confiável que Google News)."""
    import feedparser

    # RSS feeds de notícias brasileiras (inclui feeds de tecnologia)
    feeds = {
        "G1": "https://g1.globo.com/rss/g1/",
        "G1 Tecnologia": "https://g1.globo.com/rss/g1/tecnologia/",
        "UOL": "https://rss.uol.com.br/feed/noticias.xml",
        "UOL Tecnologia": "https://rss.uol.com.br/feed/tecnologia.xml",
        "Folha": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml",
        "Folha Tec": "https://feeds.folha.uol.com.br/tec/rss091.xml",
        "Estadão": "https://www.estadao.com.br/rss/",
        "CNN Brasil": "https://www.cnnbrasil.com.br/feed/",
        "CNN Tech": "https://www.cnnbrasil.com.br/tecnologia/feed/",
        "BBC Brasil": "https://feeds.bbci.co.uk/portuguese/rss.xml",
    }

    query_lower = query.lower()
    palavras_query = [p for p in query_lower.split() if len(p) > 2]
    todas_noticias = []

    for fonte, url_feed in feeds.items():
        try:
            feed = feedparser.parse(url_feed)
            # Busca mais entradas por feed
            for entry in feed.entries[:20]:
                titulo = entry.get("title", "")
                resumo = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")

                # Filtro mais flexível
                if not palavras_query or any(
                    palavra in titulo.lower() or palavra in resumo.lower()
                    for palavra in palavras_query
                ):
                    todas_noticias.append(
                        {"fonte": fonte, "titulo": titulo, "resumo": resumo[:300], "link": link}
                    )
        except Exception:
            continue

    if not todas_noticias:
        return (
            f"Nenhuma notícia encontrada para '{query}'. Últimas notícias gerais:\n\n"
            + _get_ultimas_noticias_gerais()
        )

    # Ordena por relevância
    for n in todas_noticias:
        n["score"] = sum(1 for p in palavras_query if p in n["titulo"].lower())
    todas_noticias.sort(key=lambda x: x["score"], reverse=True)

    resultado = f"Notícias sobre '{query}' ({len(todas_noticias)} encontradas):\n\n"
    for n in todas_noticias[:15]:
        resultado += (
            f"[NOTICIA] [{n['fonte']}] {n['titulo']}\n   {n['resumo']}\n   Link: {n['link']}\n\n"
        )

    return resultado


def _get_ultimas_noticias_gerais() -> str:
    """Retorna últimas notícias gerais como fallback."""
    import feedparser

    feeds = {
        "G1": "https://g1.globo.com/rss/g1/",
        "UOL": "https://rss.uol.com.br/feed/noticias.xml",
        "CNN Brasil": "https://www.cnnbrasil.com.br/feed/",
    }
    noticias = []
    for fonte, url in feeds.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                titulo = entry.get("title", "")
                link = entry.get("link", "")
                noticias.append(f"[NOTICIA] [{fonte}] {titulo}\n   Link: {link}")
        except Exception:
            continue
    return "\n\n".join(noticias[:10])


def _tool_salvar_memoria(texto: str) -> str:
    from core.memory import get_memory_service

    service = get_memory_service()
    service.add(texto)
    return f"Memoria salva: '{texto}'"


def _tool_buscar_memoria(query: str) -> str:
    from core.memory import get_memory_service

    service = get_memory_service()
    resultados = service.search(query)
    if not resultados:
        return "Nenhuma memoria relevante encontrada."
    return "Memorias encontradas:\n" + "\n".join(f"- {r}" for r in resultados)


def _tool_listar_arquivos(diretorio: str = ".") -> str:
    path = _validate_path(diretorio)
    if not path.is_dir():
        return f"Diretorio nao encontrado: {path}"
    itens = []
    for item in sorted(path.iterdir()):
        tipo = "DIR" if item.is_dir() else "FILE"
        tamanho = item.stat().st_size if tipo == "FILE" else 0
        itens.append(f"[{tipo}] {item.name}" + (f" ({tamanho} bytes)" if tipo == "FILE" else ""))
    return "\n".join(itens) if itens else "Diretorio vazio."


def _tool_ler_arquivo(caminho: str) -> str:
    path = _validate_path(caminho)
    extensao = path.suffix.lower()
    formatos_texto = [".txt", ".md", ".py", ".json", ".csv", ".xml", ".html", ".css", ".js"]
    if extensao in formatos_texto:
        with open(path, encoding="utf-8", errors="replace") as f:
            conteudo = f.read(10000)
        if len(conteudo) == 10000:
            conteudo += "\n... [arquivo truncado] ..."
        return conteudo
    from processors import processar_arquivo

    return processar_arquivo(str(path), base_dir=path.parent)


def _tool_informacoes_sistema() -> str:
    import platform

    return json.dumps(
        {
            "sistema": platform.system(),
            "versao": platform.version(),
            "python": platform.python_version(),
            "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "diretorio": os.getcwd(),
        },
        indent=2,
    )


def _tool_executar_codigo(codigo: str) -> str:
    from workers.code_worker import executar_codigo

    resultado = executar_codigo(codigo, timeout=30)
    if resultado.timed_out:
        return f"Timeout apos 30s.\nSaida: {resultado.stderr}"
    if resultado.success:
        return resultado.stdout if resultado.stdout else "Codigo executado sem saida."
    return f"Erro (codigo {resultado.returncode}):\n{resultado.stderr}"


def _tool_indexar_documento(caminho: str) -> str:
    from core.documents import get_document_library_service

    path = _validate_path(caminho)
    item = get_document_library_service().import_path(path, origin="Ferramenta do Celsius")
    return f"Documento '{item['filename']}' indexado: {item['chunk_count']} trechos criados."


def _tool_navegar_web(url: str) -> str:
    from ai.browser import navegar_web

    return navegar_web(url)


def _tool_listar_documentos_rag() -> str:
    from core.documents import get_document_library_service

    return get_document_library_service().list_text()


def _tool_remover_documento(nome_doc: str) -> str:
    from core.documents import get_document_library_service

    removed = get_document_library_service().delete_by_name(nome_doc)
    return (
        f"Documento '{nome_doc}' removido da biblioteca local."
        if removed
        else f"Documento '{nome_doc}' nao encontrado."
    )


def _tool_abrir_no_navegador(url: str) -> str:
    import re

    # If it's not a full URL, try to convert site name to URL
    url_lower = url.lower().strip()

    # YouTube search: "youtube X" → search X on YouTube
    yt_match = re.match(r"^youtube\s+(.+)$", url_lower)
    if yt_match:
        termo = yt_match.group(1).strip()
        if termo:
            target_url = (
                f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(termo)}"
            )
            return _abrir_url(target_url)

    # Google search: "google X" → search X on Google
    gg_match = re.match(r"^google\s+(.+)$", url_lower)
    if gg_match:
        termo = gg_match.group(1).strip()
        if termo:
            target_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(termo)}"
            return _abrir_url(target_url)

    # Common site mappings
    site_mappings = {
        "magazine luiza": "https://www.magazineluiza.com.br",
        "magazineluiza": "https://www.magazineluiza.com.br",
        "fundação bradesco": "https://www.fundacaobradesco.org.br",
        "fundacao bradesco": "https://www.fundacaobradesco.org.br",
        "unimar ead": "https://ead.unimar.br",
        "unimar": "https://www.unimar.br",
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "linkedin": "https://www.linkedin.com",
        "facebook": "https://www.facebook.com",
        "instagram": "https://www.instagram.com",
        "twitter": "https://twitter.com",
        "x": "https://twitter.com",
    }

    target_url = None

    # Check if it's a known site
    for site_name, site_url in site_mappings.items():
        if site_name in url_lower:
            target_url = site_url
            break

    # If it looks like a domain, add https://
    if target_url is None and (
        re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", url_lower)
        or url_lower.startswith(("http://", "https://"))
    ):
        target_url = url if url.startswith(("http://", "https://")) else f"https://{url}"

    # Otherwise, search for it first
    if target_url is None:
        target_url = f"https://www.google.com/search?q={url}"

    return _abrir_url(target_url)


def _abrir_url(target_url: str) -> str:
    """Abre URL no navegador padrao do sistema."""
    import webbrowser

    try:
        webbrowser.open(target_url)
        return f"Abrindo {target_url} no navegador..."
    except Exception as e:
        return f"Erro ao abrir navegador: {e}"


# ── Estoque tool functions ────────────────────────────────────


def _tool_listar_clientes(filtro: str = "", limite: int = 50) -> str:
    from core.relationships import get_relationship_service

    return get_relationship_service().format_customers(filtro, limite)


def _tool_cadastrar_cliente(
    nome: str,
    documento: str = "",
    contato: str = "",
    telefone: str = "",
    email: str = "",
    segmento: str = "",
    observacoes: str = "",
) -> str:
    from core.relationships import RelationshipError, get_relationship_service

    try:
        item = get_relationship_service().save_customer(
            {
                "nome": nome,
                "documento": documento,
                "contato": contato,
                "telefone": telefone,
                "email": email,
                "segmento": segmento,
                "observacoes": observacoes,
            }
        )
    except RelationshipError as exc:
        return f"Nao foi possivel cadastrar o cliente: {exc}"
    return f"Cliente cadastrado com sucesso. ID: {item['id']} | Nome: {item['name']}"


def _tool_listar_fornecedores(filtro: str = "", limite: int = 50) -> str:
    from core.relationships import get_relationship_service

    return get_relationship_service().format_suppliers(filtro, limite)


def _tool_cadastrar_fornecedor(
    nome: str,
    documento: str = "",
    contato: str = "",
    telefone: str = "",
    email: str = "",
    categoria: str = "",
    produtos: str = "",
    prazo_pagamento: str = "",
    lead_time_dias: str = "",
    observacoes: str = "",
) -> str:
    from core.relationships import RelationshipError, get_relationship_service

    try:
        item = get_relationship_service().save_supplier(
            {
                "nome": nome,
                "documento": documento,
                "contato": contato,
                "telefone": telefone,
                "email": email,
                "categoria": categoria,
                "produtos": produtos,
                "prazo_pagamento": prazo_pagamento,
                "lead_time_dias": lead_time_dias,
                "observacoes": observacoes,
            }
        )
    except RelationshipError as exc:
        return f"Nao foi possivel cadastrar o fornecedor: {exc}"
    return f"Fornecedor cadastrado com sucesso. ID: {item['id']} | Nome: {item['name']}"


def _tool_listar_produtos_servicos(filtro: str = "", limite: int = 50) -> str:
    from core.operations import get_operations_service

    return get_operations_service().format_products(filtro, limite)


def _tool_cadastrar_produto_servico(
    nome: str,
    codigo: str = "",
    tipo: str = "Produto",
    categoria: str = "",
    unidade: str = "",
    preco: str = "",
    custo: str = "",
    fornecedor_padrao: str = "",
    observacoes: str = "",
) -> str:
    from core.operations import OperationsError, get_operations_service

    try:
        item = get_operations_service().save_product(
            {
                "nome": nome,
                "codigo": codigo,
                "tipo": tipo,
                "categoria": categoria,
                "unidade": unidade,
                "preco": preco,
                "custo": custo,
                "fornecedor_padrao": fornecedor_padrao,
                "observacoes": observacoes,
            }
        )
    except OperationsError as exc:
        return f"Nao foi possivel cadastrar no catalogo: {exc}"
    return f"Cadastro comercial salvo. ID: {item['id']} | Nome: {item['name']}"


def _tool_listar_orcamentos(filtro: str = "", limite: int = 50) -> str:
    from core.workflows import get_workflow_service

    return get_workflow_service().format_quotes(filtro, limite)


def _tool_cadastrar_orcamento(
    titulo: str,
    cliente: str = "",
    valor: str = "",
    validade: str = "",
    margem: str = "",
    itens: str = "",
    observacoes: str = "",
) -> str:
    from core.workflows import WorkflowError, get_workflow_service

    try:
        item = get_workflow_service().save_quote(
            {
                "titulo": titulo,
                "cliente": cliente,
                "valor": valor,
                "validade": validade,
                "margem": margem,
                "itens": itens,
                "observacoes": observacoes,
            }
        )
    except WorkflowError as exc:
        return f"Nao foi possivel cadastrar o orcamento: {exc}"
    return f"Orcamento salvo. Numero: {item['number']} | ID: {item['id']}"


def _tool_listar_processos_prazos(filtro: str = "", limite: int = 50) -> str:
    from core.workflows import get_workflow_service

    return get_workflow_service().format_cases(filtro, limite)


def _tool_cadastrar_processo_prazo(
    processo: str,
    cliente: str = "",
    prazo: str = "",
    prioridade: str = "Normal",
    responsavel: str = "",
    proximo_passo: str = "",
    observacoes: str = "",
) -> str:
    from core.workflows import WorkflowError, get_workflow_service

    try:
        item = get_workflow_service().save_case(
            {
                "processo": processo,
                "cliente": cliente,
                "prazo": prazo,
                "prioridade": prioridade,
                "responsavel": responsavel,
                "proximo_passo": proximo_passo,
                "observacoes": observacoes,
            }
        )
    except WorkflowError as exc:
        return f"Nao foi possivel cadastrar o processo ou prazo: {exc}"
    return f"Processo ou prazo salvo. ID: {item['id']} | Nome: {item['title']}"


def _tool_gerar_relatorio_local(
    titulo: str,
    tipo: str = "Executivo",
    fonte: str = "Executivo",
    formato: str = "pdf",
    periodo: str = "Atual",
    observacoes: str = "",
) -> str:
    from core.workflows import WorkflowError, get_workflow_service

    service = get_workflow_service()
    try:
        item = service.generate_report(
            {
                "titulo": titulo,
                "tipo": tipo,
                "fonte_dados": fonte,
                "formato": formato,
                "periodo": periodo,
                "observacoes": observacoes,
            }
        )
        path = service.report_file(item["id"])
    except WorkflowError as exc:
        return f"Nao foi possivel gerar o relatorio: {exc}"
    return (
        f"Relatorio gerado localmente. ID: {item['id']} | Arquivo: {path}\n"
        f"[Baixar relatorio](/api/v1/reports/{item['id']}/download)"
    )


def _tool_listar_agenda(dias: int = 14) -> str:
    from core.agenda import get_agenda_service

    service = get_agenda_service()
    dias = max(1, min(int(dias or 14), 365))
    events = service.upcoming(days=dias)
    if not events:
        return "Nenhum compromisso futuro cadastrado na agenda local."

    resultado = f"Agenda local - proximos {dias} dias ({len(events)} compromissos):\n\n"
    for event in events:
        details = [
            event.starts_at.strftime("%d/%m/%Y %H:%M"),
            event.status or "Agendado",
        ]
        if event.customer:
            details.append(f"cliente: {event.customer}")
        if event.responsible:
            details.append(f"responsavel: {event.responsible}")
        if event.location:
            details.append(f"local: {event.location}")
        resultado += f"[{event.id}] {event.title} | {' | '.join(details)}\n"
    return resultado.strip()


def _tool_criar_compromisso_agenda(
    titulo: str,
    data_hora: str,
    cliente: str = "",
    responsavel: str = "",
    local: str = "",
    lembrete_minutos: int = 15,
    observacoes: str = "",
) -> str:
    from core.agenda import parse_agenda_datetime
    from core.business_records import get_business_record_service
    from core.modules import MODULE_AGENDA

    starts_at = parse_agenda_datetime(data_hora)
    if starts_at is None:
        return (
            "Nao consegui entender a data/hora do compromisso. "
            "Use um formato como 31/07/2026 14:30."
        )

    title = titulo.strip()
    if not title:
        return "Titulo do compromisso e obrigatorio."

    reminder = max(0, int(lembrete_minutos or 0))
    service = get_business_record_service()
    record = service.save_record(
        MODULE_AGENDA,
        title=title,
        fields={
            "titulo": title,
            "tipo": "Outro",
            "data_hora": starts_at.strftime("%d/%m/%Y %H:%M"),
            "cliente": cliente,
            "responsavel": responsavel,
            "local": local,
            "lembrete_minutos": str(reminder),
            "status": "Agendado",
            "observacoes": observacoes,
        },
    )
    return (
        "Compromisso cadastrado na agenda local.\n"
        f"ID: {record.id}\n"
        f"Titulo: {record.title}\n"
        f"Quando: {starts_at.strftime('%d/%m/%Y %H:%M')}\n"
        f"Lembrete: {reminder} minutos antes"
    )


def _tool_marcar_lembrete_agenda(evento_id: str) -> str:
    from core.agenda import get_agenda_service

    service = get_agenda_service()
    if service.mark_reminded(evento_id):
        return "Lembrete da agenda marcado como avisado."
    return f"Compromisso com ID '{evento_id}' nao encontrado."


def _stock_status_label(item) -> str:
    status = getattr(item, "stock_status", None)
    if status is not None:
        return status.label
    if item.quantidade <= 0:
        return "Sem Estoque"
    if item.quantidade <= item.estoque_min:
        return "Critico"
    if item.estoque_max > 0 and item.quantidade > item.estoque_max:
        return "Excesso"
    return "Normal"


def _tool_listar_estoque() -> str:
    from core.inventory import ColunaKanban, get_inventory_service

    service = get_inventory_service()
    items = service.get_all_items()
    if not items:
        return "O estoque esta vazio. Nenhum item cadastrado."

    colunas = {}
    for item in items:
        colunas.setdefault(item.localizacao, []).append(item)

    resultado = f"Estoque completo ({len(items)} itens):\n\n"
    for col in ColunaKanban:
        itens_col = colunas.get(col.value, [])
        if not itens_col:
            continue
        resultado += f"=== {col.label} ({len(itens_col)}) ===\n"
        for item in itens_col:
            resultado += (
                f"  [{item.id}] {item.nome} | {item.categoria} | "
                f"{item.quantidade} un. (min:{item.estoque_min} max:{item.estoque_max}) | "
                f"Saude: {_stock_status_label(item)}\n"
            )
        resultado += "\n"
    return resultado.strip()


def _tool_buscar_item_estoque(query: str) -> str:
    from core.inventory import get_inventory_service

    service = get_inventory_service()
    itens = service.buscar(query)
    if not itens:
        return f"Nenhum item encontrado para '{query}'."
    resultado = f"Resultados da busca por '{query}' ({len(itens)} itens):\n\n"
    for item in itens:
        status = _stock_status_label(item).upper()
        resultado += (
            f"  [{item.id}] {item.nome} | {item.categoria} | "
            f"{item.quantidade} un. (min:{item.estoque_min} max:{item.estoque_max}) | Status: {status}\n"
        )
    return resultado.strip()


def _tool_entrada_estoque(item_id: str, quantidade: int) -> str:
    from core.inventory import get_inventory_service

    service = get_inventory_service()
    mov = service.entrada(item_id, quantidade)
    if not mov:
        item = service.get_item(item_id)
        if not item:
            return f"Item com ID '{item_id}' nao encontrado."
        return "Erro ao registrar entrada. Verifique a quantidade."
    return (
        f"Entrada registrada: +{quantidade} un. de '{mov.item_nome}'\n"
        f"Estoque anterior: {mov.quantidade_anterior} | Estoque atual: {mov.quantidade_nova}"
    )


def _tool_saida_estoque(item_id: str, quantidade: int) -> str:
    from core.inventory import get_inventory_service

    service = get_inventory_service()
    item = service.get_item(item_id)
    if not item:
        return f"Item com ID '{item_id}' nao encontrado."
    if quantidade > item.quantidade:
        return (
            f"Saida negada: quantidade solicitada ({quantidade}) "
            f"maior que o disponivel ({item.quantidade})."
        )
    mov = service.saida(item_id, quantidade)
    if not mov:
        return "Erro ao registrar saida."
    alerta = ""
    if item.precisa_repor:
        alerta = f"\n**ALERTA: Estoque abaixo do minimo ({item.estoque_min})!**"
    return (
        f"Saida registrada: -{quantidade} un. de '{mov.item_nome}'\n"
        f"Estoque anterior: {mov.quantidade_anterior} | Estoque atual: {mov.quantidade_nova}{alerta}"
    )


def _tool_adicionar_item_estoque(
    nome: str, categoria: str, quantidade: int, estoque_minimo: int, estoque_maximo: int
) -> str:
    from core.inventory import get_inventory_service

    service = get_inventory_service()
    item = service.adicionar_item(
        nome=nome,
        categoria=categoria,
        quantidade=quantidade,
        estoque_min=estoque_minimo,
        estoque_max=estoque_maximo,
    )
    return (
        f"Item cadastrado com sucesso!\n"
        f"  ID: {item.id}\n"
        f"  Nome: {item.nome}\n"
        f"  Categoria: {item.categoria}\n"
        f"  Quantidade: {item.quantidade}\n"
        f"  Min: {item.estoque_min} | Max: {item.estoque_max}\n"
        f"  Coluna Kanban: {item.coluna.label}"
    )


def _tool_itens_estoque_baixo() -> str:
    from core.inventory import get_inventory_service

    service = get_inventory_service()
    itens = service.itens_estoque_baixo()
    if not itens:
        return "Nenhum item com estoque abaixo do minimo. Tudo em ordem!"
    resultado = f"**{len(itens)} item(s) com estoque abaixo do minimo:**\n\n"
    for item in itens:
        resultado += (
            f"  [{item.id}] {item.nome} | {item.categoria} | "
            f"{item.quantidade}/{item.estoque_min} un.\n"
        )
    return resultado.strip()


def _tool_historico_movimentacoes(item_id: str = None) -> str:
    from core.inventory import get_inventory_service

    service = get_inventory_service()
    movs = service.get_movimentacoes(item_id)
    if not movs:
        return (
            "Nenhuma movimentacao registrada."
            if not item_id
            else f"Nenhuma movimentacao para o item '{item_id}'."
        )
    resultado = f"Historico de movimentacoes ({len(movs)} registros):\n\n"
    for mov in reversed(movs[-30:]):
        sinal = "+" if mov.tipo == "entrada" else "-"
        resultado += (
            f"  [{mov.timestamp}] {mov.tipo.upper()}: "
            f"{mov.item_nome} {sinal}{mov.quantidade} un. "
            f"({mov.quantidade_anterior} -> {mov.quantidade_nova})\n"
        )
    return resultado.strip()


_CHART_ARGUMENT_NAMES = {
    "tipo",
    "titulo",
    "labels",
    "valores",
    "legendas",
    "xlabel",
    "ylabel",
    "cores",
    "meta",
    "unidade",
    "subtitulo",
}
_CHART_TYPE_ALIASES = {
    "barra": "bar",
    "barras": "bar",
    "bar": "bar",
    "barra_horizontal": "barh",
    "barras_horizontais": "barh",
    "barh": "barh",
    "agrupado": "grouped_bar",
    "barras_agrupadas": "grouped_bar",
    "grouped_bar": "grouped_bar",
    "empilhado": "stacked_bar",
    "barras_empilhadas": "stacked_bar",
    "stacked_bar": "stacked_bar",
    "pizza": "pie",
    "pie": "pie",
    "rosca": "donut",
    "donut": "donut",
    "linha": "line",
    "linhas": "line",
    "line": "line",
    "area": "area",
    "histograma": "histogram",
    "histogram": "histogram",
    "dispersao": "scatter",
    "dispersão": "scatter",
    "scatter": "scatter",
    "radar": "radar",
    "mapa_de_calor": "heatmap",
    "heatmap": "heatmap",
    "cascata": "waterfall",
    "waterfall": "waterfall",
    "funil": "funnel",
    "funnel": "funnel",
    "caixa": "boxplot",
    "boxplot": "boxplot",
    "combinado": "combo",
    "combo": "combo",
    "velocimetro": "gauge",
    "velocímetro": "gauge",
    "gauge": "gauge",
    "indicador": "kpi",
    "kpi": "kpi",
}


def _json_array_argument(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _normalize_chart_arguments(arguments: dict) -> dict:
    """Accept both the chart schema and common record-list calls from local LLMs."""
    if not isinstance(arguments, dict):
        return {}

    normalized = {key: value for key, value in arguments.items() if key in _CHART_ARGUMENT_NAMES}
    chart_type = (
        str(normalized.get("tipo", "bar")).strip().lower().replace(" ", "_").replace("-", "_")
    )
    normalized["tipo"] = _CHART_TYPE_ALIASES.get(chart_type, chart_type)
    normalized["titulo"] = str(normalized.get("titulo") or "Grafico")
    normalized["unidade"] = str(normalized.get("unidade") or arguments.get("unit") or "")
    normalized["subtitulo"] = str(normalized.get("subtitulo") or arguments.get("descricao") or "")
    if "meta" not in normalized:
        normalized["meta"] = arguments.get(
            "target",
            arguments.get("objetivo", arguments.get("benchmark", 0)),
        )

    data = arguments.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = None

    if isinstance(data, dict):
        if "labels" not in normalized:
            normalized["labels"] = data.get("labels", data.get("categorias"))
        if "valores" not in normalized:
            normalized["valores"] = data.get(
                "valores",
                data.get(
                    "values",
                    data.get("valor", data.get("value", data.get("atual"))),
                ),
            )
        if not normalized.get("meta"):
            normalized["meta"] = data.get(
                "meta",
                data.get("target", data.get("objetivo", 0)),
            )
        if not normalized.get("unidade"):
            normalized["unidade"] = str(data.get("unidade", data.get("unit", "")))
        data = data.get("data", data.get("itens", data.get("items")))

    if (
        ("labels" not in normalized or "valores" not in normalized)
        and isinstance(data, list)
        and data
        and all(isinstance(record, dict) for record in data)
    ):
        first_record = data[0]
        label_key = next(
            (
                key
                for key in ("nome", "label", "produto", "item", "categoria", "periodo")
                if key in first_record
            ),
            None,
        )
        value_key = next(
            (
                key
                for key in ("quantidade", "valor", "total", "value", "saldo", "preco")
                if key in first_record
            ),
            None,
        )
        if label_key is None:
            label_key = next(
                (key for key, value in first_record.items() if isinstance(value, str)),
                None,
            )
        if value_key is None:
            value_key = next(
                (
                    key
                    for key, value in first_record.items()
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                ),
                None,
            )
        if label_key and value_key:
            normalized["labels"] = [str(record.get(label_key, "")) for record in data]
            normalized["valores"] = [record.get(value_key, 0) for record in data]

    if "valores" not in normalized and isinstance(data, list):
        normalized["valores"] = data
    if "valores" in normalized and not isinstance(
        normalized["valores"],
        (list, tuple, str),
    ):
        normalized["valores"] = [normalized["valores"]]
    if "labels" not in normalized and normalized.get("valores") is not None:
        raw_values = normalized["valores"]
        value_count = len(raw_values) if isinstance(raw_values, (list, tuple)) else 1
        normalized["labels"] = [
            normalized["titulo"] if value_count == 1 else f"Item {index + 1}"
            for index in range(value_count)
        ]
    if "labels" in normalized and not isinstance(
        normalized["labels"],
        (list, tuple, str),
    ):
        normalized["labels"] = [normalized["labels"]]

    for name in ("labels", "valores", "legendas", "cores"):
        if name in normalized and normalized[name] is not None:
            normalized[name] = _json_array_argument(normalized[name])

    try:
        normalized["meta"] = float(normalized.get("meta") or 0)
    except (TypeError, ValueError):
        normalized["meta"] = 0.0

    return normalized


def _tool_gerar_grafico(
    tipo: str,
    titulo: str,
    labels: str,
    valores: str,
    legendas: str = "",
    xlabel: str = "",
    ylabel: str = "",
    cores: str = "",
    meta: float = 0,
    unidade: str = "",
    subtitulo: str = "",
) -> str:
    """Render a local business chart through the shared chart engine."""
    from core.charts import ChartError, render_business_chart

    try:
        labels_list = json.loads(labels)
        values_list = json.loads(valores)
        legends_list = json.loads(legendas) if legendas else []
        colors_list = json.loads(cores) if cores else []
        filepath = render_business_chart(
            chart_type=tipo,
            title=titulo,
            labels=labels_list,
            values=values_list,
            legends=legends_list,
            colors=colors_list,
            xlabel=xlabel,
            ylabel=ylabel,
            target=meta,
            unit=unidade,
            subtitle=subtitulo,
            output_dir=get_settings().data_dir / "cache" / "charts",
        )
    except (ChartError, json.JSONDecodeError, TypeError) as exc:
        return f"Erro ao gerar grafico: {exc}"

    return (
        f"Grafico '{tipo}' gerado com sucesso.\n"
        f"Arquivo: {filepath}\n"
        f"Exiba-o com: ![Grafico - {titulo}]({filepath})"
    )


REGISTRO_FERRAMENTAS = [
    Ferramenta(
        nome="processar_arquivo",
        descricao="Extrai e analisa o conteudo de um arquivo (PDF, DOCX, ODF, imagem, audio). Use quando o usuario enviar ou mencionar um arquivo para analise.",
        schema={
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho completo do arquivo a ser processado",
                }
            },
            "required": ["caminho"],
        },
        funcao=_tool_processar_arquivo,
    ),
    Ferramenta(
        nome="pesquisar_web",
        descricao="Busca informacoes na internet usando DuckDuckGo. Use quando precisar de dados atualizados, noticias, ou informacoes que nao estao no seu conhecimento.",
        schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termo de busca",
                }
            },
            "required": ["query"],
        },
        funcao=_tool_pesquisar_web,
    ),
    Ferramenta(
        nome="pesquisar_google",
        descricao="Busca no Google usando browser headless. Use para pesquisas mais precisas ou quando o DuckDuckGo nao retornar bons resultados.",
        schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termo de busca no Google",
                }
            },
            "required": ["query"],
        },
        funcao=_tool_pesquisar_google,
    ),
    Ferramenta(
        nome="pesquisar_noticias",
        descricao="Busca noticias atuais via RSS de sites brasileiros (G1, UOL, Folha, Estadão, CNN, BBC). Use quando o usuario pedir noticias recentes, ultimas noticias, ou atualidades sobre um tema. Mais confiável que Google News.",
        schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termo de busca para noticias",
                }
            },
            "required": ["query"],
        },
        funcao=_tool_pesquisar_noticias,
    ),
    Ferramenta(
        nome="salvar_memoria",
        descricao="Armazena um fato importante na memoria de longo prazo para lembrar em futuras conversas. Use quando o usuario pedir para lembrar de algo.",
        schema={
            "type": "object",
            "properties": {
                "texto": {
                    "type": "string",
                    "description": "O fato ou informacao a ser lembrada",
                }
            },
            "required": ["texto"],
        },
        funcao=_tool_salvar_memoria,
    ),
    Ferramenta(
        nome="buscar_memoria",
        descricao="Busca na memoria de longo prazo por informacoes relevantes. Use quando precisar lembrar de algo que o usuario disse anteriormente.",
        schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termo de busca nas memorias",
                }
            },
            "required": ["query"],
        },
        funcao=_tool_buscar_memoria,
    ),
    Ferramenta(
        nome="listar_arquivos",
        descricao="Lista arquivos e pastas em um diretorio. Use quando o usuario pedir para ver o que ha em uma pasta.",
        schema={
            "type": "object",
            "properties": {
                "diretorio": {
                    "type": "string",
                    "description": "Caminho do diretorio (relativo ou absoluto). Padrao: diretorio atual.",
                }
            },
        },
        funcao=_tool_listar_arquivos,
    ),
    Ferramenta(
        nome="ler_arquivo",
        descricao="Le o conteudo de um arquivo de texto ou documento. Use quando precisar ler o conteudo de um arquivo especifico.",
        schema={
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho completo do arquivo a ser lido",
                }
            },
            "required": ["caminho"],
        },
        funcao=_tool_ler_arquivo,
    ),
    Ferramenta(
        nome="informacoes_sistema",
        descricao="Retorna informacoes do sistema (SO, Python, data/hora). Use quando o usuario perguntar sobre o ambiente ou configuracao do sistema.",
        schema={"type": "object", "properties": {}},
        funcao=_tool_informacoes_sistema,
    ),
    Ferramenta(
        nome="executar_codigo",
        descricao="Executa um script Python e retorna a saida. Use quando precisar calcular algo, processar dados, criar graficos, ou testar logica.",
        schema={
            "type": "object",
            "properties": {
                "codigo": {
                    "type": "string",
                    "description": "Codigo Python a ser executado",
                }
            },
            "required": ["codigo"],
        },
        funcao=_tool_executar_codigo,
    ),
    Ferramenta(
        nome="indexar_documento",
        descricao="Indexa um documento para busca semantica futura (RAG). Use quando o usuario quiser guardar um documento para consultas posteriores.",
        schema={
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho do arquivo a ser indexado",
                }
            },
            "required": ["caminho"],
        },
        funcao=_tool_indexar_documento,
    ),
    Ferramenta(
        nome="navegar_web",
        descricao="Abre uma pagina web e retorna o conteudo estruturado. Use para acessar sites, extrair informacoes especificas, ou interagir com paginas.",
        schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL da pagina a ser acessada",
                }
            },
            "required": ["url"],
        },
        funcao=_tool_navegar_web,
    ),
    Ferramenta(
        nome="listar_documentos_rag",
        descricao="Lista todos os documentos indexados no sistema RAG. Use quando o usuario perguntar quais documentos estao disponiveis.",
        schema={"type": "object", "properties": {}},
        funcao=_tool_listar_documentos_rag,
    ),
    Ferramenta(
        nome="remover_documento",
        descricao="Remove um documento do indice RAG. Use quando o usuario quiser deletar um documento indexado.",
        schema={
            "type": "object",
            "properties": {
                "nome_doc": {
                    "type": "string",
                    "description": "Nome do documento a ser removido",
                }
            },
            "required": ["nome_doc"],
        },
        funcao=_tool_remover_documento,
    ),
    Ferramenta(
        nome="abrir_no_navegador",
        descricao="Abre um site ou pesquisa no navegador. Para YouTube: passe 'youtube [termo]'. Para Google: passe 'google [termo]'. Para outros sites: passe a URL ou nome do site.",
        schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL completa para abrir no navegador",
                }
            },
            "required": ["url"],
        },
        funcao=_tool_abrir_no_navegador,
    ),
    # ── Estoque ────────────────────────────────────────────────
    Ferramenta(
        nome="listar_clientes",
        descricao="Lista clientes reais cadastrados localmente. Use para consultar clientes sem inventar dados.",
        schema={
            "type": "object",
            "properties": {
                "filtro": {"type": "string", "description": "Nome, documento ou contato"},
                "limite": {"type": "integer", "description": "Maximo de resultados"},
            },
        },
        funcao=_tool_listar_clientes,
    ),
    Ferramenta(
        nome="cadastrar_cliente",
        descricao="Cadastra um cliente na base local quando o usuario pedir explicitamente.",
        schema={
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome ou razao social"},
                "documento": {"type": "string", "description": "CPF, CNPJ ou documento"},
                "contato": {"type": "string", "description": "Pessoa de contato"},
                "telefone": {"type": "string"},
                "email": {"type": "string"},
                "segmento": {"type": "string"},
                "observacoes": {"type": "string"},
            },
            "required": ["nome"],
        },
        funcao=_tool_cadastrar_cliente,
    ),
    Ferramenta(
        nome="listar_fornecedores",
        descricao="Lista fornecedores reais cadastrados localmente. Use para consultar fornecedores sem inventar dados.",
        schema={
            "type": "object",
            "properties": {
                "filtro": {
                    "type": "string",
                    "description": "Nome, documento, categoria ou produto",
                },
                "limite": {"type": "integer", "description": "Maximo de resultados"},
            },
        },
        funcao=_tool_listar_fornecedores,
    ),
    Ferramenta(
        nome="cadastrar_fornecedor",
        descricao="Cadastra um fornecedor na base local quando o usuario pedir explicitamente.",
        schema={
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome ou razao social"},
                "documento": {"type": "string", "description": "CNPJ ou documento"},
                "contato": {"type": "string"},
                "telefone": {"type": "string"},
                "email": {"type": "string"},
                "categoria": {"type": "string"},
                "produtos": {"type": "string"},
                "prazo_pagamento": {"type": "string"},
                "lead_time_dias": {"type": "string"},
                "observacoes": {"type": "string"},
            },
            "required": ["nome"],
        },
        funcao=_tool_cadastrar_fornecedor,
    ),
    Ferramenta(
        nome="listar_produtos_servicos",
        descricao="Lista produtos, servicos, pacotes e assinaturas do catalogo comercial local com codigo, preco e status.",
        schema={
            "type": "object",
            "properties": {
                "filtro": {"type": "string", "description": "Nome, codigo ou categoria"},
                "limite": {"type": "integer", "description": "Maximo de resultados"},
            },
        },
        funcao=_tool_listar_produtos_servicos,
    ),
    Ferramenta(
        nome="cadastrar_produto_servico",
        descricao="Cadastra um produto ou servico no catalogo comercial local quando o usuario pedir explicitamente.",
        schema={
            "type": "object",
            "properties": {
                "nome": {"type": "string"},
                "codigo": {"type": "string", "description": "Codigo ou SKU"},
                "tipo": {
                    "type": "string",
                    "enum": ["Produto", "Servico", "Pacote", "Assinatura"],
                },
                "categoria": {"type": "string"},
                "unidade": {"type": "string"},
                "preco": {"type": "string", "description": "Preco de venda"},
                "custo": {"type": "string"},
                "fornecedor_padrao": {"type": "string"},
                "observacoes": {"type": "string"},
            },
            "required": ["nome"],
        },
        funcao=_tool_cadastrar_produto_servico,
    ),
    Ferramenta(
        nome="listar_orcamentos",
        descricao="Lista orcamentos reais da base local, com numero, cliente, valor e status.",
        schema={
            "type": "object",
            "properties": {
                "filtro": {"type": "string", "description": "Numero, titulo ou cliente"},
                "limite": {"type": "integer", "description": "Maximo de resultados"},
            },
        },
        funcao=_tool_listar_orcamentos,
    ),
    Ferramenta(
        nome="cadastrar_orcamento",
        descricao="Cria um orcamento local quando o usuario pedir explicitamente.",
        schema={
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "cliente": {"type": "string"},
                "valor": {"type": "string", "description": "Valor total"},
                "validade": {"type": "string", "description": "Data no formato AAAA-MM-DD"},
                "margem": {"type": "string"},
                "itens": {"type": "string"},
                "observacoes": {"type": "string"},
            },
            "required": ["titulo"],
        },
        funcao=_tool_cadastrar_orcamento,
    ),
    Ferramenta(
        nome="listar_processos_prazos",
        descricao="Lista processos, casos e prazos reais mantidos localmente, incluindo atrasos.",
        schema={
            "type": "object",
            "properties": {
                "filtro": {"type": "string", "description": "Processo, cliente ou responsavel"},
                "limite": {"type": "integer", "description": "Maximo de resultados"},
            },
        },
        funcao=_tool_listar_processos_prazos,
    ),
    Ferramenta(
        nome="cadastrar_processo_prazo",
        descricao="Cadastra um processo ou prazo local quando o usuario pedir explicitamente.",
        schema={
            "type": "object",
            "properties": {
                "processo": {"type": "string"},
                "cliente": {"type": "string"},
                "prazo": {"type": "string", "description": "Data no formato AAAA-MM-DD"},
                "prioridade": {
                    "type": "string",
                    "enum": ["Baixa", "Normal", "Alta", "Critica"],
                },
                "responsavel": {"type": "string"},
                "proximo_passo": {"type": "string"},
                "observacoes": {"type": "string"},
            },
            "required": ["processo"],
        },
        funcao=_tool_cadastrar_processo_prazo,
    ),
    Ferramenta(
        nome="gerar_relatorio_local",
        descricao="Gera um arquivo PDF, DOCX ou Markdown com dados empresariais locais do Celsius.",
        schema={
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "tipo": {
                    "type": "string",
                    "enum": ["Executivo", "Operacional", "Estoque", "Vendas", "Clientes"],
                },
                "fonte": {
                    "type": "string",
                    "enum": [
                        "Executivo",
                        "Estoque",
                        "Clientes",
                        "Fornecedores",
                        "Orcamentos",
                        "Processos e prazos",
                    ],
                },
                "formato": {"type": "string", "enum": ["pdf", "docx", "md"]},
                "periodo": {"type": "string"},
                "observacoes": {"type": "string"},
            },
            "required": ["titulo"],
        },
        funcao=_tool_gerar_relatorio_local,
    ),
    Ferramenta(
        nome="listar_agenda",
        descricao="Lista compromissos futuros da agenda local do usuario. Use para perguntas sobre agenda, consultas, visitas, prazos, lembretes e proximos compromissos.",
        schema={
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Quantidade de dias futuros para consultar. Padrao: 14.",
                }
            },
        },
        funcao=_tool_listar_agenda,
    ),
    Ferramenta(
        nome="criar_compromisso_agenda",
        descricao="Cria um compromisso ou lembrete na agenda local do usuario. Use quando o usuario pedir para marcar, agendar ou lembrar de algo.",
        schema={
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Titulo do compromisso"},
                "data_hora": {
                    "type": "string",
                    "description": "Data e hora. Exemplo: 31/07/2026 14:30.",
                },
                "cliente": {"type": "string", "description": "Cliente ou paciente relacionado"},
                "responsavel": {"type": "string", "description": "Responsavel pelo compromisso"},
                "local": {"type": "string", "description": "Local do compromisso"},
                "lembrete_minutos": {
                    "type": "integer",
                    "description": "Minutos antes para emitir lembrete. Padrao: 15.",
                },
                "observacoes": {"type": "string", "description": "Observacoes adicionais"},
            },
            "required": ["titulo", "data_hora"],
        },
        funcao=_tool_criar_compromisso_agenda,
    ),
    Ferramenta(
        nome="marcar_lembrete_agenda",
        descricao="Marca um lembrete de agenda como avisado, evitando repeticao do alerta.",
        schema={
            "type": "object",
            "properties": {
                "evento_id": {
                    "type": "string",
                    "description": "ID do compromisso retornado por listar_agenda.",
                }
            },
            "required": ["evento_id"],
        },
        funcao=_tool_marcar_lembrete_agenda,
    ),
    Ferramenta(
        nome="listar_estoque",
        descricao="Lista todos os itens do estoque com quantidade, minimo, maximo e coluna Kanban. Use quando o usuario perguntar sobre o estoque, quais itens tem, ou pedir um resumo geral.",
        schema={"type": "object", "properties": {}},
        funcao=_tool_listar_estoque,
    ),
    Ferramenta(
        nome="buscar_item_estoque",
        descricao="Busca um item no estoque por nome ou categoria. Use quando o usuario quiser saber a quantidade de um item especifico.",
        schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nome ou categoria do item para buscar",
                }
            },
            "required": ["query"],
        },
        funcao=_tool_buscar_item_estoque,
    ),
    Ferramenta(
        nome="entrada_estoque",
        descricao="Registra entrada de itens no estoque (aumenta a quantidade). Use quando o usuario disser que entrou, recebeu, comprou, ou adicionou itens.",
        schema={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID do item (obtido via listar_estoque ou buscar_item_estoque)",
                },
                "quantidade": {
                    "type": "integer",
                    "description": "Quantidade a entrada",
                },
            },
            "required": ["item_id", "quantidade"],
        },
        funcao=_tool_entrada_estoque,
    ),
    Ferramenta(
        nome="saida_estoque",
        descricao="Registra saida de itens do estoque (diminui a quantidade). Use quando o usuario disser que usou, enviou, vendeu, ou removeu itens.",
        schema={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID do item (obtido via listar_estoque ou buscar_item_estoque)",
                },
                "quantidade": {
                    "type": "integer",
                    "description": "Quantidade a saida",
                },
            },
            "required": ["item_id", "quantidade"],
        },
        funcao=_tool_saida_estoque,
    ),
    Ferramenta(
        nome="adicionar_item_estoque",
        descricao="Adiciona um novo item ao estoque. Use quando o usuario quiser cadastrar um item novo.",
        schema={
            "type": "object",
            "properties": {
                "nome": {
                    "type": "string",
                    "description": "Nome do item",
                },
                "categoria": {
                    "type": "string",
                    "description": "Categoria do item (ex: Alimentos, Limpeza, Eletronicos)",
                },
                "quantidade": {
                    "type": "integer",
                    "description": "Quantidade inicial",
                },
                "estoque_minimo": {
                    "type": "integer",
                    "description": "Estoque minimo para alerta",
                },
                "estoque_maximo": {
                    "type": "integer",
                    "description": "Estoque maximo",
                },
            },
            "required": ["nome", "categoria", "quantidade", "estoque_minimo", "estoque_maximo"],
        },
        funcao=_tool_adicionar_item_estoque,
    ),
    Ferramenta(
        nome="itens_estoque_baixo",
        descricao="Lista itens com estoque abaixo do minimo. Use quando o usuario perguntar quais itens precisam de reposicao ou estao em nivel critico.",
        schema={"type": "object", "properties": {}},
        funcao=_tool_itens_estoque_baixo,
    ),
    Ferramenta(
        nome="historico_movimentacoes",
        descricao="Retorna o historico de entradas e saidas do estoque. Use quando o usuario quiser ver o historico de movimentacoes de um item ou de todos.",
        schema={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID do item (opcional). Se omitido, retorna historico completo.",
                }
            },
        },
        funcao=_tool_historico_movimentacoes,
    ),
    Ferramenta(
        nome="gerar_grafico",
        descricao=(
            "Gera localmente graficos empresariais, KPIs e indicadores de eficiencia em PNG. "
            "Tipos: bar, barh, grouped_bar, stacked_bar, pie, donut, line, area, "
            "histogram, scatter, radar, heatmap, waterfall, funnel, boxplot, "
            "combo, gauge e kpi. Valores e labels sao arrays JSON."
        ),
        schema={
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "description": (
                        "Tipo: bar, barh, grouped_bar, stacked_bar, pie, donut, line, "
                        "area, histogram, scatter, radar, heatmap, waterfall, funnel, "
                        "boxplot, combo, gauge ou kpi"
                    ),
                },
                "titulo": {
                    "type": "string",
                    "description": "Titulo do grafico",
                },
                "labels": {
                    "type": "string",
                    "description": 'Array JSON de categorias/periodos (e.g. \'["Jan","Fev","Mar"]\')',
                },
                "valores": {
                    "type": "string",
                    "description": "Array JSON de dados numericos (e.g. '[100,200,150]' ou '[[100,50],[200,80]]' para multiplas series)",
                },
                "legendas": {
                    "type": "string",
                    "description": "Array JSON de legendas para multiplas series (opcional)",
                },
                "xlabel": {
                    "type": "string",
                    "description": "Label do eixo X (opcional)",
                },
                "ylabel": {
                    "type": "string",
                    "description": "Label do eixo Y (opcional)",
                },
                "cores": {
                    "type": "string",
                    "description": 'Array JSON de cores hex (opcional, e.g. \'["#3498DB","#E74C3C"]\')',
                },
                "meta": {
                    "type": "number",
                    "description": "Meta ou valor de referencia para gauge e kpi",
                },
                "unidade": {
                    "type": "string",
                    "description": "Unidade exibida, por exemplo %, R$ ou un.",
                },
                "subtitulo": {
                    "type": "string",
                    "description": "Explicacao curta abaixo do titulo",
                },
            },
            "required": ["tipo", "titulo", "labels", "valores"],
        },
        funcao=_tool_gerar_grafico,
    ),
]


def obter_schemas_openai():
    return [f.para_openai() for f in REGISTRO_FERRAMENTAS]


def obter_ferramenta(nome):
    for f in REGISTRO_FERRAMENTAS:
        if f.nome == nome:
            return f
    return None


# Tools that should retry on failure (network operations)
RETRYABLE_TOOLS = {"pesquisar_web", "navegar_web", "abrir_no_navegador"}

# Max retries for retryable tools
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds

# Circuit breaker configuration per tool
# (failure_threshold, recovery_timeout_seconds)
CIRCUIT_BREAKER_CONFIG = {
    "pesquisar_web": (5, 60),
    "pesquisar_google": (3, 120),
    "pesquisar_noticias": (5, 60),
    "navegar_web": (3, 120),
    "abrir_no_navegador": (3, 120),
}

# Tools protected by circuit breakers
CIRCUIT_PROTECTED_TOOLS = set(CIRCUIT_BREAKER_CONFIG.keys())

# Tool result cache
_TOOL_CACHE_DIR = get_settings().data_dir / "cache" / "tools"
_TOOL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache TTLs (in seconds)
CACHE_TTL = {
    "pesquisar_web": 3600,  # 1 hour
    "navegar_web": 1800,  # 30 min
    "buscar_memoria": 300,  # 5 min
    "informacoes_sistema": 60,  # 1 min
    "listar_documentos_rag": 600,  # 10 min
    "listar_arquivos": 300,  # 5 min
    "listar_agenda": 30,  # 30 sec
    "listar_clientes": 30,  # 30 sec
    "listar_fornecedores": 30,  # 30 sec
    "listar_produtos_servicos": 30,  # 30 sec
    "listar_orcamentos": 30,
    "listar_processos_prazos": 30,
    "listar_estoque": 30,  # 30 sec (dados podem mudar rapido)
    "buscar_item_estoque": 30,  # 30 sec
}

# Tools that should not be cached
NON_CACHEABLE_TOOLS = {
    "executar_codigo",
    "salvar_memoria",
    "indexar_documento",
    "remover_documento",
    "processar_arquivo",
    "abrir_no_navegador",
    "criar_compromisso_agenda",
    "marcar_lembrete_agenda",
    "cadastrar_cliente",
    "cadastrar_fornecedor",
    "cadastrar_produto_servico",
    "cadastrar_orcamento",
    "cadastrar_processo_prazo",
    "gerar_relatorio_local",
    "entrada_estoque",
    "saida_estoque",
    "adicionar_item_estoque",
    "gerar_grafico",
}


def _get_cache_key(nome: str, argumentos: dict) -> str:
    """Generate cache key from tool name and arguments."""
    key_data = f"{nome}:{json.dumps(argumentos, sort_keys=True)}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:32]


def _get_cache_path(cache_key: str) -> Path:
    """Get cache file path."""
    return _TOOL_CACHE_DIR / f"{cache_key}.json"


def _load_cached_result(cache_key: str, max_age: int) -> Any | None:
    """Load cached result if not expired."""
    cache_path = _get_cache_path(cache_key)
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, encoding="utf-8") as f:
            cached = json.load(f)

        cached_time = cached.get("timestamp", 0)
        if time.time() - cached_time > max_age:
            cache_path.unlink(missing_ok=True)
            return None

        logger.debug("Cache hit for %s", cache_key)
        return cached.get("result")
    except Exception as e:
        logger.warning("Failed to load cache for %s: %s", cache_key, e)
        return None


def _save_cached_result(cache_key: str, result: Any) -> None:
    """Save result to cache."""
    cache_path = _get_cache_path(cache_key)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "result": result}, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("Failed to save cache for %s: %s", cache_key, e)


def _validate_tool_args(ferramenta: Ferramenta, argumentos: dict) -> tuple[bool, str]:
    """Validate tool arguments against schema.

    Returns:
        (is_valid, error_message)
    """
    schema = ferramenta.schema
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    # Check required arguments
    for req in required:
        if req not in argumentos:
            return False, f"Argumento obrigatorio ausente: {req}"

    # Check for unexpected arguments
    for arg in argumentos:
        if arg not in properties:
            logger.warning("Argumento inesperado para %s: %s", ferramenta.nome, arg)

    # Basic type validation
    for arg_name, arg_value in argumentos.items():
        if arg_name in properties:
            expected_type = properties[arg_name].get("type")
            if expected_type == "string" and not isinstance(arg_value, str):
                return False, f"Argumento '{arg_name}' deve ser string"
            elif expected_type == "integer" and not isinstance(arg_value, int):
                return False, f"Argumento '{arg_name}' deve ser inteiro"
            elif expected_type == "number" and not isinstance(arg_value, (int, float)):
                return False, f"Argumento '{arg_name}' deve ser numero"
            elif expected_type == "boolean" and not isinstance(arg_value, bool):
                return False, f"Argumento '{arg_name}' deve ser booleano"

    # Path traversal check for path arguments
    for arg_name, arg_value in argumentos.items():
        if (
            isinstance(arg_value, str)
            and ".." in arg_value
            and any(kw in arg_name.lower() for kw in ["caminho", "path", "diretorio", "url"])
        ):
            return False, f"Path traversal detectado em '{arg_name}'"

    return True, ""


def _retry_with_backoff(
    func, *args, max_retries=MAX_RETRIES, base_delay=RETRY_BASE_DELAY, **kwargs
):
    """Execute function with exponential backoff retry."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Retry %d/%d for %s after %.1fs: %s",
                    attempt + 1,
                    max_retries,
                    func.__name__,
                    delay,
                    e,
                )
                time.sleep(delay)
            else:
                logger.error("All retries exhausted for %s: %s", func.__name__, e)

    raise last_error


def executar_ferramenta(
    nome: str,
    argumentos: dict,
    *,
    require_approval: bool = False,
) -> str:
    """Execute a tool with validation, retry, circuit breaker, metrics, and graceful degradation."""
    metrics = get_metrics()
    ferramenta = obter_ferramenta(nome)
    if not ferramenta:
        return f"Ferramenta '{nome}' nao encontrada."

    if require_approval and nome in SENSITIVE_TOOLS:
        request = get_tool_approval_store().request(nome, argumentos)
        return approval_message(request)

    if nome == "gerar_grafico":
        argumentos = _normalize_chart_arguments(argumentos)

    # Validate arguments
    is_valid, error_msg = _validate_tool_args(ferramenta, argumentos)
    if not is_valid:
        return f"Erro de validacao em '{nome}': {error_msg}"

    # Check circuit breaker before network tools
    if nome in CIRCUIT_PROTECTED_TOOLS:
        cb_threshold, cb_timeout = CIRCUIT_BREAKER_CONFIG[nome]
        cb = get_circuit_breaker(
            f"tool:{nome}",
            failure_threshold=cb_threshold,
            recovery_timeout=cb_timeout,
        )
        if not cb.allow_request():
            return (
                f"Servico '{nome}' indisponivel (circuit breaker aberto). "
                f"Tente novamente em {cb_timeout}s."
            )

    metrics.inc(MetricNames.TOOL_CALLS_TOTAL, tool=nome)

    try:
        with metrics.timer(MetricNames.TOOL_DURATION_SECONDS, tool=nome):
            if nome in RETRYABLE_TOOLS:
                resultado = _retry_with_backoff(ferramenta.funcao, **argumentos)
            else:
                resultado = ferramenta.funcao(**argumentos)
        return resultado
    except CircuitBreakerOpenError as e:
        logger.warning("Circuit breaker open for %s: %s", nome, e)
        return f"Servico '{nome}' indisponivel temporariamente. Tente novamente em alguns segundos."
    except Exception as e:
        metrics.inc(MetricNames.TOOL_ERRORS_TOTAL, tool=nome)
        logger.error("Erro ao executar '%s': %s", nome, e, exc_info=True)
        return f"Erro ao executar '{nome}': {type(e).__name__}: {e}. Tente novamente ou reformule a solicitacao."
