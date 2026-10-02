import hashlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.model_downloader import (
    ModelIntegrityError,
    _call_with_retry,
    _download_artifact,
    _required_bytes,
    _store_digest,
    _sufficient_disk_space,
    download_model,
    verify_model_file,
    verify_registered_model,
)

MODEL_BYTES = b"conteudo do modelo"
MODEL_SHA256 = hashlib.sha256(MODEL_BYTES).hexdigest()


class FakeModel:
    def __init__(
        self,
        *,
        filename="m.gguf",
        hf_file="m.gguf",
        hf_repo="repo/model",
        sha256="",
        size_gb=2.0,
    ):
        self.filename = filename
        self.hf_file = hf_file
        self.hf_repo = hf_repo
        self.sha256 = sha256
        self.size_gb = size_gb
        self.has_mmproj = False


def _fake_hub_download(repo_id, filename, revision, local_dir):
    target = Path(local_dir) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(MODEL_BYTES)
    return str(target)


def _install_fake_hub(monkeypatch):
    module = types.ModuleType("huggingface_hub")
    module.hf_hub_download = _fake_hub_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)


def _patch_downloader_env(monkeypatch, resources: Path):
    _install_fake_hub(monkeypatch)
    monkeypatch.setattr("core.model_downloader._resolve_revision", lambda _repo: "a" * 40)
    monkeypatch.setattr("core.model_downloader._remote_sha256", lambda *_a, **_k: MODEL_SHA256)
    monkeypatch.setattr(
        "core.model_downloader.get_settings",
        lambda: SimpleNamespace(get_resources_dir=lambda: resources),
    )


def _assert_staging_empty(resources: Path) -> None:
    staging = resources / ".downloads"
    assert not staging.exists() or not any(staging.iterdir())


def test_verify_model_file_accepts_matching_sha256(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"modelo Celsius")
    expected = hashlib.sha256(model.read_bytes()).hexdigest()

    assert verify_model_file(model, expected) == expected


def test_verify_model_file_rejects_modified_artifact(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"conteudo alterado")

    with pytest.raises(ModelIntegrityError, match="Falha de integridade"):
        verify_model_file(model, "0" * 64)


def test_registered_model_uses_downloaded_digest_sidecar(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"modelo verificado")
    expected = hashlib.sha256(model.read_bytes()).hexdigest()
    _store_digest(model, expected)

    registered = type("Model", (), {"sha256": ""})()
    monkeypatch.setattr("core.model_downloader._find_model", lambda _model_id: registered)

    assert verify_registered_model("test", model) is True
    model.write_bytes(b"modelo adulterado")
    with pytest.raises(ModelIntegrityError):
        verify_registered_model("test", model)


def test_verify_registered_model_accepts_unknown_local_model(tmp_path, monkeypatch):
    model = tmp_path / "qwen-heretic.gguf"
    model.write_bytes(b"modelo local fora do catalogo")
    monkeypatch.setattr("core.model_downloader._find_model", lambda _id: None)

    assert verify_registered_model("qwen-heretic", model) is True


