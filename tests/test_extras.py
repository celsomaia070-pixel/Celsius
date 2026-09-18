import tomllib
from importlib.util import find_spec

import pytest

from core.extras import (
    EXTRA_PROBES,
    INSTALL_HINTS,
    feature_notice_lines,
    install_hint,
    is_extra_available,
    missing_extras,
    missing_modules,
)
from tools.sync_requirements import APP_EXTRA_GROUPS


@pytest.mark.parametrize("extra", ("docker", "documents", "voice", "web"))
def test_extra_groups_declared_in_pyproject(extra):
    with open("pyproject.toml", "rb") as handle:
        extras = tomllib.load(handle)["project"]["optional-dependencies"]
    assert extra in extras
    assert extras[extra]


def test_probe_every_runtime_extra_has_probes_and_hint():
    for extra in APP_EXTRA_GROUPS:
        assert EXTRA_PROBES[extra]
        assert INSTALL_HINTS[extra]


def test_missing_modules_available(monkeypatch):
    monkeypatch.setattr("core.extras.find_spec", lambda name: object())
    for extra in APP_EXTRA_GROUPS:
        assert missing_modules(extra) == ()
        assert is_extra_available(extra)
    assert not missing_modules("nope")


def test_missing_modules_unavailable(monkeypatch):
    monkeypatch.setattr("core.extras.find_spec", lambda name: None)
    for extra in APP_EXTRA_GROUPS:
        assert missing_modules(extra) == EXTRA_PROBES[extra]
        assert not is_extra_available(extra)


def test_unknown_extra_treated_as_missing_without_crash():
    assert missing_modules("nope") == ()
    assert not is_extra_available("nope")
    assert install_hint("nope") == "pip install celsius[nope]"


def test_find_spec_uncached_on_import_error(monkeypatch):
    calls = {"count": 0}

    def flaky_spec(name):
        calls["count"] += 1
        raise ImportError("simulated")

    monkeypatch.setattr("core.extras.find_spec", flaky_spec)
    assert not is_extra_available("docker")
    assert calls["count"] >= len(EXTRA_PROBES["docker"])


def test_missing_extras_lists_unavailable_groups(monkeypatch):
    monkeypatch.setattr("core.extras.find_spec", lambda name: None)
    missing = missing_extras()
    assert "docker" in missing
    assert "documents" in missing


def test_feature_notice_lines_contain_hints(monkeypatch):
    monkeypatch.setattr("core.extras.find_spec", lambda name: None)
    lines = feature_notice_lines()
    assert len(lines) == len(APP_EXTRA_GROUPS)
    prefixes = {f"{extra}:" for extra in APP_EXTRA_GROUPS}
    for line in lines:
        assert any(line.startswith(prefix) for prefix in prefixes)
        assert "pip install" in line
