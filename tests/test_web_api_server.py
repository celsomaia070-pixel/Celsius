"""Tests for the local web server network boundary."""

from types import SimpleNamespace

import pytest

from core.web_api import server as server_module


def _settings(*, mobile_lan: bool = False):
    return SimpleNamespace(
        web=SimpleNamespace(host="127.0.0.1"),
        mobile=SimpleNamespace(enabled=mobile_lan, allow_lan=mobile_lan),
    )


def test_desktop_web_stays_on_loopback_when_mobile_lan_is_enabled(monkeypatch):
    monkeypatch.setattr(server_module, "create_app", lambda **kwargs: object())

    server = server_module.LocalWebApiServer(settings=_settings(mobile_lan=True))

    assert server.host == "127.0.0.1"
    assert server.url == "http://127.0.0.1:8790"
    assert server.use_https is False


def test_lan_web_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(server_module, "create_app", lambda **kwargs: object())

    with pytest.raises(ValueError, match="allow_lan=True"):
        server_module.LocalWebApiServer(
            host="0.0.0.0",
            settings=_settings(),
        )
