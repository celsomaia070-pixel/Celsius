# Arquitetura

O Celsius e uma aplicacao desktop local, orientada a modulos. A interface fica em
PySide6, enquanto tarefas pesadas rodam em workers para nao travar a janela.

## Visao Geral

```text
Usuario
  |
  v
ui/  -> workers/ -> ai/ -> core/
  |        |        |       |
  |        |        |       +-- settings, modelos, memoria, sandbox
  |        |        +---------- engine, RAG, ferramentas, navegacao
  |        +------------------- IA, microfone, TTS, codigo
  +---------------------------- chat, anexos, kanban, dialogos
```

## Modulos Principais

### `main.py`

Ponto de entrada. Inicializa configuracao, logging, container, modelo e janela
principal.

### `core/`

Camada de servicos compartilhados:

- `settings.py`: configuracao central com Pydantic.
- `config.py`: catalogo de modelos e compatibilidade legado.
- `model_router.py`: escolha de modelo por perfil/capacidade.
- `model_downloader.py`: download sob demanda de modelos.
- `conversations.py`: persistencia de conversas.
- `memory.py`: memoria semantica (SQLite + cache de embeddings).
- `inventory.py`: estoque (SQLite com migracao automatica do JSON legado).
- `sqlite_store.py`: camada SQLite compartilhada (WAL + lock entre processos).
- `json_persistence.py`: escrita atomica para arquivos JSON duravels.
- `sandbox.py`: execucao controlada de codigo (subprocesso local ou backend
  opcional via Docker).
- `extras.py`: deteccao de extras opcionais (documentos, voz, web, docker).
- `telemetry.py`, `metrics.py`: observabilidade opcional.

### `ai/`

Camada de inteligencia:

- `engine.py`: orquestra resposta da IA.
- `react.py`: ciclo de raciocinio/acao.
- `tools.py`: ferramentas chamadas pela IA.
- `rag.py`: busca hibrida e contexto documental.
- `agents.py`: agentes especializados.
- `browser.py`: automacao web.

### `processors/`

Extrai texto ou metadados de anexos:

- PDF, DOCX, ODF/ODS/ODP.
- Imagens.
- Audio.
- Relatorios.

### `workers/`

Executa tarefas demoradas fora da thread principal:

- `ai_worker.py`: resposta da IA.
- `mic_worker.py`: microfone/transcricao (Whisper carregado sob demanda e de
  forma lazy; um daemon pre-carrega o modelo em background em `main.py`).
- `tts_worker.py`: fala.
- `code_worker.py`: execucao controlada (sandbox local ou Docker).

### `ui/`

Interface grafica:

- `window.py`: janela principal.
- `chat/`: area de chat, mensagens e entrada.
- `controllers/`: ponte entre UI, workers e persistencia.
- `theme/`: tokens, esquemas e stylesheet.
- `kanban_view.py`: gerenciamento visual de estoque.

## Fluxo de uma Mensagem

1. Usuario digita ou anexa arquivos na UI.
2. `ui/window.py` coleta texto e anexos.
3. `WorkerController` envia a tarefa para `AIWorker`.
4. `AIWorker` processa anexos com `processors/`.
5. `ai/engine.py` monta contexto, memoria, RAG e ferramentas.
6. Modelo local gera resposta.
7. Worker emite sinais para atualizar a UI.
8. Conversa e memoria sao persistidas.
9. Apos cada resposta, um thread em background (`remember_from_turn` em
   `core/memory.py`) extrai fatos duraveis do dialogo e os salva como memoria
   de longo prazo, reutilizando o mesmo modelo local sem bloquear a UI.

## Memoria de Longo Prazo nas Conversas

- Duas fontes: o historico efemero da conversa (JSON em `data/conversations/`) e a
  memoria duravel (SQLite `memorias.db`).
- Apos cada turno concluido, desktop e web chamam `extract_and_store_async()`
  com as ultimas mensagens; o extrator usa o LLM local com um prompt dedicado e
  salva apenas fatos novos (`MemoryService.add_unique`, que descarta
  quase-duplicatas lexicais).
- Na busca, desktop (`get_memories_for_ai`) e web (`_load_memories`) montam uma
  consulta por turno recente via `memory_query_context()` e mesclam os
  resultados com `MemoryService.search_multi()`, em vez de buscar so a ultima
  mensagem.
