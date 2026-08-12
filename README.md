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
- Perfil empresarial local com modulos configuraveis por cliente.
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
- Cadastro local de fornecedores.
- Sidebar dinamica por modulos da empresa.
- Base de acesso local pelo celular, com token e comandos por texto/voz.
- Geracao de relatorios em PDF/DOCX.
- Licenciamento com trial e chave de ativacao.

## Modulos por Empresa

O Celsius pode ser configurado por perfil de empresa. Em `Configuracoes`, a area
`Modulos da empresa` permite ativar apenas os recursos relevantes para cada
cliente. `Chat` e `Configuracoes` permanecem sempre ativos; os demais modulos
podem ser ligados ou desligados sem alterar codigo.

No primeiro uso, o assistente de configuracao pergunta nome, segmento, descricao
e necessidades principais da empresa, sugere uma selecao inicial de modulos e
salva tudo localmente em `data/customer_profile.json` e
`data/celsius_settings.json`.

## Acesso Pelo Celular

O Celsius pode expor uma interface local para celulares na mesma rede Wi-Fi. O
recurso fica desligado por padrao e usa token de pareamento. Em `Configuracoes`,
use a secao `Celular` para ativar o acesso e clique em `Parear celular`. O
Celsius inicia o acesso local e abre uma janela com QR Code e link de pareamento.
O botao `Regenerar token` invalida links antigos e cria um novo pareamento.

O painel mobile aceita comandos digitados e gravacao de voz enviada ao PC para
transcricao local pelo Celsius. O audio e otimizado no navegador como WAV mono em
16 kHz antes do envio. A resposta do Celsius volta para o celular em texto e pode
ser reproduzida pela voz nativa do navegador. Por padrao, o acesso usa HTTPS
local com certificado autoassinado gerado em `data/mobile_access`. No primeiro
acesso, o celular pode pedir confirmacao de seguranca para esse certificado
local. Se HTTPS for desligado, alguns navegadores podem bloquear o microfone.

## Requisitos

- Windows 10/11.
- Python 3.10 ou superior.
- FFmpeg para audio.
- Git, se for clonar o repositorio.
- Inno Setup, apenas para gerar instalador.
- GPU compativel com Vulkan recomendada para melhor desempenho.

## Comeco Rapido

```powershell
git clone https://github.com/celsomaia070-pixel/Celsius.git
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

O total de testes evolui junto com o produto. A execucao e considerada valida
quando ambos os comandos terminam sem erros; o CI repete essa verificacao em
Windows e Linux.

## Documentacao

- [Indice da documentacao](docs/README.md)
- [Guia do iniciante](docs/GUIA_INICIANTE.md)
- [Desenvolvimento](docs/DEVELOPMENT.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Configuracao](docs/CONFIGURATION.md)
- [Privacidade e protecao de dados](docs/PRIVACY.md)
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
