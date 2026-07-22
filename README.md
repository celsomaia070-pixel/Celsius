# Celsius - Agente Multimodal de IA

Celsius é um agente de IA multimodal avançado com capacidades reais de ação, construído com Python, PySide6 e llama-cpp-python.

## Funcionalidades

- **Processamento de Documentos**: PDF, DOCX, ODT, ODS, ODP com extração de metadados
- **Análise de Imagens**: OCR, descrições, metadados EXIF
- **Transcrição de Áudio**: Whisper (suporte a MP3, WAV, OGG, M4A, FLAC)
- **Execução de Código Python**: Sandbox seguro com limites de recursos
- **Pesquisa Web**: DuckDuckGo em tempo real
- **Navegação Web**: Playwright para automação e extração
- **RAG (Retrieval-Augmented Generation)**: ChromaDB + sentence-transformers
- **Memória de Longo Prazo**: Busca semântica com embeddings
- **Relatórios**: Geração de PDF e DOCX
- **Texto-para-Fala**: edge-tts (pt-BR)
- **Fala-para-Texto**: SpeechRecognition + Google
- **Sistema Multi-Agente**: Agentes especializados (RAG, Código, Web, Arquivos, Memória)
- **Ícones SVG nativos**: Substituição do `qtawesome` por módulo próprio (`ui/icons.py`) — 23 ícones, zero dependências externas
- **Memória semântica melhorada**: threshold 0.15, top_k 10, injeção de até 15 memórias no prompt; busca retorna todas quando total ≤ limite
- **Histórico de conversa**: Arquivos e imagens agora persistem no contexto da sessão
- **Indicador "Pensando..."**: Movido para dentro do chat (widget dedicado), sem texto fixo na barra superior
- **Cursor piscante em streaming**: Animação `▌` durante geração de resposta
- **Mensagens do usuário**: Alinhadas à direita, largura total, fade-in suave

## Requisitos

- Python 3.10+
- llama-cpp-python com suporte Vulkan (GPU) ou CPU
- FFmpeg (para processamento de áudio)
- Dependências do sistema para Playwright: `playwright install-deps`

## Instalação

```bash
# Clonar repositório
git clone https://github.com/celso/celsius.git
cd celsius

# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Instalar dependências
pip install -e ".[dev]"

# Instalar Playwright
playwright install chromium

# Executar (modelos GGUF serão baixados automaticamente)
python main.py
```

## Uso

```bash
python main.py
```

### Atalhos de Teclado

| Atalho | Ação |
|---|---|
| `Ctrl+K` | Paleta de comandos |
| `Ctrl+N` | Nova conversa |
| `Ctrl+B` | Mostrar/esconder sidebar |
| `Ctrl+Shift+L` | Alternar tema claro/escuro |
| `Ctrl+Shift+Del` | Limpar conversa atual |
| `Ctrl+,` | Configurações |
| `Enter` | Enviar mensagem |

### Bate-Papo

- **Enviar mensagem**: Digite no campo de texto e pressione **Enter** ou clique no botão de envio (avião de papel).
- **Anexar arquivo**: Clique no botão de **clips**. Imagens (.png, .jpg, .gif, .webp) e documentos (.pdf, .docx, .xlsx, .txt) são processados automaticamente.
- **Gravar áudio**: Clique no botão de **microfone**. O áudio é transcrito com Whisper e o texto é enviado automaticamente. O ícone fica vermelho durante a gravação.
- **Leitura em voz alta**: O botão de **volume** ativa/desativa TTS (edge-tts, pt-BR). Respostas da IA são lidas automaticamente quando ativado.
- **Copiar resposta**: Passe o mouse sobre uma mensagem da IA e clique no ícone de **copiar** que aparece.
- **Renderização**: Mensagens suportam Markdown completo: código, tabelas, listas, negrito, itálico e cabeçalhos.

### Sidebar

