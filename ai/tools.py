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

logger = logging.getLogger(__name__)


class Ferramenta:
    def __init__(self, nome, descricao, schema, funcao):
        self.nome = nome
        self.descricao = descricao
        self.schema = schema
        self.funcao = funcao

    def para_ollama(self):
        return {
            "type": "function",
            "function": {
                "name": self.nome,
                "description": self.descricao,
                "parameters": self.schema,
            },
        }

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
    from ai.rag import get_rag_service
    from processors import processar_arquivo

    path = _validate_path(caminho)
    texto = processar_arquivo(str(path), base_dir=path.parent)
    nome = path.name
    service = get_rag_service()
    n_chunks = service.index_document(texto, nome)
    return f"Documento '{nome}' indexado: {n_chunks} chunks criados."


def _tool_navegar_web(url: str) -> str:
    from ai.browser import navegar_web

    return navegar_web(url)


def _tool_listar_documentos_rag() -> str:
    from ai.rag import get_rag_service

    service = get_rag_service()
    return service.list_documents()


def _tool_remover_documento(nome_doc: str) -> str:
    from ai.rag import get_rag_service

    service = get_rag_service()
    return service.remove_document(nome_doc)


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
    """Abre URL no navegador do sistema."""
    import os
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            browsers = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]

            opened = False
            for browser in browsers:
                if os.path.exists(browser):
                    subprocess.Popen([browser, target_url])
                    opened = True
                    break

            if not opened:
                os.startfile(target_url)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target_url])
        else:
            subprocess.Popen(["xdg-open", target_url])
        return f"Abrindo {target_url} no navegador..."
    except Exception as e:
        return f"Erro ao abrir navegador: {e}"


# ── Estoque tool functions ────────────────────────────────────


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
                f"{item.quantidade} un. (min:{item.estoque_min} max:{item.estoque_max})\n"
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
        status = "CRITICO" if item.precisa_repor else "OK"
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


