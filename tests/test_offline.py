"""Regression tests proving the document pipeline and privacy-critical paths
stay strictly local: no socket, http or network call is allowed.

These tests block every known network entry point and verify the core flows
still complete successfully.
"""

from __future__ import annotations

import contextlib
import importlib
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NETWORK_MODULES = {
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
}

_BLOCKED_NAMES = {
    "socket": {"socket", "create_connection", "getaddrinfo", "socketpair"},
    "urllib.request": {"urlopen", "urlretrieve", "URLopener", "FancyURLopener"},
    "http.client": {"HTTPConnection", "HTTPSConnection"},
}


@contextlib.contextmanager
def _block_all_network():
    """Context manager that replaces network entry points with stubs that raise
    ``RuntimeError`` immediately.

    Any unexpected network use inside the ``with`` block is a test failure.

    The optional HTTP clients are loaded *before* ``http.client`` is patched so
    their own subclassing happens against the real classes.
    """
    originals: dict[tuple[str, str], Any] = {}

    def fake(*_args, **_kwargs):
        raise RuntimeError("RED FLAG: network call attempted in document pipeline / offline path")

    # Load optional HTTP clients first so their module-level subclassing uses
    # the real socket/http classes.
    for mod_name in _NETWORK_MODULES:
        with contextlib.suppress(ImportError):
            importlib.import_module(mod_name)

    try:
        for mod_name, attrs in _BLOCKED_NAMES.items():
            mod = importlib.import_module(mod_name)
            for attr in attrs:
                if hasattr(mod, attr):
                    originals[(mod_name, attr)] = getattr(mod, attr)
                    setattr(mod, attr, fake)

        # requests / urllib3 / httpx module-level conveniences
        for mod_name in _NETWORK_MODULES:
            try:
                mod = importlib.import_module(mod_name)
            except ImportError:
                continue
            for attr in ("request", "get", "post", "put", "delete", "head", "patch"):
                if hasattr(mod, attr):
                    originals[(mod_name, attr)] = getattr(mod, attr)
                    setattr(mod, attr, fake)
        yield
    finally:
        for (mod_name, attr), orig in originals.items():
            mod = importlib.import_module(mod_name)
            setattr(mod, attr, orig)


class _FakeEmbedder:
    """Lightweight stand-in for SentenceTransformer used only in tests."""

    def __init__(self, dim: int = 8):
        self.dim = dim

    def encode(self, texts: list[str], show_progress_bar: bool = False) -> np.ndarray:
        import hashlib
        import re

        vectors = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                seed = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16)
                vec[seed % self.dim] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.stack(vectors)


# ---------------------------------------------------------------------------
# Text processor
# ---------------------------------------------------------------------------


class TestTextProcessorOffline:
    def test_process_txt_without_network(self, tmp_path: Path):
        sample = tmp_path / "nota_fiscal.txt"
        sample.write_text("Item: caneta azul  Qtd: 12  Valor: R$ 3,50", encoding="utf-8")

        from processors import processar_arquivo

        with _block_all_network():
            result = processar_arquivo(str(sample), base_dir=tmp_path)

        assert "caneta azul" in result
        assert "R$ 3,50" in result


class TestDocxProcessorOffline:
    def test_process_docx_without_network(self, tmp_path: Path):
        try:
            from docx import Document as DocxDocument
        except ImportError:
            pytest.skip("python-docx not installed")

        sample = tmp_path / "contrato.docx"
        doc = DocxDocument()
        doc.add_paragraph("Clausula 1: O fornecedor se compromete a entregar 500 unidades.")
        doc.save(str(sample))

        from processors import processar_arquivo

        with _block_all_network():
            result = processar_arquivo(str(sample), base_dir=tmp_path)

        assert "fornecedor" in result.lower()
        assert "500 unidades" in result


# ---------------------------------------------------------------------------
# RAG indexing and search
# ---------------------------------------------------------------------------


class TestRAGOffline:
    @pytest.fixture
    def rag_service(self, tmp_path: Path, monkeypatch):
        """Create a RAGService with mocked embeddings and reranking disabled."""
        import ai.rag as rag_mod
        from core.circuit_breaker import get_circuit_breaker
        from core.settings import Settings

        for breaker_name in ("rag:search", "rag:index"):
            get_circuit_breaker(breaker_name).reset()

        fake_embedder = _FakeEmbedder(dim=8)
        monkeypatch.setattr(rag_mod, "create_sentence_transformer", lambda _name: fake_embedder)

        settings = Settings(
            base_dir=tmp_path,
            data_dir=tmp_path / "data",
        )
        settings.customer.local_offline_required = True

        svc = rag_mod.RAGService(settings=settings)
        svc._enable_reranking = False  # avoid loading CrossEncoder
        yield svc
        svc.close()
        for breaker_name in ("rag:search", "rag:index"):
            get_circuit_breaker(breaker_name).reset()

    def test_index_and_search_without_network(self, rag_service):
        text = (
            "Contrato de prestacao de servicos entre a empresa ABC Ltda e o fornecedor XYZ. "
            "O objeto deste contrato e a entrega mensal de materiais de escritorio. "
            "O valor total mensal e de R$ 4.500,00 com prazo de pagamento em 30 dias."
        )

        with _block_all_network():
            chunk_count = rag_service.index_document(text, "contrato_abc_xyz")
            results = rag_service.search_context("valor total do contrato")

        assert chunk_count > 0
        assert len(results) > 0
        assert any("4.500" in r for r in results)

    def test_list_documents_without_network(self, rag_service):
        rag_service.index_document("Documento teste", "doc_teste")

        with _block_all_network():
            listing = rag_service.list_documents()

        assert "doc_teste" in listing


