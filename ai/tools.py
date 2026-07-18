import json
import os
from datetime import datetime
from pathlib import Path

from core.config import get_settings


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


def _validate_path(path: str) -> Path:
    """Validate and resolve path within allowed directory."""
    settings = get_settings()
    path = Path(path).resolve()
    base_dir = settings.base_dir.resolve()
    try:
        path.relative_to(base_dir)
    except ValueError:
        raise ValueError(f"Path traversal attempt blocked: {path}")
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path


def _tool_processar_arquivo(caminho: str) -> str:
    from processors import processar_arquivo
    path = _validate_path(caminho)
    settings = get_settings()
    return processar_arquivo(str(path), base_dir=settings.base_dir)


def _tool_pesquisar_web(query: str) -> str:
    from core.commands import pesquisar_web
    return pesquisar_web(query)


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
    return json.dumps({
        "sistema": platform.system(),
        "versao": platform.version(),
        "python": platform.python_version(),
        "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "diretorio": os.getcwd(),
    }, indent=2)


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
    import webbrowser
    webbrowser.open(url)
    return f"Abrindo {url} no navegador..."


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
        descricao="Abre um site ou pesquisa no navegador do usuario. Use quando pedirem para abrir YouTube, Google, ou qualquer site.",
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
]


def obter_schemas_ollama():
    return [f.para_ollama() for f in REGISTRO_FERRAMENTAS]


def obter_ferramenta(nome):
    for f in REGISTRO_FERRAMENTAS:
        if f.nome == nome:
            return f
    return None


def executar_ferramenta(nome, argumentos):
    ferramenta = obter_ferramenta(nome)
    if not ferramenta:
        return f"Ferramenta '{nome}' nao encontrada."
    try:
        return ferramenta.funcao(**argumentos)
    except Exception as e:
        return f"Erro ao executar '{nome}': {e}"
