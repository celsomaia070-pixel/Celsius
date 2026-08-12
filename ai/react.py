"""ReAct loop using native OpenAI tool calling via llama-cpp-python."""

import gc
import json
import logging
import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ai.context_budget import get_budget
from ai.tools import (
    REGISTRO_FERRAMENTAS,
    _normalize_chart_arguments,
    executar_ferramenta,
)
from core.llama_cpp import get_multi_model_manager
from core.settings import get_settings
from core.telemetry import trace_span
from core.tool_approval import APPROVAL_REQUIRED_PREFIX

logger = logging.getLogger(__name__)

MAX_ITERACOES = 5
INTERNAL_CHAT_MARKERS = (
    "<|im_start|>",
    "<|im_end|>",
    "<|start_header_id|>",
    "<|end_header_id|>",
    "<|eot_id|>",
)
REASONING_OPEN_TAGS = ("<think>", "<analysis>")
REASONING_CLOSE_TAGS = ("</think>", "</analysis>")
CHART_KEYWORDS = (
    "grafico",
    "gráfico",
    "chart",
    "barras",
    "horizontal",
    "agrupado",
    "empilhado",
    "pizza",
    "pie",
    "rosca",
    "donut",
    "linha",
    "line",
    "area",
    "histograma",
    "dispersao",
    "dispersão",
    "scatter",
    "radar",
    "mapa de calor",
    "heatmap",
    "cascata",
    "waterfall",
    "funil",
    "funnel",
    "boxplot",
    "combinado",
    "combo",
    "indicador",
    "kpi",
    "eficiencia",
    "eficiência",
    "desempenho",
    "produtividade",
    "atingimento",
    "plotar",
    "plot",
    "visualizar",
)


def _sanitize_internal_markers(text: str) -> str:
    """Remove chat-template markers from user-controlled text."""
    cleaned = str(text or "")
    for marker in INTERNAL_CHAT_MARKERS:
        cleaned = cleaned.replace(marker, " ")
    return cleaned.strip()


def _first_internal_marker_index(text: str) -> int:
    positions = [text.find(marker) for marker in INTERNAL_CHAT_MARKERS if marker in text]
    return min(positions) if positions else -1


def _is_chart_request(question: str) -> bool:
    lowered = str(question or "").lower()
    return any(keyword in lowered for keyword in CHART_KEYWORDS)


