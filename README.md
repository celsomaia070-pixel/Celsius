# Celsius

Assistente local de IA multimodal para Windows, com chat, voz, memoria, RAG,
analise de documentos/imagens, automacoes web e gerenciamento de estoque.

O projeto roda modelos GGUF localmente via `llama-cpp-python`, com suporte a GPU
quando disponivel e fallback para CPU.

## Status do Projeto

- Aplicacao desktop em Python com PySide6.
- Testes automatizados com `pytest`.
- Lint e formatacao com `ruff`.
- Configuracao centralizada em `core/settings.py` e `.env`.
- Modelos GGUF baixados sob demanda para reduzir o tamanho do instalador padrao.

## Principais Recursos

- Chat com LLM local.
- Entrada por voz com Whisper.
- Saida por voz com `edge-tts`.
- Anexos de PDF, DOCX, ODT, ODS, ODP, imagens e audio.
- RAG hibrido com ChromaDB, embeddings e BM25.
- Memoria semantica de longo prazo.
- Pesquisa e navegacao web.
- Execucao controlada de codigo em sandbox.
- Gerenciamento de estoque com interface Kanban.
- Geracao de relatorios em PDF/DOCX.
- Licenciamento com trial e chave de ativacao.

## Requisitos

- Windows 10/11.
- Python 3.10 ou superior.
- FFmpeg para audio.
- Git, se for clonar o repositorio.
- Inno Setup, apenas para gerar instalador.
- GPU compativel com Vulkan recomendada para melhor desempenho.

## Comeco Rapido

```powershell
git clone https://github.com/celso/celsius.git
cd celsius

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium

python main.py
```

Se o PowerShell bloquear a ativacao do ambiente virtual:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```

## Validacao Local

```powershell
python -m ruff check .
python -m pytest -q
```

Resultado validado localmente:

```text
438 passed, 3 skipped
All checks passed!
```

## Documentacao

- [Indice da documentacao](docs/README.md)
- [Guia do iniciante](docs/GUIA_INICIANTE.md)
- [Desenvolvimento](docs/DEVELOPMENT.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Configuracao](docs/CONFIGURATION.md)
- [Build e instalador](docs/BUILD.md)
- [Seguranca](SECURITY.md)
- [Contribuicao](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Estrutura Geral

```text
celsius/
|-- main.py                  # Entrada da aplicacao
|-- ai/                      # Motor de IA, RAG, agentes e ferramentas
|-- core/                    # Configuracao, modelos, memoria, sandbox e servicos
|-- processors/              # Leitura de arquivos e extracao de conteudo
|-- workers/                 # Threads de voz, IA, TTS e execucao assinc.
|-- ui/                      # Interface PySide6
|-- tests/                   # Testes automatizados
|-- scripts/                 # Scripts auxiliares
|-- tools/                   # Ferramentas operacionais, licencas
|-- installer/               # Build do instalador Windows
|-- resources/               # Modelos e recursos locais, ignorado no Git
|-- docs/                    # Documentacao do projeto
|-- .github/                 # CI, templates e configuracoes GitHub
`-- pyproject.toml           # Metadados, pytest, ruff, mypy e bandit
```

## Configuracao

Copie `.env.example` para `.env` quando quiser sobrescrever valores padrao:

```powershell
Copy-Item .env.example .env
```

As variaveis usam o prefixo `CELSIUS_`. Exemplo:

```env
CELSIUS_MODEL_LLM_MODEL=qwen2.5-vl-7b-q4km
CELSIUS_MODEL_NUM_CTX=16384
CELSIUS_TELEMETRY_ENABLED=false
```

Veja mais em [Configuracao](docs/CONFIGURATION.md).

## Build

Build local sem embutir modelos:

```powershell
pyinstaller celsius.spec --clean
```

Build com instalador:

```powershell
installer\build.bat
```

Veja detalhes em [Build e instalador](docs/BUILD.md).

## Licenca

MIT.
