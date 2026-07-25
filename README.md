# Celsius - Agente Multimodal de IA Local

Assistente de IA multimodal com voz, memória e ações reais. Funciona 100% local com LLM via Vulkan (GPU AMD).

## Funcionalidades

- **Chat com LLM local** — llama-cpp-python + Vulkan (GPU) ou CPU fallback
- **Voz (microfone)** — faster-whisper (CTranslate2, int8) com VAD e pré-load em background
- **Voz (TTS)** — edge-tts em português (pt-BR)
- **Análise de documentos** — PDF, DOCX, ODT, ODS, ODP
- **Análise de imagens** — visão multimodal (Qwen2.5-VL, Gemma 3) via mmproj
- **Pesquisa web** — DuckDuckGo em tempo real
- **Navegação web** — Playwright para automação
- **RAG** — ChromaDB + sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)
- **Memória de longo prazo** — busca semântica com embeddings
- **Gerenciamento de estoque** — cadastro, entradas, saídas, relatórios com Kanban
- **Relatórios** — geração de PDF e DOCX
- **Interface PySide6** — temas claro/escuro, sidebar com conversas, paleta de comandos
- **Ícones SVG nativos** — 23 ícones, zero dependências externas
- **Sistema multi-agente** — agentes especializados (RAG, Código, Web, Arquivos, Memória)

## Requisitos

- Python 3.10+
- llama-cpp-python com suporte Vulkan (GPU AMD) ou CPU
- GPU AMD RX 7600 (ou similar) para melhor desempenho
- FFmpeg (para processamento de áudio)

## Instalação

```bash
# Clonar repositório
git clone https://github.com/celso/celsius.git
cd celsius

# Criar ambiente virtual
python -m venv .venv
.venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt

# Instalar Playwright (para navegação web)
playwright install chromium

# Executar (modelos GGUF são baixados automaticamente)
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

### Chat

- **Enviar mensagem**: Digite no campo de texto e pressione **Enter** ou clique no botão de envio.
- **Anexar arquivo**: Clique no botão de **clips**. Imagens e documentos são processados automaticamente.
- **Gravar áudio**: Clique no botão de **microfone** (toggle). O áudio é transcrito com faster-whisper e o texto é enviado automaticamente.
- **Leitura em voz alta**: O botão de **volume** ativa/desativa TTS (edge-tts, pt-BR).
- **Copiar resposta**: Passe o mouse sobre uma mensagem da IA e clique no ícone de **copiar**.
- **Renderização**: Mensagens suportam Markdown completo: código, tabelas, listas, negrito, itálico e cabeçalhos.

### Comandos Rápidos (no chat)

- `"que horas são"` — retorna a hora atual
- `"que dia é hoje"` — retorna a data atual
- `"pesquisar inteligência artificial"` — pesquisa na web via DuckDuckGo
- `"abra o YouTube música"` — abre YouTube
- `"abra o Google receita"` — abre Google

## Estrutura do Projeto

```
celsius/
├── main.py                 # Entry point
├── ai/
│   ├── engine.py           # Motor principal (ReAct + tools)
│   ├── react.py            # Loop ReAct + system prompts
│   ├── tools.py            # Ferramentas do agente
│   ├── rag.py              # RAG com ChromaDB
│   └── browser.py          # Navegação web (Playwright)
├── core/
│   ├── config.py           # Configurações e modelos GGUF
│   ├── llama_cpp.py        # Gerenciamento do modelo LLM
│   ├── commands.py         # Comandos rápidos (YouTube, Google, etc.)
│   ├── memory.py           # Memória semântica
│   └── sandbox.py          # Execução segura de código Python
├── processors/             # Processadores de arquivo (PDF, DOCX, etc.)
├── workers/
│   ├── mic_worker.py       # Gravação + faster-whisper
│   ├── tts_worker.py       # Text-to-speech (edge-tts)
│   └── worker_manager.py   # Gerenciamento de threads
├── ui/
│   ├── window.py           # Janela principal
│   ├── icons.py            # Ícones SVG nativos
│   ├── chat/               # Componentes do chat
│   ├── dialogs.py          # Diálogos (memória, relatório)
│   └── controllers/        # Controllers (conversa, workers)
├── tests/
├── resources/              # Modelos GGUF
├── conversations/          # Histórico de conversas (SQLite)
├── voices/                 # Cache de áudio TTS
└── pyproject.toml
```

## Configuração

O modelo padrão é `qwen2.5-vl-7b-q4km` com `num_ctx=16384` e `num_predict=2500`.

Modelos disponíveis (baixados automaticamente):

| Modelo | Tamanho | Visão | Categoria |
|---|---|---|---|
| Qwen2.5 VL 7B | ~4.5 GB | Sim | Multimodal |
| Gemma 3 4B | ~3.2 GB | Sim | Multimodal |
| Qwen2.5 Omni 7B | ~4.5 GB | Não | Multimodal |
| Qwen2.5 Coder 7B | ~5.4 GB | Não | Código |
| Llama 3.2 3B | ~2.5 GB | Não | Rápido |
| Qwen3.5 35B-A3B | ~19 GB | Não | Potente (MoE) |

## Segurança

- **Code Sandbox**: Execução isolada com imports bloqueados, limites de CPU/memória (256MB), e ambiente restrito
- **Path Traversal**: Validação de caminhos contra diretório base
- **Thread Safety**: Serviços com locks RLock para acesso concorrente

## Testes

```bash
pytest
pytest -v
pytest -m "not slow"
```

## Licença

MIT
