# Test configuration and fixtures
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import contextlib
import os
import tempfile

# ---------------------------------------------------------------------------
# Test isolation.
#
# These must be set at *import* time, before any `core.*` module is imported:
# `core.settings` builds its process-wide settings singleton on first import and
# would otherwise load the developer's real `data/celsius_settings.json`, which
# silently pins tests to whatever model this machine happens to use.
#
# The production code honours these same overrides (see
# `Settings.local_preferences_file` and `default_outcomes_path`), so tests never
# read or write real user data.
# ---------------------------------------------------------------------------

_TEST_ISOLATION_DIR = tempfile.mkdtemp(prefix="celsius-tests-")

# The user's real data/celsius_settings.json pins whatever model this machine
# uses, which made router tests machine-dependent. Pointing the preferences file
# at an empty temp file is enough: Settings then falls back to its documented
# defaults. The model is deliberately NOT forced via env, because env must keep
# winning over the file for every other test (see test_save_and_load_model_pin).
os.environ.setdefault(
    "CELSIUS_PREFERENCES_FILE", str(Path(_TEST_ISOLATION_DIR) / "celsius_settings.json")
)
os.environ.setdefault(
    "CELSIUS_CUSTOMER_PROFILE_FILE", str(Path(_TEST_ISOLATION_DIR) / "customer_profile.json")
)

# The decision layer is exercised explicitly in tests/test_decisions.py; keep it
# off by default so no test depends on a running kev.serve.
os.environ.setdefault("CELSIUS_DECISION_ENABLED", "false")
os.environ.setdefault("CELSIUS_DECISION__ENABLED", "false")

# No telemetry from the test run.
os.environ.setdefault("CELSIUS_TELEMETRY_ENABLED", "false")

# Check if PySide6 is properly installed (not just a mock)
_PYSIDE6_AVAILABLE = False
with contextlib.suppress(Exception):
    _PYSIDE6_AVAILABLE = True

# ---------------------------------------------------------------------------
# Mock heavy dependencies that core/__init__.py and core/container.py pull in.
# These must be injected BEFORE any `core.*` import triggers the chain.
# ---------------------------------------------------------------------------

_HEAVY_MODULES = [
    # Unix-only module
    "resource",
    # PySide6 — only mock if not properly installed
    # "PySide6", "PySide6.QtCore", "PySide6.QtWidgets", "PySide6.QtGui",
    # "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    # llama-cpp
    "llama_cpp",
    # opentelemetry
    "opentelemetry",
    "opentelemetry.trace",
    "opentelemetry.metrics",
    "opentelemetry.sdk",
    "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export",
    "opentelemetry.sdk.metrics",
    "opentelemetry.sdk.metrics.export",
    "opentelemetry.sdk.resources",
    "opentelemetry.exporter",
    "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto",
    "opentelemetry.exporter.otlp.proto.grpc",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.exporter.otlp.proto.grpc.metric_exporter",
    "opentelemetry.instrumentation",
    "opentelemetry.instrumentation.logging",
    "opentelemetry.instrumentation.requests",
    "opentelemetry.instrumentation.urllib",
    "opentelemetry.instrumentation.httpx",
    "opentelemetry.instrumentation.aiohttp_client",
    "opentelemetry.semconv",
    "opentelemetry.semconv.trace",
    # structlog
    "structlog",
    # Speech / audio
    "speech_recognition",
    "sounddevice",
    "whisper",
    "pydub",
    "pygame",
    "edge_tts",
    # ML / AI
    "transformers",
    # Other heavy deps
    "openai",
    "playwright",
    "feedparser",
    # project modules that have heavy deps in their init
    "core.llama_cpp",
    "core.rag",
    "ai.agents",
    "ai.browser",
    "workers.mic_worker",
    "workers.tts_worker",
    "workers.code_worker",
    "workers.windows_sandbox",
]

for _mod_name in _HEAVY_MODULES:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Give core.llama_cpp the names that __init__.py expects
_llama = sys.modules["core.llama_cpp"]
_llama.get_llama = MagicMock()
_llama.get_llama_client_config = MagicMock()
_llama.start_llama_server = MagicMock()
_llama.stop_llama_server = MagicMock()
_llama.switch_llama_model = MagicMock()
_llama.LlamaManager = type("LlamaManager", (), {})
_llama.MultiModelManager = type("MultiModelManager", (), {})
_llama.ModelRouter = type("ModelRouter", (), {})



_core_rag = sys.modules["core.rag"]
_core_rag.RAGService = type("RAGService", (), {})

_container_mod = sys.modules.get("core.container")
if _container_mod is not None and hasattr(_container_mod, "get_container"):
    pass
else:
    _container_mod = MagicMock()
    _container_mod.get_container = MagicMock()
    _container_mod.reset_container = MagicMock()
    sys.modules["core.container"] = _container_mod

_code_worker = sys.modules["workers.code_worker"]
_code_worker.executar_codigo = MagicMock()
_code_worker.CodeWorker = type("CodeWorker", (), {})


@pytest.fixture(scope="session")
def settings():
    from core.config import get_settings

    return get_settings()


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory for tests."""
    return tmp_path


def pytest_collection_modifyitems(config, items):
    """Skip UI tests when PySide6 is not properly installed."""
    if not _PYSIDE6_AVAILABLE:
        skip_pyside = pytest.mark.skip(reason="PySide6 not properly installed")
        for item in items:
            if "test_ui" in str(item.fspath):
                item.add_marker(skip_pyside)
