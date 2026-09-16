"""Tests for best-effort protection of local private files."""

from __future__ import annotations

import subprocess

from core import file_security


def test_restrict_private_file_keeps_file_when_windows_identity_times_out(tmp_path, monkeypatch):
    path = tmp_path / "conversation.json"
    path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(file_security.os, "name", "nt")

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=5)

    monkeypatch.setattr(file_security.subprocess, "run", timed_out)

    assert file_security.restrict_private_file(path) is False
    assert path.read_text(encoding="utf-8") == "{}"


def test_restrict_private_file_reports_successful_windows_acl(tmp_path, monkeypatch):
    path = tmp_path / "conversation.json"
    path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(file_security.os, "name", "nt")
    responses = iter(
        (
            subprocess.CompletedProcess(["whoami"], 0, stdout="WORKGROUP\\celsius\n"),
            subprocess.CompletedProcess(["icacls"], 0, stdout="processed"),
        )
    )
    monkeypatch.setattr(file_security.subprocess, "run", lambda *args, **kwargs: next(responses))

    assert file_security.restrict_private_file(path) is True
