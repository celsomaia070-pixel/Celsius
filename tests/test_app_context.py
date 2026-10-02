"""Tests for the runtime bootstrap context used before the Qt window opens."""

import pytest

import core.app_context as app_context
from core.app_context import CelsiusAppContext
from core.sqlite_store import connect, init_schema


class _FakeServer:
    def stop(self):
        self.stopped = True


class _FakeRuntime:
    def __init__(self):
        self.attached = None
        self.closed = False
        self.command = lambda *_: None
        self.voice = lambda *_: None

    def attach(self, server):
        self.attached = server

    def close(self):
        self.closed = True


@pytest.fixture
def fake_runtime(monkeypatch):
    runtime = _FakeRuntime()

    monkeypatch.setattr(app_context, "setup_logging", lambda **_: None)
    monkeypatch.setattr(app_context, "init_telemetry", lambda **_: None)
    monkeypatch.setattr(app_context, "get_container", lambda: None)
    monkeypatch.setattr(app_context, "reset_container", lambda: None)
    monkeypatch.setattr(app_context, "shutdown_telemetry", lambda: None)
    monkeypatch.setattr(app_context, "start_for_settings", lambda *a, **k: (_FakeServer(), None))
    monkeypatch.setattr(app_context, "get_mobile_runtime", lambda: runtime)
    return runtime


@pytest.fixture
def settings(monkeypatch):
    from core.settings import get_settings

    settings = get_settings()
    settings.telemetry.enabled = False
    settings.hardware.auto_detect = False
    settings.mobile.enabled = False
    monkeypatch.setattr(type(settings), "save_local_preferences", lambda self: None)
    return settings


def _successful_context(monkeypatch, settings):
    def _prepare_model(self, _settings):
        return True

    def _start_web(self, _settings):
        self.web_api_server = _FakeServer()

    monkeypatch.setattr(CelsiusAppContext, "_prepare_model", _prepare_model)
    monkeypatch.setattr(CelsiusAppContext, "_start_web_server", _start_web)
    return CelsiusAppContext(settings=settings)


def test_start_success_and_clean_shutdown(monkeypatch, settings, fake_runtime):
    context = _successful_context(monkeypatch, settings)
    assert context.start() is True
    assert context._started is True
    assert context.failure_message is None

    context.shutdown()
    assert context.web_api_server.stopped is True


def test_refusing_model_download_fails_without_starting(monkeypatch, settings):
    def _prepare_model(self, _settings):
        self.failure_message = "download recusado"
        return False

    monkeypatch.setattr(CelsiusAppContext, "_prepare_model", _prepare_model)
    context = CelsiusAppContext(settings=settings, confirm_download=lambda *_: False)
    assert context.start() is False
    assert context.failure_message == "download recusado"


def test_start_exception_sets_failure_and_shuts_down(monkeypatch, settings, fake_runtime):
    settings.mobile.enabled = True

    def _boom(self, _settings):
        raise RuntimeError("boot falhou")

    monkeypatch.setattr(CelsiusAppContext, "_bootstrap_logging", _boom)
    context = CelsiusAppContext(settings=settings)
    assert context.start() is False
    assert "RuntimeError" in context.failure_message
    assert fake_runtime.closed is True


def test_start_mobile_attaches_server_and_rotates_token(monkeypatch, settings, fake_runtime):
    settings.mobile.enabled = True
    settings.mobile.pairing_token = ""
    settings.mobile.pairing_token_issued_at = ""

    context = _successful_context(monkeypatch, settings)

    assert context.start() is True
    assert fake_runtime.attached is not None
    assert settings.mobile.pairing_token
    assert settings.mobile.pairing_token_issued_at


def test_shutdown_backs_up_databases(monkeypatch, settings, fake_runtime, tmp_path):
    settings.inventory_file = tmp_path / "inventory.json"
    settings.memorias_file = tmp_path / "memorias.json"
    for json_path in (settings.inventory_file, settings.memorias_file):
        with connect(json_path) as conn:
            init_schema(conn)

    monkeypatch.setattr(app_context, "_SKIP_BACKUP_UNDER_PYTEST", False)
    context = _successful_context(monkeypatch, settings)
    context.start()
    context.shutdown()

    assert (tmp_path / "backups").is_dir()
    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 2


def test_prepare_model_uses_profile_runtime_kwargs(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from core.model_router import get_model_profile

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"gguf")
    settings = SimpleNamespace(
        get_model_path=lambda _mid: model_file,
        get_mmproj_path=lambda _mid: None,
        model=SimpleNamespace(
            llm_model="qwen2.5-vl-7b-q4km",
            num_ctx=2048,
            n_gpu_layers=0,
            n_batch=512,
            n_threads=4,
        ),
    )

    captured = {}
    monkeypatch.setattr(app_context, "_ensure_model_available", lambda *a, **k: None)
    monkeypatch.setattr(
        app_context,
        "start_llama_server",
        lambda **kwargs: captured.update(kwargs) or True,
    )
    import core.config as config_module

    monkeypatch.setattr(
        config_module,
        "get_model_by_id",
        lambda _mid: SimpleNamespace(has_mmproj=False),
    )

    ctx = CelsiusAppContext.__new__(CelsiusAppContext)
    ctx._confirm_download = None
    ctx.report = lambda *_: None
    ctx._llama_started = False

    assert ctx._prepare_model(settings) is True

    profile = get_model_profile("qwen2.5-vl-7b-q4km")
    assert captured["n_ctx"] == profile.default_n_ctx
    assert captured["n_gpu_layers"] == profile.default_n_gpu_layers


def test_prepare_model_falls_back_to_settings_for_unknown_model(monkeypatch, tmp_path):
    from types import SimpleNamespace

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"gguf")
    settings = SimpleNamespace(
        get_model_path=lambda _mid: model_file,
        get_mmproj_path=lambda _mid: None,
        model=SimpleNamespace(
            llm_model="modelo-desconhecido",
            num_ctx=2048,
            n_gpu_layers=0,
            n_batch=512,
            n_threads=4,
        ),
    )

    captured = {}
    monkeypatch.setattr(app_context, "_ensure_model_available", lambda *a, **k: None)
    monkeypatch.setattr(
        app_context,
        "start_llama_server",
        lambda **kwargs: captured.update(kwargs) or True,
    )
    import core.config as config_module
    import core.model_router as model_router_module

    monkeypatch.setattr(
        config_module,
        "get_model_by_id",
        lambda _mid: SimpleNamespace(has_mmproj=False),
    )
    monkeypatch.setattr(model_router_module, "get_settings", lambda: settings)

    ctx = CelsiusAppContext.__new__(CelsiusAppContext)
    ctx._confirm_download = None
    ctx.report = lambda *_: None
    ctx._llama_started = False

    assert ctx._prepare_model(settings) is True
    assert captured["n_ctx"] == 2048
    assert captured["n_gpu_layers"] == 0