- **Nova conversa**: Botão **"+"** no topo da sidebar.
- **Buscar**: Digite no campo de busca para filtrar conversas.
- **Trocar conversa**: Clique em qualquer conversa na lista.
- **Renomear**: Clique com botão direito → **Renomear**.
- **Excluir**: Clique com botão direito → **Excluir**.
- **Memórias**: Botão **"Memórias"** na parte inferior. Adicione, visualize e remova memórias do usuário.
- **Configurações**: Botão **"Configurações"** (em desenvolvimento).

### Paleta de Comandos (`Ctrl+K`)

Busca rápida de ações. Digite para filtrar, use ↑↓ para navegar, **Enter** para executar:

| Ação | Atalho |
|---|---|
| Nova conversa | `Ctrl+N` |
| Limpar conversa | `Ctrl+Shift+Del` |
| Alternar sidebar | `Ctrl+B` |
| Alternar tema | `Ctrl+Shift+L` |
| Trocar modelo | — |
| Ver memórias | — |
| Configurações | `Ctrl+,` |

### Comandos Rápidos (no chat)

Digite frases naturais para ações rápidas:

- `"abra o youtube"` / `"pesquisar no youtube música"` — abre YouTube
- `"abra o google"` / `"buscar receita no google"` — abre Google
- `"que horas são"` — retorna a hora atual

### Temas

Dois temas disponíveis: **Claro** (padrão) e **Escuro** (GitHub-dark). Alterne com `Ctrl+Shift+L`.

### Troca de Modelos

Use o **dropdown de modelo** na barra de entrada. Modelos GGUF são baixados automaticamente na primeira seleção. Indicadores mostram status: ✓ (baixado) ou ↓ (pendente).

## Estrutura do Projeto

```
celsius/
├── src/celsius/
│   ├── config.py          # Configurações (pydantic-settings)
│   ├── constants.py       # Constantes e enums
│   ├── models/            # Modelos Pydantic
│   ├── core/
│   │   ├── memory.py      # MemoryService (thread-safe)
│   │   ├── commands.py    # Comandos rápidos
│   │   └── sandbox.py     # CodeSandbox seguro
│   ├── ai/
│   │   ├── engine.py      # Motor ReAct principal
│   │   ├── rag.py         # RAGService
│   │   ├── react.py       # Loop ReAct
│   │   ├── tools.py       # Ferramentas do agente
│   │   ├── browser.py     # Navegação web (Playwright)
│   │   └── agents.py      # Agentes especializados
│   ├── processors/        # Processadores de arquivo
│   ├── workers/           # QRunnables para thread pool
│   ├── ui/                # Interface PySide6
│   └── services/          # Serviços de negócio
├── tests/
├── pyproject.toml
└── main.py
```

## Segurança

- **Path Traversal**: Todas as operações de arquivo validam caminhos contra o diretório base
- **Code Sandbox**: Execução isolada com:
  - Imports bloqueados (os, sys, subprocess, etc.)
  - Funções perigosas bloqueadas (eval, exec, open, etc.)
  - Limites de CPU, memória (256MB), arquivos (10MB), file descriptors
  - Usuário nobody/nogroup no Unix
  - Ambiente restrito (PATH mínimo, sem PYTHONPATH)
- **Thread Safety**: Serviços com locks RLock para acesso concorrente

## Testes

```bash
# Rodar todos os testes
pytest

# Com cobertura
pytest --cov=celsius --cov-report=html

# Apenas testes rápidos
pytest -m "not slow"

# Verboso
pytest -v
```

## Linting e Formatação

```bash
# Verificar
ruff check .
mypy src/

# Corrigir automaticamente
ruff check --fix .
ruff format .
```

## Arquitetura

### WorkerManager + QRunnable
Substitui QThread por QRunnable + QThreadPool.globalInstance() para:
- Melhor gerenciamento de threads
- Reutilização de threads
- Cancelamento limpo
- Escalabilidade

### Service Classes
Substitui estado global por classes de serviço injetáveis:
- `MemoryService` - Memória semântica thread-safe
- `RAGService` - RAG com ChromaDB thread-safe
- `ConversationContext` - Histórico de conversa por sessão

### Configuração
Pydantic Settings com validação, `.env` support, types seguros.

## Licença

MIT