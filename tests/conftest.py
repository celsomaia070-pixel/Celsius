# Test configuration and fixtures
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import contextlib

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
    "sentence_transformers",
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

# Mock sentence_transformers.SentenceTransformer to return numpy-like embeddings
_st = sys.modules["sentence_transformers"]
import numpy as _np

_mock_encoder = MagicMock()
_mock_encoder.encode = MagicMock(
    side_effect=lambda texts: [_np.random.randn(384).astype(_np.float32) for _ in texts]
)
_st.SentenceTransformer = MagicMock(return_value=_mock_encoder)

_core_rag = sys.modules["core.rag"]
_core_rag.RAGService = type("RAGService", (), {})

_inventory_mod = sys.modules.get("core.inventory")
if _inventory_mod is not None and hasattr(_inventory_mod, "InventoryService"):
    pass
else:
    _inventory_mod = MagicMock()
    _inventory_mod.InventoryService = type("InventoryService", (), {})
    sys.modules["core.inventory"] = _inventory_mod

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
