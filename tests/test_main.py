"""Tests for the lightweight executable bootstrap."""

import json

from main import _enable_faulthandler, _safe_print, _write_self_test_report


def test_writes_self_test_report(tmp_path):
    report_path = tmp_path / "logs" / "self-test.json"

    result_path = _write_self_test_report(
        {"ok": False, "step": "importing example"},
        report_path=report_path,
    )

    assert result_path == report_path
    assert json.loads(report_path.read_text(encoding="utf-8")) == {
        "ok": False,
        "step": "importing example",
    }


def test_safe_print_accepts_windowed_runtime_without_stdout(monkeypatch):
    monkeypatch.setattr("sys.stdout", None)

    _safe_print("sem console")


def test_faulthandler_accepts_windowed_runtime_without_stderr(monkeypatch):
    calls = []
    monkeypatch.setattr("sys.stderr", None)
    monkeypatch.setattr("faulthandler.is_enabled", lambda: False)
    monkeypatch.setattr("faulthandler.enable", lambda **kwargs: calls.append(kwargs))

    _enable_faulthandler()

    assert calls == []
