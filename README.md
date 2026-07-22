# Celsius - Agente Multimodal de IA

Celsius é um agente de IA multimodal avançado com capacidades reais de ação, construído com Python, PySide6 e Ollama.

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
- Ollama rodando localmente com modelos instalados
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

# Iniciar Ollama (em outro terminal)
ollama serve

# Baixar modelos
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text
```

## Uso

```bash
# Executar aplicação
python -m celsius

# Ou diretamente
python main.py
```

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