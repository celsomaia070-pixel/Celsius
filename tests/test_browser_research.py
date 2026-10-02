"""Actual browser module: static retrieval, cancellation and fallback cleanup."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import web_research
from core.operation_control import OperationCancelled, bind_control


@pytest.fixture
def browser_module(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "ai/browser.py"
    spec = importlib.util.spec_from_file_location("browser_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "validate_public_http_url", lambda url: url)
    monkeypatch.setattr(
        module,
        "_browser_navigate_cb",
        SimpleNamespace(
            allow_request=lambda: True,
            record_success=Mock(),
            record_failure=Mock(),
        ),
    )
    return module


def test_static_web_content_needs_no_browser(browser_module, monkeypatch):
    monkeypatch.setattr(
        web_research,
        "fetch_public",
        lambda *a, **k: (
            "https://example.org/page",
            b"<h1>Verified content</h1>" + b" facts" * 30,
        ),
    )
    monkeypatch.setattr(
        browser_module.BrowserAgent, "start", Mock(side_effect=AssertionError("browser started"))
    )
    result = browser_module.navegar_web("https://example.org/page")
    assert "[FONTE_WEB]" in result and "Verified content" in result
    assert "<h1>" not in result


def test_web_cancellation_is_not_converted_to_error(browser_module):
    with bind_control(lambda: True), pytest.raises(OperationCancelled):
        browser_module.navegar_web("https://example.org/page")


def test_browser_is_stopped_after_navigation_failure(browser_module, monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("navigation failed")

    async def start(self, **kwargs):
        self._page = SimpleNamespace(goto=fail)

    stopped = []

    async def stop(self):
        stopped.append(True)

    monkeypatch.setattr(web_research, "fetch_public", Mock(side_effect=OSError("HTTP failed")))
    monkeypatch.setattr(browser_module.BrowserAgent, "start", start)
    monkeypatch.setattr(browser_module.BrowserAgent, "stop", stop)
    result = browser_module.navegar_web("https://example.org/page")
    assert "Erro ao navegar" in result
    assert stopped == [True]
    browser_module._browser_navigate_cb.record_failure.assert_called_once()


async def test_missing_downloaded_browser_uses_installed_edge(browser_module, monkeypatch):
    import sys
    from unittest.mock import AsyncMock

    context = SimpleNamespace(route=AsyncMock(), new_page=AsyncMock(return_value=object()))
    native_browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
    chromium = SimpleNamespace(
        launch=AsyncMock(
            side_effect=[
                RuntimeError("Executable doesn't exist"),
                native_browser,
            ]
        )
    )
    driver = SimpleNamespace(chromium=chromium, stop=AsyncMock())
    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        SimpleNamespace(
            Error=RuntimeError,
            async_playwright=lambda: SimpleNamespace(start=AsyncMock(return_value=driver)),
        ),
    )
    agent = browser_module.BrowserAgent()
    try:
        await agent.start()
        assert chromium.launch.call_args_list[1].kwargs == {"channel": "msedge", "headless": True}
        context.route.assert_awaited_once()
    finally:
        await agent.stop()