class TestCallWithRetry:
    def test_retries_then_succeeds(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("transiente")
            return "ok"

        assert _call_with_retry(fn, attempts=3, base_delay=0) == "ok"
        assert calls["n"] == 3

    def test_raises_after_attempts_exhausted(self):
        def fn():
            raise ConnectionError("sempre falha")

        with pytest.raises(ConnectionError):
            _call_with_retry(fn, attempts=3, base_delay=0)


class TestDiskSpace:
    def test_required_bytes_includes_margin(self):
        assert _required_bytes(1.0) > 1024**3
        assert _required_bytes(0.0) == 0

    def test_sufficient_disk_space_uses_free(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "core.model_downloader.shutil.disk_usage",
            lambda _path: SimpleNamespace(free=2**30),
        )
        assert _sufficient_disk_space(tmp_path, 10**9) is True
        assert _sufficient_disk_space(tmp_path, 2**31) is False

    def test_disk_usage_failure_allows_download(self, tmp_path, monkeypatch):
        def boom(_path):
            raise OSError("medição indisponível")

        monkeypatch.setattr("core.model_downloader.shutil.disk_usage", boom)
        assert _sufficient_disk_space(tmp_path, 10**9) is True


class TestDownloadArtifact:
    def test_happy_path_verifies_and_places_file(self, tmp_path, monkeypatch):
        _patch_downloader_env(monkeypatch, tmp_path)
        model = FakeModel(sha256=MODEL_SHA256)

        result = _download_artifact(
            model,
            source_filename="m.gguf",
            target_filename="m.gguf",
            sha_field="sha256",
            size_gb=2.0,
            fn_status=None,
        )

        assert result == tmp_path / "m.gguf"
        assert (tmp_path / "m.gguf").read_bytes() == MODEL_BYTES
        assert (tmp_path / "m.gguf.sha256").is_file()
        _assert_staging_empty(tmp_path)

    def test_renames_to_catalog_name(self, tmp_path, monkeypatch):
        _patch_downloader_env(monkeypatch, tmp_path)
        model = FakeModel(filename="catalogo.gguf", hf_file="m.gguf", sha256=MODEL_SHA256)

        result = _download_artifact(
            model,
            source_filename="m.gguf",
            target_filename="catalogo.gguf",
            sha_field="sha256",
            size_gb=2.0,
            fn_status=None,
        )

        assert result == tmp_path / "catalogo.gguf"
        assert (tmp_path / "catalogo.gguf").read_bytes() == MODEL_BYTES
        _assert_staging_empty(tmp_path)

    def test_repairs_corrupt_local_copy(self, tmp_path, monkeypatch):
        _patch_downloader_env(monkeypatch, tmp_path)
        (tmp_path / "m.gguf").write_bytes(b"arquivo corrompido")
        model = FakeModel(sha256=MODEL_SHA256)

        result = _download_artifact(
            model,
            source_filename="m.gguf",
            target_filename="m.gguf",
            sha_field="sha256",
            size_gb=2.0,
            fn_status=None,
        )

        assert result == tmp_path / "m.gguf"
        assert (tmp_path / "m.gguf").read_bytes() == MODEL_BYTES

    def test_valid_local_copy_short_circuits(self, tmp_path, monkeypatch):
        _patch_downloader_env(monkeypatch, tmp_path)
        dest = tmp_path / "m.gguf"
        dest.write_bytes(MODEL_BYTES)
        model = FakeModel(sha256=MODEL_SHA256)

        result = _download_artifact(
            model,
            source_filename="m.gguf",
            target_filename="m.gguf",
            sha_field="sha256",
            size_gb=2.0,
            fn_status=None,
        )

        assert result == dest
        _assert_staging_empty(tmp_path)

    def test_aborts_before_download_on_low_disk(self, tmp_path, monkeypatch):
        _install_fake_hub(monkeypatch)
        monkeypatch.setattr(
            "core.model_downloader.shutil.disk_usage",
            lambda _path: SimpleNamespace(free=1024),
        )
        monkeypatch.setattr(
            "core.model_downloader.get_settings",
            lambda: SimpleNamespace(get_resources_dir=lambda: tmp_path),
        )
        statuses = []

        result = _download_artifact(
            FakeModel(sha256=MODEL_SHA256),
            source_filename="m.gguf",
            target_filename="m.gguf",
            sha_field="sha256",
            size_gb=5.0,
            fn_status=statuses.append,
        )

        assert result is None
        assert "Sem espaco em disco" in " ".join(statuses)
        assert not (tmp_path / "m.gguf").exists()

    def test_verification_failure_leaves_no_partial_file(self, tmp_path, monkeypatch):
        _install_fake_hub(monkeypatch)
        monkeypatch.setattr("core.model_downloader._resolve_revision", lambda _repo: "a" * 40)
        monkeypatch.setattr("core.model_downloader._remote_sha256", lambda *_a, **_k: "0" * 64)
        monkeypatch.setattr(
            "core.model_downloader.get_settings",
            lambda: SimpleNamespace(get_resources_dir=lambda: tmp_path),
        )
        statuses = []

        result = _download_artifact(
            FakeModel(),
            source_filename="m.gguf",
            target_filename="m.gguf",
            sha_field="sha256",
            size_gb=2.0,
            fn_status=statuses.append,
        )

        assert result is None
        assert not (tmp_path / "m.gguf").exists()
        _assert_staging_empty(tmp_path)


class TestDownloadModel:
    def test_download_model_returns_path(self, tmp_path, monkeypatch):
        _patch_downloader_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "core.model_downloader._find_model", lambda _id: FakeModel(sha256=MODEL_SHA256)
        )

        result = download_model("m")

        assert result == tmp_path / "m.gguf"
        assert (tmp_path / "m.gguf").read_bytes() == MODEL_BYTES
