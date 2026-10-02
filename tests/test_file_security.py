"""Tests for best-effort protection of local private files."""

from __future__ import annotations

import pytest
import subprocess

from core import file_security
from core.file_security import (
    validate_path,
    set_allowed_roots,
    get_allowed_roots,
    require_write_confirmation,
)


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


def test_restrict_private_directory_uses_inheritable_windows_acl(tmp_path, monkeypatch):
    path = tmp_path / "private-cache"
    monkeypatch.setattr(file_security.os, "name", "nt")
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        if command[0] == "whoami":
            return subprocess.CompletedProcess(command, 0, stdout="WORKGROUP\\celsius\n")
        return subprocess.CompletedProcess(command, 0, stdout="processed")

    monkeypatch.setattr(file_security.subprocess, "run", run)
    assert file_security.restrict_private_directory(path) is True
    assert path.is_dir()
    assert "WORKGROUP\\celsius:(OI)(CI)F" in calls[-1]


def test_restrict_private_directory_does_not_recurse_into_children(tmp_path, monkeypatch):
    # "/T" applies "/inheritance:r" to child files while "(OI)(CI)F" is only valid on
    # directories, so icacls leaves those files with no ACE and nothing can read them.
    path = tmp_path / "data"
    monkeypatch.setattr(file_security.os, "name", "nt")
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        if command[0] == "whoami":
            return subprocess.CompletedProcess(command, 0, stdout="WORKGROUP\\celsius\n")
        return subprocess.CompletedProcess(command, 0, stdout="processed")

    monkeypatch.setattr(file_security.subprocess, "run", run)
    assert file_security.restrict_private_directory(path) is True
    assert "/T" not in calls[-1]
    assert "/C" not in calls[-1]


class TestPathValidation:
    def test_validate_path_within_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_allowed_roots([])
        path = tmp_path / "subdir" / "file.txt"
        path.parent.mkdir()
        path.write_text("ok")
        validated = validate_path(path)
        assert validated == path.resolve()

    def test_validate_path_traversal_blocked(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_allowed_roots([])
        with pytest.raises(PermissionError) as exc_info:
            validate_path("../etc/passwd")
        assert "fora do diretório" in str(exc_info.value).lower()

    def test_validate_path_outside_allowed_roots(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_allowed_roots([tmp_path / "allowed"])
        (tmp_path / "allowed").mkdir()
        outside = tmp_path / "outside" / "file.txt"
        outside.parent.mkdir()
        outside.write_text("x")
        with pytest.raises(PermissionError) as exc_info:
            validate_path(outside)
        assert "fora das raízes" in str(exc_info.value)

    def test_validate_path_allow_create(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_allowed_roots([tmp_path])
        new_file = tmp_path / "newfile.txt"
        validated = validate_path(new_file, allow_create=True)
        assert validated == new_file.resolve()

    def test_validate_path_requires_existence(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_allowed_roots([tmp_path])
        with pytest.raises(FileNotFoundError):
            validate_path(tmp_path / "nonexistent.txt")

    def test_validate_path_normalizes(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_allowed_roots([tmp_path])
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "file.txt").write_text("x")
        validated = validate_path("./sub/../sub/file.txt")
        assert validated == (tmp_path / "sub" / "file.txt").resolve()


class TestAllowedRoots:
    def test_set_and_get_allowed_roots(self, tmp_path):
        roots = [str(tmp_path / "a"), str(tmp_path / "b")]
        set_allowed_roots(roots)
        got = get_allowed_roots()
        assert len(got) == 2
        assert all(str(p) in roots for p in got)

    def test_empty_allowed_roots_defaults_to_cwd(self, tmp_path, monkeypatch):
        set_allowed_roots([])
        monkeypatch.chdir(tmp_path)
        file_in_cwd = tmp_path / "ok.txt"
        file_in_cwd.write_text("x")
        validated = validate_path(file_in_cwd)
        assert validated == file_in_cwd.resolve()


class TestWriteConfirmation:
    def test_write_requires_confirmation(self):
        assert require_write_confirmation("any/path.txt") is True
        assert require_write_confirmation("any/path.txt", "sobrescrever") is True
        assert require_write_confirmation("any/path.txt", "mover") is True
        assert require_write_confirmation("any/path.txt", "excluir") is True
