"""Downloads GGUF models from HuggingFace."""

import hashlib
import re
from collections.abc import Callable
from pathlib import Path

from core.config import GGUFModel
from core.settings import get_settings


class ModelIntegrityError(RuntimeError):
    """Raised when a model artifact does not match its trusted SHA-256."""


def _file_sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remote_sha256(repo_id: str, filename: str) -> str:
    from huggingface_hub import get_hf_file_metadata, hf_hub_url

    metadata = get_hf_file_metadata(hf_hub_url(repo_id, filename))
    etag = str(metadata.etag or "").strip('"')
    if not re.fullmatch(r"[0-9a-fA-F]{64}", etag):
        raise ModelIntegrityError(f"SHA-256 oficial indisponivel para {filename}")
    return etag.lower()


def verify_model_file(path: Path, expected_sha256: str) -> str:
    """Return the calculated digest or raise when the artifact is corrupted."""
    expected = expected_sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ModelIntegrityError(f"SHA-256 esperado invalido para {path.name}")
    actual = _file_sha256(path)
    if actual != expected:
        raise ModelIntegrityError(
            f"Falha de integridade em {path.name}: esperado {expected}, obtido {actual}"
        )
    return actual


def _digest_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.sha256")


def _store_digest(path: Path, digest: str) -> None:
    target = _digest_path(path)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(f"{digest.lower()}  {path.name}\n", encoding="ascii")
    temporary.replace(target)


def _stored_digest(path: Path) -> str:
    sidecar = _digest_path(path)
    if not sidecar.is_file():
        return ""
    return sidecar.read_text(encoding="ascii").split(maxsplit=1)[0].strip().lower()


def verify_registered_model(model_id: str, path: Path | None = None) -> bool:
    """Verify a local model when a trusted catalog hash is registered."""
    model = _find_model(model_id)
    if model is None:
        raise ValueError(f"Model '{model_id}' not found in registry")
    model_path = path or get_settings().get_model_path(model_id)
    expected = model.sha256 or _stored_digest(model_path)
    if not expected:
        return True
    verify_model_file(model_path, expected)
    return True


def verify_registered_mmproj(model_id: str, path: Path) -> bool:
    """Verify a vision projector when a trusted catalog hash is registered."""
    model = _find_model(model_id)
    if model is None:
        raise ValueError(f"Model '{model_id}' not found in registry")
    expected = model.mmproj_sha256 or _stored_digest(path)
    if not expected:
        return True
    verify_model_file(path, expected)
    return True


def get_downloaded_models() -> set[str]:
    """Return set of model ids that are already downloaded."""
    settings = get_settings()
    downloaded = set()
    for model in _get_all_models():
        if settings.get_model_path(model.id).is_file():
            downloaded.add(model.id)
    return downloaded


def is_model_downloaded(model_id: str) -> bool:
    """Check if a specific model is already downloaded."""
    settings = get_settings()
    model = _find_model(model_id)
    if not model:
        return False
    return settings.get_model_path(model_id).is_file()


def is_mmproj_downloaded(model_id: str) -> bool:
    """Check if mmproj file is downloaded for a model."""
    settings = get_settings()
    model = _find_model(model_id)
    if not model or not model.has_mmproj:
        return False
    return settings.get_mmproj_path(model_id) is not None


def download_model(
    model_id: str,
    fn_progress: Callable[[str, int], None] | None = None,
    fn_status: Callable[[str], None] | None = None,
) -> Path | None:
    """Download a GGUF model from HuggingFace. Returns the local path on success."""
    model = _find_model(model_id)
    if not model:
        raise ValueError(f"Model '{model_id}' not found in registry")

    resources = get_settings().get_resources_dir()
    resources.mkdir(parents=True, exist_ok=True)

    dest = resources / model.filename
    if dest.exists():
        try:
            expected = model.sha256 or _remote_sha256(model.hf_repo, model.hf_file)
            if fn_status:
                fn_status(f"Verificando integridade de {dest.name}...")
            verify_model_file(dest, expected)
            _store_digest(dest, expected)
            if fn_status:
                fn_status(f"Modelo verificado: {dest.name}")
            return dest
        except Exception as error:
            if fn_status:
                fn_status(f"Modelo local invalido: {error}")
            return None

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as err:
        raise ImportError(
            "huggingface_hub nao esta instalado. Execute: pip install huggingface_hub"
        ) from err

    if fn_status:
        fn_status(f"Baixando {model.name} ({model.quant})...")

    try:
        expected = model.sha256 or _remote_sha256(model.hf_repo, model.hf_file)
        path = hf_hub_download(
            repo_id=model.hf_repo,
            filename=model.hf_file,
            local_dir=str(resources),
        )
        result = Path(path)

        # Rename if needed (hf_hub_download keeps original name)
        if result.name != model.filename:
            target = resources / model.filename
            result.rename(target)
            result = target

        if fn_status:
            fn_status("Verificando SHA-256 do modelo...")
        verify_model_file(result, expected)
        _store_digest(result, expected)

        if fn_status:
            fn_status(f"Download concluido: {result.name}")

        return result
    except Exception as e:
        if fn_status:
            fn_status(f"Erro ao baixar modelo: {e}")
        return None


def download_mmproj(
    model_id: str,
    fn_status: Callable[[str], None] | None = None,
) -> Path | None:
    """Download mmproj file for a model (vision support)."""
    model = _find_model(model_id)
    if not model or not model.has_mmproj:
        return None

    resources = get_settings().get_resources_dir()
    dest = resources / model.mmproj_file
    if dest.exists():
        try:
            expected = model.mmproj_sha256 or _remote_sha256(model.hf_repo, model.mmproj_file)
            verify_model_file(dest, expected)
            _store_digest(dest, expected)
            return dest
        except Exception as error:
            if fn_status:
                fn_status(f"Projetor visual local invalido: {error}")
            return None

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return None

    if fn_status:
        fn_status("Baixando mmproj (suporte a visao)...")

    try:
        expected = model.mmproj_sha256 or _remote_sha256(model.hf_repo, model.mmproj_file)
        path = hf_hub_download(
            repo_id=model.hf_repo,
            filename=model.mmproj_file,
            local_dir=str(resources),
        )
        result = Path(path)
        verify_model_file(result, expected)
        _store_digest(result, expected)
        if fn_status:
            fn_status(f"mmproj baixado: {result.name}")
        return result
    except Exception as e:
        if fn_status:
            fn_status(f"Erro ao baixar mmproj: {e}")
        return None


def get_model_size_gb(model_id: str) -> float:
    """Get model size in GB from registry."""
    model = _find_model(model_id)
    return model.size_gb if model else 0.0


def _find_model(model_id: str) -> GGUFModel | None:
    from core.config import get_model_by_id

    return get_model_by_id(model_id)


def _get_all_models() -> list[GGUFModel]:
    from core.config import GGUF_MODELS

    return GGUF_MODELS
