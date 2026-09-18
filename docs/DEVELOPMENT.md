# Desenvolvimento

Este guia descreve o fluxo recomendado para alterar o projeto com seguranca.

## Preparar Ambiente

```powershell
cd E:\PythonProjectCELSIUS
python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.in
python -m playwright install chromium
```

## Rodar Localmente

```powershell
python main.py
```

## Validar Antes de Commitar

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

Para formatar automaticamente:

```powershell
python -m ruff format .
python -m ruff check . --fix
```

## Testes

Rodar tudo:

```powershell
python -m pytest -q
```

Rodar um arquivo:

```powershell
python -m pytest tests\test_settings.py -q
```

Rodar um teste especifico:

```powershell
python -m pytest tests\test_settings.py::TestTelemetrySettingsDefaults::test_enabled -q
```

## Organizacao de Codigo

- `core/`: regras centrais, configuracao, persistencia e servicos.
- `ai/`: comportamento da IA e ferramentas.
- `processors/`: leitura de arquivos.
- `workers/`: tarefas em background.
- `ui/`: interface grafica.
- `tests/`: cobertura automatizada.

Ao adicionar uma funcionalidade:

1. Coloque regra compartilhada em `core/`.
2. Coloque comportamento de IA em `ai/`.
3. Coloque processamento de arquivo em `processors/`.
4. Coloque tarefas demoradas em `workers/`.
5. Exponha na interface em `ui/`.
6. Adicione ou atualize testes.

## Dependencias

`pyproject.toml` e a unica fonte editavel das dependencias. Os arquivos
`requirements.in`, `requirements.txt` e `requirements-dev.in` existem para
compatibilidade com instaladores e sao gerados automaticamente.

As dependencias de runtime sao separadas por extras opcionais em
`[project.optional-dependencies]`:

- `documents`, `voice`, `web`, `docker`: funcionalidades opcionais.
- `all`: union de todas acima.
- `dev`, `test`, `security`: ferramentas de desenvolvimento.

A instalacao base (`pip install celsius`) fica leve; os arquivos
`requirements.in`/`requirements.txt` gerados continuam incluindo o conjunto
completo (base + extras de aplicacao), de modo que desenvolvimento, CI e o
instalador se comportam como antes.

Ao adicionar ou atualizar uma dependencia:

```powershell
python tools\sync_requirements.py
python tools\sync_requirements.py --check
```

Dependencias opcionais sao importadas de forma lazy pelos modulos que as usam.
Ao criar um extra novo, inclua suas sondas em `core/extras.py` para que a UI
possa orientar o usuario a instalar o grupo faltante.

O CI falha quando esses arquivos ficam diferentes do `pyproject.toml`, e quando
o `pylock.toml` (bloqueio PEP 751) estiver desatualizado. Após mudar o
`requirements.in`, regenere o lock com:

```powershell
python tools\lock_requirements.py
python tools\lock_requirements.py --check
```

## CI (GitHub Actions)

`.github/workflows/ci.yml` cobre, além de Lint/Format e manifestos:

- **Testes** em `ubuntu` e `windows` com Python 3.10/3.12/3.14, com cache de pip
  apontando para `requirements.txt`, `pylock.toml` e `requirements-dev.in`, e
  medindo cobertura (`--cov=core --cov=ai --cov=workers --cov=ui`); o relatório
  é publicado como artefato e a cobertura mínima é aplicada
  (`coverage report --fail-under=50`).
- **Typecheck** (`mypy core/ workers/ ai/`) com cache `.mypy_cache` persistido
  entre execuções.
- **Security** (`pip-audit --strict` e `bandit`).
- **Native smoke** (`pytest integration_tests --run-native-smoke`) que valida o
  arranque real do `main.py` em um processo filho, sem modelo local.

Para rodar localmente a mesma checagem de cobertura:

```powershell
python -m pytest -q --cov=core --cov=ai --cov=workers --cov=ui --cov-report=term
python -m coverage report --fail-under=50 --skip-empty
```

## Git

Antes de abrir PR ou fazer commit:

```powershell
git status --short
python -m ruff check .
python -m pytest -q
```

Nao commite:

- `.venv/`
- `venv/`
- `build/`
- `dist/`
- `resources/`
- `cache/`
- `rag_vectors.sqlite3*`
- `conversations/`
- `logs/`
- `keys/`
- `licenses.json`
- arquivos `.gguf`
- arquivos `.pem`

## Padrao de Commit

Use mensagens curtas e objetivas:

```text
docs: reorganiza documentacao
fix: corrige persistencia atomica
test: adiciona cobertura do sandbox
ci: ajusta workflow de testes
```