- Controles em `MemorySettings`: `auto_extract_facts`, `extraction_max_facts` e
  `extraction_recent_messages` (todas ligadas por padrao).

## Dados Locais

Os diretorios abaixo guardam dados da maquina do usuario e nao devem ir para o
Git:

- `resources/`
- `cache/`
- `rag_vectors.sqlite3` e arquivos auxiliares do indice local
- `inventory.db*` e `memorias.db*` (bancos SQLite gerados em runtime)
- `data/conversations/`
- `voices/`
- `logs/`
- `data/`
- `build/`
- `dist/`

## Privacidade e Modo Offline

O Celsius roda inteiramente na maquina do usuario:

- **Pipeline de documentos e 100% local**: os `processors/`, o RAG
  (`ai/rag.py`) e o indice vetorial (`core/vector_store.py`) nao usam socket,
  http nem nenhuma chamada de rede. Cada commit deve preservar isso — o suite
  `tests/test_offline.py` bloqueia a rede e garante que processar, indexar e
  buscar documentos funciona sem qualquer saida da maquina.
- **Telemetria desligada por padrao** (`CELSIUS_TELEMETRY__ENABLED=false`). Quando
  o perfil exige operacao local (`customer.local_offline_required=True`, padrao),
  a telemetria nem sequer e inicializada — em `core/app_context.py` e tambem em
  `core/telemetry.py` — e a inicializacao registra "MODO OFF-LINE".
- **Modelos locais**: LLM (GGUF), embeddings e Whisper sao locais; na primeira
  execucao em modo fonte, pesos que ainda nao existem em cache podem ser
  baixados do Hugging Face/OpenAI (apenas binarios de modelo, nenhum conteudo do
  usuario).
- **Ferramentas de internet** (pesquisa web, navegacao, e-mail futuro) existem
  mas exigem aprovacao humana explicita (`core/tool_approval.py`).
- **Pastas autorizadas** (`security.allowed_file_roots`): o agente so le arquivos
  dentro da pasta do projeto e de pastas extras configuradas. A pasta do projeto
  e sempre autorizada; a adicao de pastas extras estende o acesso, nunca reduz.
  Configuravel pelo painel de configuracoes (uma pasta por linha) ou via env
  `CELSIUS_SECURITY__ALLOWED_FILE_ROOTS` (array JSON).
- **Escrita segura**: a ferramenta `criar_editar_arquivo` grava apenas dentro
  das mesmas pastas autorizadas, somente em extensoes texto (`txt`, `md`, `csv`,
  `json`), e esta em `SENSITIVE_TOOLS` (`core/tool_approval.py`) — exige
  aprovacao humana explicita. Sobrescrita gera backup `*.bak`; `criar` nunca
  sobrescreve um arquivo existente. Não ha edicao in-place de binarios.

Os testes de regressao de privacidade são: `tests/test_offline.py`.

## Persistencia

- Conversas ficam em arquivos JSON atomicos (`core/json_persistence.py`):
  o conteudo e escrito em um temporario, sincronizado com `fsync` e movido por
  `os.replace`, evitando arquivos corrompidos em queda de energia.
- Estoque e memoria usam SQLite (`core/sqlite_store.py`, banco ao lado do JSON
  legado, WAL + `synchronous=FULL`). Na primeira abertura o JSON e migrado
  automaticamente para o banco e o JSON original e mantido como backup.
- Embutimentos da memoria sao cacheados em `*.embeddings_cache.npy`.

## Extras Opcionais

A instalacao base (`pip install celsius`) fica leve. PDF/OCR, voz, web/mobile e
Docker vivem em `[project.optional-dependencies]` e importam suas dependencias
de forma lazy:

```powershell
pip install celsius[all]
pip install celsius[documents]  # PDF, OCR, DOCX, ODF, PDFs de relatorio
pip install celsius[voice]      # transcricao Whisper e TTS
pip install celsius[web]        # API local (mobile) e automacao de navegador
pip install celsius[docker]     # backend de sandbox via Docker
```

`core/extras.py` informa no runtime qual extra esta faltando e como instalar.

## Decisoes de Projeto

- Preferir operacao local e privada.
- Baixar modelos sob demanda.
- Manter configuracao em `.env` e `core/settings.py`.
- Evitar travar a UI com workers.
- Usar testes para proteger modulos criticos como settings, sandbox, RAG e
  roteamento de modelos.