# ---------------------------------------------------------------------------
# App context telemetry suppression
# ---------------------------------------------------------------------------


class TestAppContextOfflineMode:
    def test_bootstrap_logging_skips_telemetry_when_offline(self, tmp_path: Path, monkeypatch):
        """Telemetry must NOT be initialised when local_offline_required=True."""
        import core.app_context as ac_mod
        from core.settings import Settings

        call_tracker: dict[str, bool] = {"called": False}

        def _spy_init(**_kwargs):
            call_tracker["called"] = True

        monkeypatch.setattr(ac_mod, "setup_logging", lambda **_: None)
        monkeypatch.setattr(ac_mod, "enable_faulthandler", lambda *_a: None)
        monkeypatch.setattr(ac_mod, "init_telemetry", _spy_init)
        monkeypatch.setattr(ac_mod, "get_container", lambda: None)

        settings = Settings(
            base_dir=tmp_path,
            data_dir=tmp_path / "data",
        )
        settings.customer.local_offline_required = True
        settings.telemetry.enabled = True
        ac_mod.CelsiusAppContext(settings=settings)._bootstrap_logging(settings)

        assert call_tracker["called"] is False, (
            "init_telemetry was called despite local_offline_required=True"
        )

    def test_start_emits_offline_notice(self, tmp_path: Path, monkeypatch):
        """A clear offline-mode message must be logged when local_offline_required=True."""
        import core.app_context as ac_mod
        from core.app_context import CelsiusAppContext
        from core.settings import Settings

        reported: list[str] = []

        monkeypatch.setattr(ac_mod, "setup_logging", lambda **_: None)
        monkeypatch.setattr(ac_mod, "enable_faulthandler", lambda *_a: None)
        monkeypatch.setattr(ac_mod, "init_telemetry", lambda **_: None)
        monkeypatch.setattr(ac_mod, "get_container", lambda: None)
        monkeypatch.setattr(ac_mod, "shutdown_telemetry", lambda: None)
        monkeypatch.setattr(
            ac_mod,
            "start_for_settings",
            lambda *_a, **_kw: (MagicMock(stop=lambda: None), None),
        )
        monkeypatch.setattr(ac_mod, "get_mobile_runtime", lambda: MagicMock())
        monkeypatch.setattr(CelsiusAppContext, "_prepare_model", lambda self, _s: True)
        monkeypatch.setattr(
            CelsiusAppContext,
            "_start_web_server",
            lambda self, _s: setattr(self, "web_api_server", MagicMock(stop=lambda: None)),
        )

        settings = Settings(base_dir=tmp_path, data_dir=tmp_path / "data")
        settings.customer.local_offline_required = True
        settings.telemetry.enabled = True  # should be suppressed
        settings.hardware.auto_detect = False
        settings.mobile.enabled = False
        settings.features.multi_agent = False
        settings.features.voice_input = False
        monkeypatch.setattr(type(settings), "save_local_preferences", lambda self: None)

        ctx = CelsiusAppContext(settings=settings)

        class _StatusCollector:
            def __call__(self, msg: str) -> None:
                reported.append(msg)

        ctx._status = _StatusCollector()
        assert ctx.start() is True
        assert any("OFF-LINE" in msg.upper() for msg in reported), (
            f"Expected an OFF-LINE notice in startup messages, got: {reported}"
        )


# ---------------------------------------------------------------------------
# Security: base_dir always remains authorized
# ---------------------------------------------------------------------------


class TestSecurityBaseDirAlwaysAuthorized:
    def test_base_dir_still_readable_when_extra_roots_configured(self, tmp_path: Path, monkeypatch):
        """base_dir must never become inaccessible even when explicit roots are added."""
        import ai.tools
        from ai.tools import _validate_path
        from core.settings import SecuritySettings, Settings

        extra = tmp_path / "extra"
        extra.mkdir()
        file_in_base = tmp_path / "nota.txt"
        file_in_base.write_text("conteudo", encoding="utf-8")

        settings = Settings(
            base_dir=tmp_path,
            security=SecuritySettings(allowed_file_roots=(str(extra),)),
        )
        monkeypatch.setattr(ai.tools, "get_settings", lambda: settings)

        assert _validate_path(str(file_in_base)) == file_in_base.resolve()

    def test_explicit_root_file_accessible(self, tmp_path: Path, monkeypatch):
        """Files under an explicitly configured root must be readable."""
        import ai.tools
        from ai.tools import _validate_path
        from core.settings import SecuritySettings, Settings

        extra = tmp_path / "empresa"
        extra.mkdir()
        file_in_extra = extra / "relatorio.txt"
        file_in_extra.write_text("relatorio ok", encoding="utf-8")

        settings = Settings(
            base_dir=tmp_path / "base",
            security=SecuritySettings(allowed_file_roots=(str(extra),)),
        )
        monkeypatch.setattr(ai.tools, "get_settings", lambda: settings)

        assert _validate_path(str(file_in_extra)) == file_in_extra.resolve()

    def test_outside_roots_still_rejected(self, tmp_path: Path, monkeypatch):
        """Files outside both base_dir and configured roots remain denied."""
        import ai.tools
        from ai.tools import _validate_path
        from core.settings import SecuritySettings, Settings

        extra = tmp_path / "empresa"
        extra.mkdir()
        outside = tmp_path / "fora"
        outside.mkdir()
        secret = outside / "segredo.txt"
        secret.write_text("private", encoding="utf-8")

        settings = Settings(
            base_dir=tmp_path / "base",
            security=SecuritySettings(allowed_file_roots=(str(extra),)),
        )
        monkeypatch.setattr(ai.tools, "get_settings", lambda: settings)

        with pytest.raises(PermissionError):
            _validate_path(str(secret))
