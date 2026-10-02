"""Tests for the post-load warm-up on LlamaManager."""

import importlib.util
import sys
import threading
import time
from pathlib import Path

import pytest


def _load_real_llama_cpp():
    """Load the real core.llama_cpp module under an alias.

    The test session conftest pre-populates ``sys.modules["core.llama_cpp"]``
    and ``sys.modules["llama_cpp"]`` with MagicMock stubs, so importing the
    real class through the normal path is impossible. Loading the source file
    under a distinct name keeps the real ``LlamaManager`` available while the
    mocks stay untouched for the rest of the session.
    """
    saved = {}
    for name in ("llama_cpp", "core.llama_cpp"):
        if name in sys.modules:
            saved[name] = sys.modules[name]
            del sys.modules[name]
    try:
        path = Path(__file__).resolve().parent.parent / "core" / "llama_cpp.py"
        spec = importlib.util.spec_from_file_location("_llama_cpp_real", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        for name, value in saved.items():
            sys.modules[name] = value


_REAL = None


@pytest.fixture
def real_llama_cpp():
    global _REAL
    if _REAL is None:
        _REAL = _load_real_llama_cpp()
    return _REAL


class _FakeLLM:
    def __init__(self):
        self.completions = []

    def create_chat_completion(self, messages=None, max_tokens=1, temperature=0.0, **_kwargs):
        self.completions.append(
            {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        )
        return {"choices": [{"message": {"content": "ok"}}]}


def _make_manager(
    real_llama_cpp, *, started=True, llm=None, warm_up_on_load=True, monkeypatch=None
):
    manager = real_llama_cpp.LlamaManager.__new__(real_llama_cpp.LlamaManager)
    manager._started = started
    manager._llm = llm
    manager._inference_lock = threading.Lock()

    settings_fake = type("Model", (), {"warm_up_on_load": warm_up_on_load})()
    settings_container = type("Settings", (), {"model": settings_fake})()
    if monkeypatch is not None:
        monkeypatch.setattr(real_llama_cpp, "get_settings", lambda: settings_container)
    return manager


def test_warm_up_runs_short_completion_in_background(real_llama_cpp, monkeypatch):
    llm = _FakeLLM()
    manager = _make_manager(real_llama_cpp, llm=llm, monkeypatch=monkeypatch)
    manager._warm_up_async("qwen-heretic-q4km")

    deadline = time.time() + 5
    while not llm.completions and time.time() < deadline:
        time.sleep(0.01)

    assert llm.completions
    call = llm.completions[0]
    assert call["max_tokens"] == 1
    assert call["temperature"] == 0.0
    assert "Celsius" in call["messages"][0]["content"]


def test_warm_up_skipped_when_disabled(real_llama_cpp, monkeypatch):
    llm = _FakeLLM()
    manager = _make_manager(real_llama_cpp, llm=llm, warm_up_on_load=False, monkeypatch=monkeypatch)
    manager._warm_up_async("qwen-heretic-q4km")
    time.sleep(0.05)

    assert llm.completions == []


def test_warm_up_skipped_when_model_unloaded(real_llama_cpp, monkeypatch):
    manager = _make_manager(real_llama_cpp, started=True, llm=None, monkeypatch=monkeypatch)
    manager._warm_up_async("qwen-heretic-q4km")  # must not raise
    time.sleep(0.05)
    assert True


def test_warm_up_does_not_raise_on_failure(real_llama_cpp, monkeypatch):
    class _BoomLLM:
        def create_chat_completion(self, **_kwargs):
            raise RuntimeError("simulated warm-up failure")

    manager = _make_manager(real_llama_cpp, llm=_BoomLLM(), monkeypatch=monkeypatch)
    manager._warm_up_async("qwen-heretic-q4km")  # must not raise
    time.sleep(0.05)
    assert True
