import hashlib

import pytest

from core.model_downloader import (
    ModelIntegrityError,
    _store_digest,
    verify_model_file,
    verify_registered_model,
)


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
