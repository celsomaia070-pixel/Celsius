# AGENTS.md

## Project Overview

Celsius is a local multimodal AI desktop assistant for Windows, built with Python 3.10+ and PySide6. It runs GGUF models locally via `llama-cpp-python` with GPU support and CPU fallback. All document processing, RAG, and inference are 100% local — no network calls in the core pipeline.

## Commands

```powershell
# Setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.in
python -m playwright install chromium

# Run
python main.py

# Lint & Format
python -m ruff check .
python -m ruff format --check .
python -m ruff format .
python -m ruff check . --fix

# Typecheck
python -m mypy core/ workers/ ai/

# Tests
python -m pytest -q
python -m pytest tests/test_settings.py -q
python -m pytest tests/test_settings.py::TestClass::test_name -q

# Coverage
python -m pytest -q --cov=core --cov=ai --cov=workers --cov=ui --cov-report=term
python -m coverage report --fail-under=50 --skip-empty

# Security
python -m pip-audit --strict
python -m bandit -r core/ ai/ workers/ ui/

# Dependency management (pyproject.toml is the source of truth)
python tools\sync_requirements.py
python tools\sync_requirements.py --check
python tools\lock_requirements.py
python tools\lock_requirements.py --check
```

## Architecture

```
ui/          -> PySide6 GUI (window, chat, kanban, task_panel, theme)
workers/     -> Background threads (AI, TTS, mic, code execution)
ai/          -> LLM engine, RAG, tools, agents, browser, multi-agent
core/        -> Settings, models, memory, sandbox, persistence, security
processors/  -> File reading (PDF, DOCX, ODF, XLSX, images, audio)
tests/       -> pytest suite
scripts/     -> Utilities and integration smoke tests
tools/       -> Operational tools (license, requirements sync)
installer/   -> Windows installer build (Inno Setup)
```

### Key Patterns

- **Lazy imports**: Optional dependencies (documents, voice, web, docker) are imported lazily. `core/extras.py` detects missing extras at runtime.
- **Atomic writes**: JSON persistence uses temp file + `fsync` + `os.replace` (`core/json_persistence.py`).
- **SQLite with WAL**: Shared store with cross-process locking (`core/sqlite_store.py`).
- **Worker pattern**: Heavy tasks run in `workers/` threads; UI stays responsive via Qt signals.
- **Agentic modes**: 6 modes in `core/agent_modes.py` (assistente, executor, documentos, estoque, pesquisador, desenvolvedor). Task lifecycle: `created -> planning -> waiting_confirmation -> running -> paused -> cancelled/failed/completed`.
- **Security**: `core/file_security.py` (path validation, allowed roots), `core/tool_policy.py` (allowlist per mode, risk levels), `core/audit_log.py` (JSONL audit trail).
- **Settings**: Pydantic-based config in `core/settings.py`, env vars prefixed `CELSIUS_`.

## Code Style

- Python 3.10+, line length 100
- Ruff for linting and formatting (see `pyproject.toml`)
- Type hints encouraged; mypy configured but not strict
- No comments unless the "why" is non-obvious
- Commit messages: short, lowercase, conventional format (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`)

## Testing

- pytest with `pytest-qt`, `pytest-asyncio`, `pytest-mock`, `pytest-xdist`
- `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`
- Markers: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.unit`
- `tests/conftest.py` isolates `CELSIUS_PREFERENCES_FILE` and `CELSIUS_CUSTOMER_PROFILE_FILE` to temp dirs
- Expected: ~1134 passed, 3 skipped
- Coverage minimum: 50%

## What NOT to Commit

`.venv/`, `build/`, `dist/`, `resources/`, `cache/`, `logs/`, `data/`, `voices/`, `*.db`, `*.db.lock`, `*.gguf`, `*.pem`, `licenses.json`, `*.embeddings_cache.npy`, `conversations/`, `keys/`

## Critical Invariants

1. **Offline-first**: Document processing, RAG, and inference must never make network calls. `tests/test_offline.py` enforces this.
2. **UI responsiveness**: Never block the Qt main thread. Use workers for anything >100ms.
3. **Path safety**: All file access must go through `core/file_security.py` with allowed roots.
4. **Write confirmation**: Destructive tools require explicit human approval (`core/tool_approval.py`).
5. **Atomic persistence**: Never write JSON/SQLite directly — always use the provided atomic helpers.