def _extract_textual_tool_call(text: str) -> tuple[str, dict] | None:
    """Recover tool calls emitted as visible JSON by local chat templates."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", str(text or "")):
        try:
            payload, _end = decoder.raw_decode(text[match.start() :])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue

        name = payload.get("name")
        arguments = payload.get("arguments")
        function = payload.get("function")
        if isinstance(function, dict):
            name = function.get("name", name)
            arguments = function.get("arguments", arguments)
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                continue
        if isinstance(name, str) and isinstance(arguments, dict):
            return name, arguments
    return None


def _chart_response_from_tool_result(result: str, title: str) -> str | None:
    if not isinstance(result, str) or "Arquivo:" not in result:
        return None
    path = result.partition("Arquivo:")[2].splitlines()[0].strip()
    if not _is_generated_chart_path(path):
        return None
    markdown = next(
        (
            line.partition("Exiba-o com:")[2].strip()
            for line in result.splitlines()
            if "Exiba-o com:" in line
        ),
        "",
    )
    if not markdown:
        markdown = f"![Grafico - {title}]({path})"
    return f"Grafico **{title}** gerado com sucesso.\n\n{markdown}"


def _execute_textual_chart_call(response: str) -> str | None:
    call = _extract_textual_tool_call(response)
    if call is None or call[0] != "gerar_grafico":
        return None
    arguments = _normalize_chart_arguments(call[1])
    result = executar_ferramenta("gerar_grafico", arguments)
    return _chart_response_from_tool_result(
        result,
        str(arguments.get("titulo") or "Grafico"),
    )


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _try_direct_business_report(question: str) -> str | None:
    """Generate explicitly requested local reports without relying on model tool choice."""
    normalized = _normalized_text(question)
    report_actions = ("gere", "gerar", "crie", "criar", "faca", "produza", "emita")
    if "relatorio" not in normalized or not any(action in normalized for action in report_actions):
        return None

    sources = (
        (("estoque", "inventario"), "Estoque", "Relatorio de estoque"),
        (("cliente", "clientes"), "Clientes", "Relatorio de clientes"),
        (("fornecedor", "fornecedores"), "Fornecedores", "Relatorio de fornecedores"),
        (("orcamento", "orcamentos", "venda", "vendas"), "Orcamentos", "Relatorio comercial"),
        (
            ("processo", "processos", "prazo", "prazos"),
            "Processos e prazos",
            "Relatorio de processos e prazos",
        ),
    )
    source = "Executivo"
    title = "Relatorio executivo"
    for keywords, candidate_source, candidate_title in sources:
        if any(keyword in normalized for keyword in keywords):
            source = candidate_source
            title = candidate_title
            break

    output_format = "docx" if "docx" in normalized or "word" in normalized else "pdf"
    if "markdown" in normalized or re.search(r"\bmd\b", normalized):
        output_format = "md"
    result = executar_ferramenta(
        "gerar_relatorio_local",
        {
            "titulo": title,
            "tipo": source if source != "Processos e prazos" else "Operacional",
            "fonte": source,
            "formato": output_format,
            "periodo": "Atual",
        },
    )
    if source == "Estoque":
        return f"{result}\n\n{_inventory_report_summary()}"
    return result


def _inventory_report_summary() -> str:
    """Show the local records used by a stock report so the model cannot invent them."""
    try:
        from core.inventory import get_inventory_service

        items = get_inventory_service().get_all_items()
    except Exception as exc:
        logger.error("Falha ao resumir estoque local: %s", exc, exc_info=True)
        return "Nao foi possivel consultar os itens do estoque local."
    if not items:
        return (
            "**Dados confirmados no inventory.json**\n\n"
            "O arquivo esta acessivel, mas nao possui itens cadastrados."
        )

    total_units = sum(item.quantidade for item in items)
    critical = sum(1 for item in items if item.precisa_repor)
    lines = [
        "**Dados confirmados no inventory.json**",
        "",
        f"- Itens cadastrados: {len(items)}",
        f"- Unidades registradas: {total_units}",
        f"- Itens que exigem reposicao: {critical}",
        "",
        "| Item | Categoria | Atual | Minimo | Maximo | Status |",
        "|---|---|---:|---:|---:|---|",
    ]
    for item in items:
        status = "Repor" if item.precisa_repor else "Regular"
        lines.append(
            f"| {item.nome} | {item.categoria} | {item.quantidade} | "
            f"{item.estoque_min} | {item.estoque_max} | {status} |"
        )
    return "\n".join(lines)


def _chart_type_from_question(question: str) -> str:
    lowered = _normalized_text(question).replace("-", " ")
    mappings = (
        (("velocimetro", "gauge"), "gauge"),
        (("indicador", "kpi"), "kpi"),
        (("mapa de calor", "heatmap"), "heatmap"),
        (("barra horizontal", "barras horizontais", "barh"), "barh"),
        (("empilhado", "empilhadas", "stacked"), "stacked_bar"),
        (("agrupado", "agrupadas", "grouped"), "grouped_bar"),
        (("rosca", "donut"), "donut"),
        (("pizza", "pie"), "pie"),
        (("radar",), "radar"),
        (("cascata", "waterfall"), "waterfall"),
        (("funil", "funnel"), "funnel"),
        (("boxplot", "grafico de caixa"), "boxplot"),
        (("combinado", "combo"), "combo"),
        (("histograma", "histogram"), "histogram"),
        (("dispersao", "scatter"), "scatter"),
        (("linha", "line"), "line"),
        (("area",), "area"),
    )
    for keywords, chart_type in mappings:
        if any(keyword in lowered for keyword in keywords):
            return chart_type
    if any(
        keyword in lowered
        for keyword in ("eficiencia", "atingimento", "produtividade", "desempenho")
    ):
        return "gauge"
    return "bar"


def _is_generated_chart_path(path_value: str) -> bool:
    if not path_value or path_value.startswith(("http://", "https://", "data:")):
        return False
    try:
        path = Path(path_value).expanduser().resolve()
        chart_root = (get_settings().data_dir / "cache" / "charts").resolve()
        path.relative_to(chart_root)
        return path.is_file() and path.suffix.lower() == ".png" and path.stat().st_size > 0
    except (OSError, ValueError):
        return False


def _response_has_generated_chart(response: str) -> bool:
    for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", str(response or "")):
        if _is_generated_chart_path(match.group(1).strip()):
            return True
    return False


def _inventory_chart_arguments(question: str, items: list) -> tuple[dict, str]:
    chart_type = _chart_type_from_question(question)
    lowered = _normalized_text(question)
    efficiency_request = any(
        keyword in lowered
        for keyword in ("eficiencia", "desempenho", "produtividade", "atingimento", "kpi")
    )
    if efficiency_request or chart_type in {"gauge", "kpi"}:
        healthy = sum(1 for item in items if not item.precisa_repor)
        efficiency = round(healthy / len(items) * 100, 1)
        arguments = {
            "tipo": chart_type if chart_type in {"gauge", "kpi"} else "gauge",
            "titulo": "Eficiencia de disponibilidade do estoque",
            "labels": ["Itens acima do estoque minimo"],
            "valores": [efficiency],
            "meta": 90,
            "unidade": "%",
            "subtitulo": f"{healthy} de {len(items)} itens sem necessidade de reposicao",
        }
        summary = (
            f"**Indicador:** {efficiency:.1f}% dos itens estao acima do estoque minimo "
            f"({healthy} de {len(items)}). Meta de referencia: 90%."
        )
        return arguments, summary

    labels = [str(item.nome) for item in items]
    quantities = [item.quantidade for item in items]
    minimums = [item.estoque_min for item in items]
    maximums = [item.estoque_max for item in items]
    arguments = {
        "tipo": chart_type,
        "titulo": "Visao do estoque",
        "labels": labels,
        "valores": quantities,
        "ylabel": "Quantidade",
    }
    if chart_type in {"grouped_bar", "stacked_bar", "combo", "radar", "area", "line"}:
        arguments["valores"] = [quantities, minimums, maximums]
        arguments["legendas"] = ["Atual", "Minimo", "Maximo"]
    elif chart_type == "scatter":
        arguments["valores"] = [[item.estoque_min, item.quantidade] for item in items]
        arguments["xlabel"] = "Estoque minimo"
        arguments["ylabel"] = "Quantidade atual"
    elif chart_type == "heatmap":
        arguments["valores"] = [
            [item.quantidade, item.estoque_min, item.estoque_max] for item in items
        ]
        arguments["legendas"] = ["Atual", "Minimo", "Maximo"]
    elif chart_type == "boxplot":
        by_category: dict[str, list[int]] = {}
        for item in items:
            by_category.setdefault(str(item.categoria), []).append(item.quantidade)
        arguments["labels"] = list(by_category)
        arguments["valores"] = list(by_category.values())
    summary = f"Grafico criado com {len(items)} itens cadastrados no estoque."
    return arguments, summary


def _try_direct_business_chart(question: str) -> str | None:
    lowered = _normalized_text(question)
    if not any(keyword in lowered for keyword in ("estoque", "inventario", "produto", "item")):
        return None
    try:
        from core.inventory import get_inventory_service

        items = get_inventory_service().get_all_items()
        if not items:
            return "Nao ha itens cadastrados para gerar o grafico solicitado."
        arguments, summary = _inventory_chart_arguments(question, items)
        normalized = _normalize_chart_arguments(arguments)
        result = executar_ferramenta("gerar_grafico", normalized)
        chart_response = _chart_response_from_tool_result(
            result,
            str(normalized.get("titulo") or "Grafico"),
        )
        if chart_response:
            logger.info(
                "Grafico empresarial gerado diretamente: tipo=%s itens=%s",
                normalized.get("tipo"),
                len(items),
            )
            return f"{chart_response}\n\n{summary}"
        logger.warning("Falha no grafico empresarial direto: %s", result)
    except Exception as exc:
        logger.error("Falha no grafico empresarial direto: %s", exc, exc_info=True)
    return None


def _parse_numeric_cell(value: str) -> float | None:
    match = re.search(r"-?\d[\d.,]*", str(value or "").replace(" ", ""))
    if not match:
        return None
    cleaned = match.group(0)
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _chart_arguments_from_markdown_table(question: str, text: str) -> dict | None:
    table_lines = [line.strip() for line in str(text or "").splitlines() if "|" in line]
    if len(table_lines) < 3:
        return None
    rows = [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in table_lines
        if not re.fullmatch(r"\|?[\s:|-]+\|?", line)
    ]
    if len(rows) < 3:
        return None

    headers = [_normalized_text(header) for header in rows[0]]
    data_rows = [row for row in rows[1:] if len(row) == len(headers)]
    if len(data_rows) < 2:
        return None

    label_keywords = ("nome", "item", "produto", "categoria", "periodo", "mes", "data", "cliente")
    label_index = next(
        (
            index
            for index, header in enumerate(headers)
            if any(keyword in header for keyword in label_keywords)
        ),
        0,
    )
    excluded_headers = {"id", "codigo", "status"}
    numeric_columns = []
    for index, header in enumerate(headers):
        if index == label_index or header in excluded_headers:
            continue
        parsed = [_parse_numeric_cell(row[index]) for row in data_rows]
        if all(value is not None for value in parsed):
            numeric_columns.append((index, header, parsed))
    if not numeric_columns:
        return None

    normalized_question = _normalized_text(question)
    requested_column = next(
        (column for column in numeric_columns if column[1] and column[1] in normalized_question),
        None,
    )
    chart_type = _chart_type_from_question(question)
    multi_series_types = {"grouped_bar", "stacked_bar", "line", "area", "radar", "heatmap", "combo"}
    selected_columns = (
        numeric_columns
        if chart_type in multi_series_types and len(numeric_columns) > 1
        else [requested_column or numeric_columns[0]]
    )
    labels = [row[label_index] for row in data_rows]
    values = [column[2] for column in selected_columns]
    if len(values) == 1:
        values = values[0]
    return {
        "tipo": chart_type,
        "titulo": "Visualizacao dos dados",
        "labels": labels,
        "valores": values,
        "legendas": [column[1].title() for column in selected_columns],
    }


def _chart_arguments_from_labeled_numbers(question: str) -> dict | None:
    pairs = re.findall(
        r"([A-Za-zÀ-ÿ][^,;:\n=]{0,35})\s*[:=]\s*"
        r"(?:R\$\s*)?(-?\d+(?:[.,]\d+)?)\s*%?",
        str(question or ""),
    )
    if len(pairs) < 2:
        return None
    labels = [label.strip(" .-") for label, _value in pairs]
    values = [_parse_numeric_cell(value) for _label, value in pairs]
    if any(value is None for value in values):
        return None
    return {
        "tipo": _chart_type_from_question(question),
        "titulo": "Visualizacao dos dados informados",
        "labels": labels,
        "valores": values,
    }


def _try_chart_from_text(question: str, text: str) -> str | None:
    arguments = _chart_arguments_from_markdown_table(question, text)
    if arguments is None:
        arguments = _chart_arguments_from_labeled_numbers(question)
    if arguments is None:
        return None
    normalized = _normalize_chart_arguments(arguments)
    result = executar_ferramenta("gerar_grafico", normalized)
    chart_response = _chart_response_from_tool_result(
        result,
        str(normalized.get("titulo") or "Grafico"),
    )
    if chart_response:
        logger.info("Grafico gerado a partir de dados textuais: tipo=%s", normalized.get("tipo"))
    return chart_response


def _is_reasoning_model(model_id: str) -> bool:
    normalized = (model_id or "").lower()
    return "deepseek-r1" in normalized or "reasoning" in normalized


def _strip_reasoning_blocks(text: str) -> str:
    """Remove model reasoning while preserving the user-facing answer."""
    cleaned = str(text or "")
    cleaned = re.sub(
        r"(?is)<(?:think|analysis)>.*?</(?:think|analysis)>",
        "",
        cleaned,
    )

    lowered = cleaned.lower()
    orphan_closes = [(lowered.rfind(tag), tag) for tag in REASONING_CLOSE_TAGS if tag in lowered]
    if orphan_closes:
        marker_idx, marker = max(orphan_closes)
        cleaned = cleaned[marker_idx + len(marker) :]

    lowered = cleaned.lower()
    open_positions = [lowered.find(tag) for tag in REASONING_OPEN_TAGS if tag in lowered]
    if open_positions:
        cleaned = cleaned[: min(open_positions)]
    return cleaned.strip()


class _ReasoningStreamFilter:
    """Hold private reasoning tokens and emit only the final answer."""

    def __init__(self, assume_reasoning: bool = False):
        self._state = "hidden" if assume_reasoning else "undecided"
        self._buffer = ""

    def feed(self, content: str) -> str:
        if not content:
            return ""
        if self._state == "visible":
            return content

        self._buffer += content
        if self._state == "undecided":
            candidate = self._buffer.lstrip().lower()
            if not candidate:
                return ""
            if any(candidate.startswith(tag) for tag in REASONING_OPEN_TAGS):
                self._state = "hidden"
            elif any(tag.startswith(candidate) for tag in REASONING_OPEN_TAGS):
                return ""
            else:
                self._state = "visible"
                visible = self._buffer
                self._buffer = ""
                return visible

        lowered = self._buffer.lower()
        closes = [(lowered.find(tag), tag) for tag in REASONING_CLOSE_TAGS if tag in lowered]
        if not closes:
            return ""

        marker_idx, marker = min(closes)
        visible = self._buffer[marker_idx + len(marker) :].lstrip()
        self._buffer = ""
        self._state = "visible"
        return visible

    def finish(self) -> str:
        if self._state == "undecided":
            visible = self._buffer
            self._buffer = ""
            self._state = "visible"
            return visible
        self._buffer = ""
        return ""


def _agenda_prompt_context() -> str:
    try:
        from core.agenda import get_agenda_service

        return get_agenda_service().prompt_context()
    except Exception as exc:
        logger.debug("Agenda context unavailable (non-blocking): %s", exc)
        return ""


SYSTEM_PROMPT_REACT = (
    "Voce e {assistant_name}, {assistant_profile}. Data: {data_hora}.\n"
    "Sua identidade fixa e Celsius. Nao mude seu nome, produto ou natureza.\n"
    "Responda SEMPRE em portugues do Brasil.\n\n"
    "{customer_context}\n\n"
    "## Regras Obrigatorias\n"
    "- NUNCA invente informacoes privadas, dados da empresa, estoque, clientes, fornecedores ou memorias.\n"
    "- Para perguntas sobre dados internos nao registrados, diga: 'Nao tenho essa informacao registrada.'\n"
    "- Para conhecimento geral, estudos, redacao, tecnologia, cultura, explicacoes e temas fora do negocio, responda normalmente com seu conhecimento geral.\n"
    "- O perfil da empresa orienta exemplos e prioridades, mas NAO limita os assuntos que voce pode ajudar.\n"
    "- Se houver memorias no contexto, USE-AS. Nao diga que nao sabe.\n"
    "- Use o historico recente da conversa para entender referencias, continuacoes e perguntas como 'o que eu disse?'.\n"
    "- Nao comence se apresentando. Va direto ao ponto.\n"
    "- Nao anuncie ferramentas que vai chamar. Apenas chame e mostre o resultado.\n"
    "- Nao explique o que esta fazendo. O resultado final deve ser direto e util.\n"
    "- Nao exponha raciocinio interno, cadeia de pensamento, tags <think> ou etapas privadas de analise.\n"
    "- NAO use ferramentas para perguntas que voce ja sabe responder.\n\n"
    "## Agenda (ACESSO LOCAL VIA FERRAMENTAS)\n"
    "Voce TEM acesso aos compromissos locais do usuario via ferramentas de agenda.\n"
    "Para perguntas sobre compromissos, consultas, visitas, prazos e lembretes, use listar_agenda.\n"
    "Para criar um compromisso ou lembrete, use criar_compromisso_agenda.\n"
    "Nunca invente compromissos que nao estejam registrados.\n\n"
    "## Clientes e Fornecedores (ACESSO LOCAL VIA FERRAMENTAS)\n"
    "Consulte clientes e fornecedores pelas ferramentas locais antes de responder sobre cadastros.\n"
    "Use listar_clientes e listar_fornecedores para consultas.\n"
    "Use cadastrar_cliente ou cadastrar_fornecedor somente quando o usuario pedir o cadastro.\n"
    "Nunca invente pessoas, empresas, documentos, contatos ou condicoes comerciais.\n\n"
    "## Produtos e Servicos (CATALOGO COMERCIAL LOCAL)\n"
    "Para consultar SKU, preco, custo, margem, unidade ou status comercial, use listar_produtos_servicos.\n"
    "Para cadastrar no catalogo, use cadastrar_produto_servico somente quando solicitado.\n"
    "Catalogo comercial e estoque sao diferentes: catalogo define a oferta; estoque informa saldo fisico.\n\n"
    "## Orcamentos, Relatorios, Processos e Prazos\n"
    "Consulte propostas reais com listar_orcamentos e crie uma somente quando solicitado com cadastrar_orcamento.\n"
    "Consulte vencimentos reais com listar_processos_prazos; nunca invente processos, clientes ou datas.\n"
    "Cadastre processos e prazos somente quando o usuario pedir explicitamente.\n"
    "Quando o usuario pedir um arquivo de relatorio empresarial, use gerar_relatorio_local. "
    "Os dados e arquivos permanecem neste computador.\n\n"
    "## Estoque (SEMPRE ACESSIVEL VIA FERRAMENTAS - NUNCA INVENTE DADOS)\n"
    "Voce TEM acesso total ao estoque do usuario via ferramentas.\n"
    "Para QUALQUER pergunta sobre estoque/itens/produtos/componentes, use a ferramenta adequada.\n"
    "NUNCA invente nomes de itens, quantidades, categorias ou qualquer dado de estoque.\n"
    "Use APENAS os dados reais retornados pelas ferramentas de estoque.\n"
    "TODOS os itens retornados pelas ferramentas ESTAO no estoque do usuario.\n"
    "Exemplos de perguntas que DEVEM usar ferramentas de estoque:\n"
    "- 'quais itens tenho / liste os componentes' -> listar_estoque\n"
    "- 'quanto de X tenho' -> buscar_item_estoque\n"
    "- 'entrada de X unidades' -> buscar_item_estoque + entrada_estoque\n"
    "- 'saida de X unidades' -> buscar_item_estoque + saida_estoque\n"
    "- 'cadastrar item novo' -> adicionar_item_estoque\n"
    "- 'itens com estoque baixo' -> itens_estoque_baixo\n"
    "- 'historico de movimentacoes' -> historico_movimentacoes\n"
    "- 'gerar relatorio' -> listar_estoque (e formate como relatorio)\n"
    "Para entrada/saida: primeiro busque o item para obter o ID, depois execute a operacao.\n"
    "Itens com status 'CRITICO' ou 'estoque baixo' estao no estoque, precisam de reposicao.\n"
    "NUNCA diga que um item 'nao esta no estoque' se ele foi retornado pela ferramenta.\n\n"
    "### FORMATO DE RESPOSTA PARA ESTOQUE:\n"
    "Ao listar itens do estoque:\n"
    "- VA DIRETO AO PONTO. Nao explique que vai chamar a ferramenta, nao peca desculpas, nao de recomendacoes.\n"
    "- Apresente os itens em formato de tabela ou lista limpa.\n"
    "- Exemplo correto:\n"
    "  Item | Quantidade | Categoria\n"
    "  Parafuso M8 | 150 | Ferragens\n"
    "  Porca sextavada | 80 | Ferragens\n"
    "- Nao adicione observacoes como 'verifique a lista' ou 'recomendo'. Os dados falam por si.\n\n"
    "## Graficos e Visualizacao de Dados\n"
    "Quando o usuario pedir um grafico, KPI, indicador, visualizacao, ou plotar dados, "
    "CHAME a ferramenta gerar_grafico. NUNCA apenas descreva os dados.\n"
    "SEMPRE gere o grafico. NUNCA sugira Excel/Google Sheets/Canva.\n"
    "NUNCA invente URL, imagem remota ou caminho de arquivo para representar um grafico.\n"
    "Indicadores de eficiencia devem informar valor, unidade, criterio e meta usada.\n"
    "Mesmo que os dados ja estejam no contexto, CHAME gerar_grafico para criar a imagem visual.\n"
    "Apos chamar a ferramenta, inclua o resultado na resposta:\n"
    "![Grafico - Titulo](caminho_retornado_pela_ferramenta)\n\n"
    "## Web, YouTube e Google (SEMPRE CHAME A FERRAMENTA)\n"
    "Para QUALQUER pedido de pesquisa, abrir site, YouTube ou Google, voce DEVE chamar uma ferramenta.\n"
    "NUNCA diga que nao pode fazer isso. NUNCA sugira que o usuario faca sozinho.\n"
    "APOS CHAMAR A FERRAMENTA, apenas confirme brevemente (ex: 'Abrindo YouTube.'). NAO faca perguntas adicionais.\n"
    "NUNCA pergunte 'o que voce gostaria de fazer' ou 'deseja ver mais' apos abrir um site.\n\n"
    "Regras:\n"
    "- 'abra/pesquise/abrir [algo] no YouTube' -> abrir_no_navegador(url='youtube [algo]')\n"
    "- 'abra/pesquise/abrir [algo] no Google' -> abrir_no_navegador(url='google [algo]')\n"
    "- 'abra/pesquise/abrir [algo]' (sem plataforma) -> abrir_no_navegador(url='[algo]')\n"
    "- 'pesquise na web/noticias sobre [algo]' -> pesquisar_web(query='[algo]')\n"
    "- 'ultimas noticias sobre [algo]' -> pesquisar_noticias(query='ultimas noticias sobre [algo]')\n"
    "- 'abra o site [url]' -> abrir_no_navegador(url='[url]')\n\n"
    "## Documentos Anexados\n"
    "Sempre que houver um documento anexado, o conteudo ja esta disponivel no contexto.\n"
    "NAO chame processar_arquivo. Analise os dados e responda diretamente.\n"
    "Memorias do usuario nunca substituem o conteudo de um documento anexado.\n"
    "Se aparecer EXTRACAO_INSUFICIENTE, informe que a extracao convencional e o OCR local "
    "nao recuperaram texto suficiente. Solicite uma versao mais nitida ou pesquisavel e "
    "nao produza um relatorio como se tivesse lido o arquivo.\n"
    "IMPORTANTE: se o usuario pedir um GRAFICO, CHAME gerar_grafico usando os dados do contexto.\n\n"
    "{response_style_context}\n"
    "### REGRA FINAL - QUERIES DE DADOS\n"
    "Para consultas simples de dados (estoque, agenda, fornecedores, etc.):\n"
    "responda APENAS com os dados em tabela ou lista. Sem contexto, sem explicacao,\n"
    "sem recomendacao, sem perguntas. A resposta deve ser APENAS os dados.\n\n"
)


class PassoReact:
    def __init__(
        self, tipo: str, conteudo: str, ferramenta: str | None = None, resultado: str | None = None
    ):
        self.tipo = tipo
        self.conteudo = conteudo
        self.ferramenta = ferramenta
        self.resultado = resultado

    def para_display(self):
        if self.tipo == "raciocinio":
            return f"Pensamento: {self.conteudo}"
        elif self.tipo == "acao":
            return f"Acao: {self.ferramenta}({self.conteudo})"
        elif self.tipo == "observacao":
            preview = (
                self.resultado[:200] + "..." if len(self.resultado or "") > 200 else self.resultado
            )
            return f"Observacao: {preview}"
        elif self.tipo == "resposta":
            return None
        return self.conteudo


def _formatar_ferramentas_texto() -> str:
    linhas = []
    for f in REGISTRO_FERRAMENTAS:
        params = f.schema.get("properties", {})
        required = f.schema.get("required", [])
        param_str = ", ".join(f"{k}" + (" (obrigatorio)" if k in required else "") for k in params)
        linhas.append(f"- {f.nome}: {f.descricao}")
        if param_str:
            linhas.append(f"  Parametros: {param_str}")
    return "\n".join(linhas)


def _filtrar_ferramentas(pergunta: str, *, has_document: bool = False) -> list:
    """Filter tools based on query relevance."""
    keywords_map = {
        "pesquisar_web": [
            "pesquisar",
            "buscar",
            "procurar",
            "web",
            "internet",
            "atual",
            "hoje",
            "agora",
            "preco",
            "noticia",
        ],
        "pesquisar_google": ["google", "buscar no google", "pesquisa google"],
        "pesquisar_noticias": [
            "noticia",
            "noticias",
            "ultimas",
            "recentes",
            "atualidades",
            "aconteceu",
            "jornal",
        ],
        "navegar_web": ["navegar", "extrair", "scraping", "scrape", "extrair conteudo"],
        "abrir_no_navegador": [
            "abrir",
            "abre",
            "abrir site",
            "abrir no navegador",
            "youtube",
            "google",
            "abrir no browser",
            "abra o site",
            "abrir site",
        ],
        "executar_codigo": ["codigo", "python", "calcular", "script", "programa", "executar"],
        "salvar_memoria": ["lembrar", "memoria", "salvar", "guarda", "anota"],
        "buscar_memoria": [
            "lembra",
            "memoria",
            "buscar memoria",
            "o que eu disse",
            "o que eu falei",
        ],
        "listar_arquivos": ["listar", "arquivos", "pasta", "diretorio", "arquivos na"],
        "ler_arquivo": ["ler arquivo", "abrir arquivo", "conteudo do arquivo"],
        "processar_arquivo": [
            "processar",
            "analisar arquivo",
            "arquivo pdf",
            "arquivo doc",
            "arquivo odt",
        ],
        "informacoes_sistema": ["sistema", "info", "versao", "python", "so"],
        "indexar_documento": ["indexar", "guardar documento", "indexar documento", "rag"],
        "listar_documentos_rag": ["listar documentos", "documentos indexados", "documentos no rag"],
        "remover_documento": ["remover documento", "deletar documento", "apagar documento"],
        "listar_estoque": [
            "estoque",
            "itens",
            "peças",
            "pecas",
            "produtos",
            "inventario",
            "quais itens",
            "resumo do estoque",
        ],
        "buscar_item_estoque": ["estoque", "quantidade", "tem de", "tenho", "quanto", "item"],
        "entrada_estoque": [
            "entrada",
            "recebi",
            "comprei",
            "entrou",
            "adicionar estoque",
            "repor",
            "reposicao",
            "aumentar estoque",
        ],
        "saida_estoque": [
            "saida",
            "usei",
            "enviei",
            "vendi",
            "removeu",
            "diminuir estoque",
            "gastei",
            "consumi",
        ],
        "adicionar_item_estoque": [
            "cadastrar item",
            "novo item",
            "adicionar item",
            "cadastrar produto",
            "novo produto",
            "item novo",
        ],
        "itens_estoque_baixo": [
            "estoque baixo",
            "estoque minimo",
            "critico",
            "precisa repor",
            "repicao",
            "itens baixos",
            "alerta",
        ],
        "historico_movimentacoes": [
            "historico",
            "movimentacoes",
            "ultimas entradas",
            "ultimas saidas",
            "log de estoque",
        ],
        "listar_agenda": [
            "agenda",
            "compromisso",
            "compromissos",
            "consulta",
            "consultas",
            "visita",
            "visitas",
            "prazo",
            "prazos",
            "lembrete",
            "lembretes",
            "horario",
        ],
        "criar_compromisso_agenda": [
            "marque",
            "agenda",
            "agende",
            "crie compromisso",
            "criar compromisso",
            "me lembre",
            "lembrar de",
            "lembrete",
        ],
        "marcar_lembrete_agenda": [
            "marcar lembrete",
            "lembrete enviado",
            "dispensar lembrete",
            "ignorar lembrete",
        ],
        "listar_clientes": [
            "cliente",
            "clientes",
            "cadastro de cliente",
            "carteira de clientes",
        ],
        "cadastrar_cliente": [
            "cadastrar cliente",
            "novo cliente",
            "adicione o cliente",
            "adicionar cliente",
        ],
        "listar_fornecedores": [
            "fornecedor",
            "fornecedores",
            "cadastro de fornecedor",
            "compras de fornecedor",
        ],
        "cadastrar_fornecedor": [
            "cadastrar fornecedor",
            "novo fornecedor",
            "adicione o fornecedor",
            "adicionar fornecedor",
        ],
        "listar_produtos_servicos": [
            "catalogo",
            "produto",
            "produtos",
            "servico",
            "servicos",
            "sku",
            "preco de venda",
            "margem",
            "tabela de preco",
        ],
        "cadastrar_produto_servico": [
            "cadastrar produto",
            "novo produto",
            "cadastrar servico",
            "novo servico",
            "adicionar ao catalogo",
        ],
        "listar_orcamentos": ["orcamento", "orcamentos", "proposta", "propostas", "venda"],
        "listar_processos_prazos": ["processo", "processos", "caso", "casos", "prazo", "prazos"],
        "gerar_relatorio_local": [
            "gerar relatorio",
            "gere um relatorio",
            "criar relatorio",
            "crie um relatorio",
            "faca um relatorio",
            "relatorio em pdf",
            "relatorio pdf",
        ],
        "gerar_grafico": [
            "grafico",
            "graficos",
            "chart",
            "barras",
            "pizza",
            "pie",
            "line",
            "area",
            "histograma",
            "dispersao",
            "scatter",
            "radar",
            "mapa de calor",
            "heatmap",
            "cascata",
            "waterfall",
            "funil",
            "funnel",
            "boxplot",
            "combinado",
            "combo",
            "indicador",
            "kpi",
            "eficiencia",
            "eficiência",
            "desempenho",
            "produtividade",
            "atingimento",
            "meta",
            "visualizar",
            "visualizar dados",
            "plotar",
            "plot",
        ],
    }

    pergunta_lower = pergunta.lower()
    relevant_tools = set()

    for tool_name, keywords in keywords_map.items():
        if any(kw in pergunta_lower for kw in keywords):
            relevant_tools.add(tool_name)

    if has_document:
        # The attachment is already extracted by AIWorker. Sending every company
        # tool schema increases prompt processing time and can make the model call
        # processar_arquivo twice. Keep only tools explicitly requested by the user.
        relevant_tools.discard("processar_arquivo")
        return [f for f in REGISTRO_FERRAMENTAS if f.nome in relevant_tools]

    # Always include basic tools
    relevant_tools.add("informacoes_sistema")

    # Sempre incluir ferramentas web (essenciais para pesquisa/abrir sites)
    relevant_tools.add("abrir_no_navegador")
    relevant_tools.add("pesquisar_web")

    # Read access remains available across the local business databases. Write
    # tools are still exposed only when the request contains an explicit intent.
    relevant_tools.update(
        {
            "buscar_item_estoque",
            "buscar_memoria",
            "historico_movimentacoes",
            "itens_estoque_baixo",
            "listar_agenda",
            "listar_clientes",
            "listar_documentos_rag",
            "listar_estoque",
            "listar_fornecedores",
            "listar_orcamentos",
            "listar_processos_prazos",
            "listar_produtos_servicos",
        }
    )

    return [f for f in REGISTRO_FERRAMENTAS if f.nome in relevant_tools]


def _formatar_ferramentas_texto_filtrado(ferramentas: list) -> str:
    """Format only the given list of tools."""
    linhas = []
    for f in ferramentas:
        params = f.schema.get("properties", {})
        required = f.schema.get("required", [])
        param_str = ", ".join(f"{k}" + (" (obrigatorio)" if k in required else "") for k in params)
        linhas.append(f"- {f.nome}: {f.descricao}")
        if param_str:
            linhas.append(f"  Parametros: {param_str}")
    return "\n".join(linhas)


def loop_react(
    prompt_dict: dict[str, Any],
    fn_status: Callable[[str], None] | None = None,
    fn_passo: Callable[[Any], None] | None = None,
    fn_chunk: Callable[[str], None] | None = None,
    history: list[dict] | None = None,
) -> tuple[str, list[PassoReact]]:
    """Main ReAct loop using native OpenAI tool calling."""
    pergunta = _sanitize_internal_markers(prompt_dict.get("pergunta", ""))
    texto_doc = _sanitize_internal_markers(prompt_dict.get("documento", ""))
    nome_doc = _sanitize_internal_markers(prompt_dict.get("nome_documento", ""))
    caminho_doc = _sanitize_internal_markers(prompt_dict.get("caminho_documento", ""))
    memorias_ativas = prompt_dict.get("memorias_ativas", True)
    memorias_fornecidas = prompt_dict.get("memorias_relevantes")
    document_extraction_failed = "EXTRACAO_INSUFICIENTE" in texto_doc
    chart_request = _is_chart_request(pergunta)

    from core.memory import buscar_memorias

    if memorias_fornecidas is not None:
        memorias_relevantes = [
            str(memory).strip() for memory in memorias_fornecidas if str(memory).strip()
        ]
    else:
        memorias_relevantes = (
            buscar_memorias(pergunta)
            if pergunta and memorias_ativas and not document_extraction_failed
            else []
        )

    data_hora = datetime.now().strftime("%d/%m/%Y as %H:%M")
    settings = get_settings()
    customer_context = settings.customer_prompt_context
    response_style_context = settings.response_style_prompt_context
    agenda_context = _agenda_prompt_context()

    ferramentas_relevantes = _filtrar_ferramentas(
        pergunta,
        has_document=bool(texto_doc),
    )
    ferramentas_openai = [f.para_openai() for f in ferramentas_relevantes]
    system_content = SYSTEM_PROMPT_REACT.format(
        assistant_name=settings.assistant.name,
        assistant_profile=settings.assistant.profile,
        customer_context=customer_context,
        response_style_context=response_style_context,
        data_hora=data_hora,
    )

    extra_system_prompt = _sanitize_internal_markers(prompt_dict.get("system_prompt", ""))
    if extra_system_prompt:
        system_content += f"\n## Contexto da Interface\n{extra_system_prompt}\n"
    if agenda_context:
        system_content += f"\n{agenda_context}\n"

    if texto_doc:
        budget = get_budget()
        max_doc_chars = int(budget.document_max * 3.5)
        max_doc_chars = min(max_doc_chars, settings.doc_text_limit)

        doc_info = "\n## Documento Anexado\n"
        doc_info += f"Nome: {nome_doc}\n"
        if caminho_doc:
            doc_info += f"Caminho completo: {caminho_doc}\n"
        if document_extraction_failed:
            doc_info += (
                "A extracao convencional e o OCR local falharam ou foram insuficientes. "
                "Explique o diagnostico e solicite uma versao mais nitida ou pesquisavel. "
                "Nao invente um relatorio nem use memorias como conteudo do arquivo.\n"
            )
        else:
            doc_info += "Conteudo ja extraido abaixo. NAO chame processar_arquivo novamente.\n"
            doc_info += "Analise o conteudo e responda diretamente ao pedido do usuario.\n"
        doc_info += f"Conteudo:\n{texto_doc[:max_doc_chars]}\n"
        system_content += doc_info

    if memorias_relevantes:
        memorias_texto = "\n".join(
            f"- {_sanitize_internal_markers(m)}" for m in memorias_relevantes
        )
        memorias_section = (
            f"\n## Memorias do Usuario (INFORMACOES CONFIRMADAS PELO USUARIO)\n{memorias_texto}\n"
        )
    else:
        memorias_section = ""

    if pergunta and not texto_doc:
        try:
            from ai.rag import buscar_contexto

            rag_chunks = buscar_contexto(pergunta)
            if rag_chunks:
                rag_context = "\n---\n".join(rag_chunks)
                system_content += (
                    f"\n## Contexto de Documentos Indexados\n"
                    f"{rag_context}\n"
                    f"Use este contexto para responder se for relevante.\n"
                )
        except Exception as e:
            logger.debug("RAG context search failed (non-blocking): %s", e)

    from ai.agents import classificar_tarefa, obter_prompt_agente

    agente = classificar_tarefa(pergunta) if pergunta else None
    if agente:
        agent_prompt = obter_prompt_agente(agente)
        if agent_prompt:
            system_content += f"\n## Modo Agente: {agente.nome}\n{agent_prompt}\n"

    mensagens = [{"role": "system", "content": system_content}]

    if history:
        budget = get_budget()
        trimmed_history = budget.trim_history(history)
        for msg in trimmed_history:
            msg = dict(msg)
            msg["content"] = _sanitize_internal_markers(msg.get("content", ""))
            mensagens.append(msg)
        budget_info = budget.analyze_messages(mensagens)
        if budget_info["utilization"] > 0.70:
            pct = int(budget_info["utilization"] * 100)
            logger.info(
                "Context budget usage: %s%% (%s/%s tokens)",
                pct,
                budget_info["total_used"],
                budget_info["available"],
            )

    if memorias_section:
        mensagens.append({"role": "system", "content": memorias_section})

    pergunta_final = pergunta if pergunta else "Faca um resumo direto do arquivo anexado."
    mensagens.append({"role": "user", "content": pergunta_final})

    passos = []
    if chart_request:
        if fn_status:
            fn_status("Gerando visualizacao local...")
        direct_chart = _try_direct_business_chart(pergunta)
        if direct_chart is None:
            direct_chart = _try_chart_from_text(pergunta, pergunta)
        if direct_chart:
            step = PassoReact("resposta", direct_chart)
            passos.append(step)
            if fn_passo:
                fn_passo(step)
            return direct_chart, passos

    stock_context = nome_doc == "Dados do Estoque"
    direct_report = (
        _try_direct_business_report(pergunta) if not texto_doc or stock_context else None
    )
    if direct_report:
        if fn_status:
            fn_status("Relatorio local concluido.")
        step = PassoReact("resposta", direct_report)
        passos.append(step)
        if fn_passo:
            fn_passo(step)
        return direct_report, passos

    multi_manager = get_multi_model_manager()
    has_document = bool(texto_doc)
    has_image = bool(prompt_dict.get("caminho_imagem"))
    if fn_status:
        fn_status("Selecionando melhor modelo local...")
    model_id, llama = multi_manager.route_and_invoke(
        pergunta,
        has_document=has_document,
        has_image=has_image,
    )
    complexity = multi_manager.get_current_complexity()

    if fn_status:
        fn_status("Estruturando a resposta...")

    logger.info(f"ReAct: routing to {model_id} (complexity: {complexity})")

    for i in range(MAX_ITERACOES):
        if fn_status:
            textos_status = (
                "Pensando...",
                "Elaborando a melhor resposta...",
                "Organizando os detalhes...",
                "Validando informacoes...",
                "Refinando a resposta final...",
            )
            fn_status(textos_status[min(i, len(textos_status) - 1)])

        with trace_span("react.llm_call", {"model": model_id, "iteration": i}) as span:
            try:
                kwargs = {
                    "messages": mensagens,
                    "temperature": settings.response.temperature,
                    "max_tokens": min(settings.num_predict, 4096),
                    "top_p": settings.response.top_p,
                    "stream": True,
                    "repeat_penalty": 1.05 if memorias_relevantes else 1.2,
                    "frequency_penalty": 0.1 if memorias_relevantes else 0.3,
                    "presence_penalty": 0.1 if memorias_relevantes else 0.3,
                    "stop": list(INTERNAL_CHAT_MARKERS),
                }
                if ferramentas_openai:
                    kwargs["tools"] = ferramentas_openai
                    kwargs["tool_choice"] = "auto"

                stream = llama.create_chat_completion(**kwargs)
            except Exception as e:
                span.set_attribute("error", str(e))
                return f"Erro ao conectar com o LLM: {e}", passos

            conteudo_acumulado = ""
            tool_calls_buffer: dict[int, dict[str, str]] = {}
            tokens_repetidos = 0
            ultimo_token = ""
            thinking_emitted = False
            writing_emitted = False
            reasoning_filter = _ReasoningStreamFilter(_is_reasoning_model(model_id))

            for chunk in stream:
                choice = chunk["choices"][0]
                delta = choice.get("delta", {})
                content = delta.get("content") or ""
                if content:
                    combined_content = conteudo_acumulado + content
                    marker_idx = _first_internal_marker_index(combined_content)
                    stop_stream = marker_idx >= 0
                    if stop_stream:
                        content = combined_content[len(conteudo_acumulado) : marker_idx]
                        combined_content = combined_content[:marker_idx]
                        if not content:
                            conteudo_acumulado = combined_content
                            break

                    if content == ultimo_token:
                        tokens_repetidos += 1
                        if tokens_repetidos > 10:
                            break
                    else:
                        tokens_repetidos = 0
                        ultimo_token = content
                    visible_content = reasoning_filter.feed(content)
                    if visible_content:
                        conteudo_acumulado += visible_content

                        if not thinking_emitted and conteudo_acumulado.strip():
                            thinking_emitted = True
                            passo_pensamento = PassoReact("raciocinio", conteudo_acumulado)
                            passos.append(passo_pensamento)
                            if fn_passo:
                                fn_passo(passo_pensamento)

                        if fn_chunk and not chart_request:
                            if not writing_emitted and fn_status:
                                writing_emitted = True
                                fn_status("Escrevendo resposta...")
                            fn_chunk(visible_content)

                    if stop_stream:
                        break

                if delta.get("tool_calls"):
                    for call in delta["tool_calls"]:
                        idx = call.get("index", 0)
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {"name": "", "arguments": ""}
                        fn_data = call.get("function", {})
                        if fn_data.get("name"):
                            tool_calls_buffer[idx]["name"] = fn_data["name"]
                        if fn_data.get("arguments"):
                            tool_calls_buffer[idx]["arguments"] += fn_data["arguments"]

            trailing_content = reasoning_filter.finish()
            if trailing_content:
                conteudo_acumulado += trailing_content
                if fn_chunk and not chart_request:
                    fn_chunk(trailing_content)

            span.set_attribute("content_length", len(conteudo_acumulado))
            span.set_attribute("tool_calls_count", len(tool_calls_buffer))

        tool_calls_acumulados = []
        if tool_calls_buffer:
            for idx in sorted(tool_calls_buffer.keys()):
                tc = tool_calls_buffer[idx]
                if tc["name"]:
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse tool call arguments for %s", tc["name"])
                        args = {}
                    tool_calls_acumulados.append(
                        {"function": {"name": tc["name"], "arguments": args}}
                    )

        if conteudo_acumulado or tool_calls_acumulados:
            tool_calls_msg = None
            if tool_calls_acumulados:
                tool_calls_msg = []
                for j, call in enumerate(tool_calls_acumulados):
                    tool_calls_msg.append(
                        {
                            "id": f"call_{j}",
                            "type": "function",
                            "function": call["function"],
                        }
                    )
            mensagens.append(
                {
                    "role": "assistant",
                    "content": conteudo_acumulado or "",
                    "tool_calls": tool_calls_msg,
                }
            )

        if not tool_calls_acumulados:
            if conteudo_acumulado:
                passos.append(PassoReact("resposta", conteudo_acumulado))
                if fn_passo:
                    fn_passo(passos[-1])
                resposta_final = _limpar_resposta(conteudo_acumulado)
                resposta_final = _fallback_grafico(pergunta, resposta_final)
                return resposta_final, passos
            continue

        for j, call in enumerate(tool_calls_acumulados):
            nome_func = call["function"]["name"]
            args = call["function"]["arguments"]

            passo_acao = PassoReact("acao", str(args), ferramenta=nome_func)
            passos.append(passo_acao)
            if fn_passo:
                fn_passo(passo_acao)

            if fn_status:
                fn_status(f"Consultando ferramenta: {nome_func}...")

            with trace_span(
                "react.tool_execution",
                {"tool": nome_func, "argument_names": ",".join(sorted(args))[:200]},
            ) as tool_span:
                resultado = executar_ferramenta(nome_func, args, require_approval=True)
                tool_span.set_attribute("result_length", len(str(resultado)))

            if str(resultado).startswith(APPROVAL_REQUIRED_PREFIX):
                resposta_aprovacao = str(resultado).removeprefix(APPROVAL_REQUIRED_PREFIX).strip()
                passos.append(PassoReact("resposta", resposta_aprovacao))
                return resposta_aprovacao, passos

            passo_obs = PassoReact("observacao", "", resultado=resultado)
            passos.append(passo_obs)
            if fn_passo:
                fn_passo(passo_obs)

            mensagens.append(
                {
                    "role": "tool",
                    "tool_call_id": f"call_{j}",
                    "content": str(resultado),
                }
            )

            gc.collect()

    resposta_fallback = (
        "Analisei a solicitacao mas nao consegui gerar uma resposta completa "
        "nas iteracoes disponiveis. Tente reformular a pergunta."
    )
    resposta_fallback = _fallback_grafico(pergunta, resposta_fallback)
    passos.append(PassoReact("resposta", resposta_fallback))
    return resposta_fallback, passos


def _limpar_resposta(texto: str) -> str:
    texto = _strip_reasoning_blocks(texto)
    marker_idx = _first_internal_marker_index(texto)
    if marker_idx >= 0:
        texto = texto[:marker_idx]
    texto = re.sub(r"(?is)\n?##\s*Memorias do Usuario.*", "", texto)
    texto = re.sub(r"(?is)\n?##\s*Perfil do Cliente/Empresa.*", "", texto)
    texto = re.sub(r"^[sS]ou o [cC]elsius,?\s*(seu\s+)?(assistente\s+)?(de\s+)?IA\.?\s*", "", texto)
    texto = re.sub(r"\(Nota:.*?\)", "", texto, flags=re.DOTALL)
    texto = re.sub(r"([\U0001F300-\U0001F9FF])\1{3,}$", "", texto)
    texto = re.sub(r"[\.]{5,}$", "...", texto)
    texto = re.sub(r"[-]{5,}$", "", texto)
    texto = re.sub(r"[=]{5,}$", "", texto)
    return texto.strip()


def _fallback_grafico(pergunta: str, resposta: str) -> str:
    """Detect chart requests that the LLM failed to generate and auto-generate."""
    if not _is_chart_request(pergunta):
        return resposta
    if _response_has_generated_chart(resposta):
        return resposta

    textual_result = _execute_textual_chart_call(resposta)
    if textual_result:
        logger.info("[FallbackGrafico] Chamada textual recuperada e executada")
        return textual_result

    direct_result = _try_direct_business_chart(pergunta)
    if direct_result:
        logger.info("[FallbackGrafico] Grafico empresarial gerado sem depender do LLM")
        return direct_result

    text_result = _try_chart_from_text(pergunta, f"{pergunta}\n{resposta}")
    if text_result:
        logger.info("[FallbackGrafico] Dados tabulares recuperados e renderizados")
        return text_result

    cleaned_response = re.sub(
        r"!\[[^\]]*\]\((?:https?://|data:)[^)]+\)",
        "",
        resposta,
    ).strip()
    if cleaned_response and "example.com" not in cleaned_response:
        cleaned_response += "\n\n"
    else:
        cleaned_response = ""
    return (
        f"{cleaned_response}"
        "Nao encontrei dados numericos suficientes para criar um grafico confiavel. "
        "Informe os valores, anexe uma tabela ou indique qual modulo empresarial "
        "contem os dados. O Celsius nao cria links ou indicadores ficticios."
    )