def _tool_gerar_grafico(
    tipo: str,
    titulo: str,
    labels: str,
    valores: str,
    legendas: str = "",
    xlabel: str = "",
    ylabel: str = "",
    cores: str = "",
) -> str:
    """Gera um grafico com matplotlib e salva como PNG."""
    import hashlib
    import json
    from pathlib import Path

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        labels_list = json.loads(labels)
        valores_data = json.loads(valores)
    except (json.JSONDecodeError, TypeError) as e:
        return f"Erro ao processar dados: JSON invalido - {e}"

    legendas_list = json.loads(legendas) if legendas else []
    cores_list = json.loads(cores) if cores else []

    chart_dir = Path(__file__).parent.parent / "cache" / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    filename = hashlib.md5(f"{tipo}{titulo}{labels}{valores}".encode()).hexdigest()[:12]
    filepath = chart_dir / f"{filename}.png"

    # Estilo moderno e limpo
    plt.style.use(
        "seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default"
    )

    fig, ax = plt.subplots(figsize=(9, 5.5))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    # Paleta de cores moderna (inspirada em Tailwind/Design Systems)
    default_colors = [
        "#3B82F6",
        "#EF4444",
        "#22C55E",
        "#F59E0B",
        "#8B5CF6",
        "#06B6D4",
        "#F97316",
        "#EC4899",
        "#14B8A6",
        "#84CC16",
    ]

    # Configurações comuns de fonte
    title_font = {"fontsize": 16, "fontweight": "600", "color": "#111827", "pad": 16}
    label_font = {"fontsize": 11, "color": "#374151"}

    def _apply_style():
        """Aplica estilo comum aos eixos."""
        ax.set_title(titulo, **title_font)
        if xlabel:
            ax.set_xlabel(xlabel, **label_font)
        if ylabel:
            ax.set_ylabel(ylabel, **label_font)
        ax.tick_params(axis="both", labelsize=10, colors="#6B7280")
        # Grid suave
        ax.grid(True, axis="y", color="#E5E7EB", linewidth=0.8, linestyle="-")
        ax.grid(False, axis="x")
        # Remove bordas superiores/direitas
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#E5E7EB")
        ax.spines["bottom"].set_color("#E5E7EB")
        if legendas_list:
            ax.legend(frameon=False, fontsize=10, loc="upper right")

    if tipo == "bar":
        x_pos = range(len(labels_list))
        if isinstance(valores_data[0], list):  # Múltiplas séries
            n_series = len(valores_data)
            width = 0.7 / n_series
            for i, serie in enumerate(valores_data):
                cor = (
                    cores_list[i]
                    if i < len(cores_list)
                    else default_colors[i % len(default_colors)]
                )
                nome = legendas_list[i] if i < len(legendas_list) else f"Série {i + 1}"
                bars = ax.bar(
                    [xi + i * width for xi in x_pos],
                    serie,
                    width,
                    label=nome,
                    color=cor,
                    edgecolor="none",
                    zorder=3,
                )
                # Arredondar topo das barras
                for bar in bars:
                    bar.set_capstyle("round")
        else:
            cor = cores_list[0] if cores_list else default_colors[0]
            bars = ax.bar(
                labels_list, valores_data, color=cor, edgecolor="none", width=0.6, zorder=3
            )
            for bar in bars:
                bar.set_capstyle("round")

    elif tipo == "pie":
        colors_pie = cores_list if cores_list else default_colors[: len(labels_list)]
        wedges, texts, autotexts = ax.pie(
            valores_data,
            labels=labels_list,
            colors=colors_pie,
            autopct="%1.1f%%",
            startangle=90,
            textprops={"fontsize": 11, "color": "#111827"},
            pctdistance=0.75,
            wedgeprops={"edgecolor": "#FAFAFA", "linewidth": 2, "antialiased": True},
        )
        for autotext in autotexts:
            autotext.set_color("white")
            autotext.set_fontweight("600")
            autotext.set_fontsize(10)
        ax.axis("equal")

    elif tipo == "line":
        if isinstance(valores_data[0], list):
            for i, serie in enumerate(valores_data):
                cor = (
                    cores_list[i]
                    if i < len(cores_list)
                    else default_colors[i % len(default_colors)]
                )
                nome = legendas_list[i] if i < len(legendas_list) else f"Série {i + 1}"
                ax.plot(
                    labels_list,
                    serie,
                    marker="o",
                    markersize=6,
                    markerfacecolor="white",
                    markeredgewidth=2,
                    color=cor,
                    label=nome,
                    linewidth=2.5,
                    zorder=3,
                )
        else:
            cor = cores_list[0] if cores_list else default_colors[0]
            ax.plot(
                labels_list,
                valores_data,
                marker="o",
                markersize=6,
                markerfacecolor="white",
                markeredgewidth=2,
                color=cor,
                linewidth=2.5,
                zorder=3,
            )
            ax.fill_between(labels_list, valores_data, alpha=0.08, color=cor)

    elif tipo == "area":
        if isinstance(valores_data[0], list):
            for i, serie in enumerate(valores_data):
                cor = (
                    cores_list[i]
                    if i < len(cores_list)
                    else default_colors[i % len(default_colors)]
                )
                nome = legendas_list[i] if i < len(legendas_list) else f"Série {i + 1}"
                ax.fill_between(labels_list, serie, alpha=0.25, color=cor, label=nome)
                ax.plot(labels_list, serie, color=cor, linewidth=1.5)
        else:
            cor = cores_list[0] if cores_list else default_colors[0]
            ax.fill_between(labels_list, valores_data, alpha=0.3, color=cor)
            ax.plot(labels_list, valores_data, color=cor, linewidth=1.5)

    elif tipo == "histogram":
        cor = cores_list[0] if cores_list else default_colors[0]
        ax.hist(
            valores_data,
            bins=max(5, len(labels_list) // 2),
            color=cor,
            edgecolor="#FAFAFA",
            linewidth=1.5,
            alpha=0.85,
            zorder=3,
        )

    elif tipo == "scatter":
        x_data = (
            valores_data if not isinstance(valores_data[0], list) else [v[0] for v in valores_data]
        )
        y_data = labels_list if not isinstance(labels_list[0], (list, str)) else valores_data
        if isinstance(valores_data[0], list) and len(valores_data[0]) == 2:
            x_data = [v[0] for v in valores_data]
            y_data = [v[1] for v in valores_data]
        cor = cores_list[0] if cores_list else default_colors[0]
        ax.scatter(
            x_data, y_data, c=cor, s=90, alpha=0.7, edgecolors="white", linewidths=1.5, zorder=3
        )

    else:
        plt.close(fig)
        return f"Tipo de grafico '{tipo}' nao suportado. Tipos validos: bar, pie, line, area, histogram, scatter"

    _apply_style()
    plt.tight_layout()
    fig.savefig(
        str(filepath),
        dpi=180,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        transparent=False,
    )
    plt.close(fig)

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
            "Gera um grafico visual (PNG) e exibe direto no chat. "
            "Use quando o usuario pedir graficos, chart,Pizza, barras, linhas, area, histograma, ou dispersao. "
            "Tipos: bar, pie, line, area, histogram, scatter. "
            "Valores e labels sao arrays JSON."
        ),
        schema={
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "description": "Tipo do grafico: bar, pie, line, area, histogram, scatter",
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
            },
            "required": ["tipo", "titulo", "labels", "valores"],
        },
        funcao=_tool_gerar_grafico,
    ),
]


def obter_schemas_ollama():
    return [f.para_ollama() for f in REGISTRO_FERRAMENTAS]


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
_TOOL_CACHE_DIR = Path(__file__).parent.parent / "cache" / "tools"
_TOOL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache TTLs (in seconds)
CACHE_TTL = {
    "pesquisar_web": 3600,  # 1 hour
    "navegar_web": 1800,  # 30 min
    "buscar_memoria": 300,  # 5 min
    "informacoes_sistema": 60,  # 1 min
    "listar_documentos_rag": 600,  # 10 min
    "listar_arquivos": 300,  # 5 min
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


def executar_ferramenta(nome: str, argumentos: dict) -> str:
    """Execute a tool with validation, retry, circuit breaker, metrics, and graceful degradation."""
    metrics = get_metrics()
    ferramenta = obter_ferramenta(nome)
    if not ferramenta:
        return f"Ferramenta '{nome}' nao encontrada."

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
