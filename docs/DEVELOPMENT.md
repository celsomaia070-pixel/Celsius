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

- Runtime: `requirements.txt`.
- Desenvolvimento: `requirements-dev.in`.
- Metadados do pacote: `pyproject.toml`.

Ao adicionar dependencia nova, atualize o arquivo certo e rode os testes.

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
- `chroma_db/`
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
