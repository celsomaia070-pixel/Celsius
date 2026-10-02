"""Downloads GGUF models from HuggingFace."""

import hashlib
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


def _resolve_revision(repo_id: str) -> str:
    """Resolve the current repository state to an immutable commit SHA."""
    from huggingface_hub import model_info

    revision = str(model_info(repo_id, revision="main").sha or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", revision):
        raise ModelIntegrityError(f"Revisao imutavel indisponivel para {repo_id}")
    return revision


def _remote_sha256(repo_id: str, filename: str, *, revision: str = "main") -> str:
    from huggingface_hub import get_hf_file_metadata, hf_hub_url

    metadata = get_hf_file_metadata(hf_hub_url(repo_id, filename, revision=revision))
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


def _call_with_retry(
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Retry a transient network call with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return fn()
        except Exception as error:  # noqa: BLE001 - transient network faults retry
            last_error = error
            if attempt + 1 < max(1, attempts):
                time.sleep(base_delay * (2**attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError("operacao de rede falhou")


def _required_bytes(size_gb: float) -> int:
    """Disk bytes needed (model + 10% margin); 0 for unknown (no pre-check)."""
    return int(max(size_gb, 0.0) * (1024**3) * 1.1)


def _sufficient_disk_space(directory: Path, required_bytes: int) -> bool:
    try:
        free = shutil.disk_usage(directory).free
    except OSError:
        return True
    return free >= required_bytes


def _staging_dir(resources: Path) -> Path:
    staging = resources / ".downloads" / f"artifact-{time.time_ns()}"
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def _download_artifact(
    model: GGUFModel,
    *,
    source_filename: str,
    target_filename: str,
    sha_field: str,
    size_gb: float,
    fn_status: Callable[[str], None] | None,
) -> Path | None:
    """Download a single artifact into ``resources`` with verification.

    Downloads go to a staging directory and only move to the final name
    after the SHA-256 check passes (atomic ``Path.replace``). A corrupt
    local copy is repaired in place, and partial/interrupted downloads
    never linger under the final filename.
    """
    resources = get_settings().get_resources_dir()
    resources.mkdir(parents=True, exist_ok=True)
    dest = resources / target_filename

    registered = str(getattr(model, sha_field, "") or "").strip()
    if dest.exists():
        try:
            expected = registered or _remote_sha256(model.hf_repo, source_filename, revision="main")
            verify_model_file(dest, expected)
            _store_digest(dest, expected)
            return dest
        except Exception as error:
            if fn_status:
                fn_status(f"Arquivo local invalido; baixando novamente: {error}")

    required = _required_bytes(size_gb)
    if required and not _sufficient_disk_space(resources, required):
        if fn_status:
            fn_status("Sem espaco em disco: necessario ~%.1f GB livre." % (required / (1024**3)))
        return None

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as err:
        raise ImportError(
            "huggingface_hub nao esta instalado. Execute: pip install huggingface_hub"
        ) from err

    if fn_status:
        fn_status(f"Baixando {dest.name}...")

    staging = _staging_dir(resources)
    try:
        revision = _call_with_retry(lambda: _resolve_revision(model.hf_repo))
        expected = registered or _call_with_retry(
            lambda: _remote_sha256(model.hf_repo, source_filename, revision=revision)
        )

        downloaded = _call_with_retry(
            lambda: hf_hub_download(
                repo_id=model.hf_repo,
                filename=source_filename,
                revision=revision,
                local_dir=str(staging),
            )
        )
        staged = Path(downloaded)
        if staged.name != target_filename:
            target_in_staging = staging / target_filename
            staged.rename(target_in_staging)
            staged = target_in_staging

        verify_model_file(staged, expected)
        staged.replace(dest)
        _store_digest(dest, expected)
        if fn_status:
            fn_status(f"Download concluido: {dest.name} (verificado)")
        return dest
    except Exception as error:
        if fn_status:
            fn_status(f"Erro ao baixar {dest.name}: {error}")
        return None
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def verify_registered_model(model_id: str, path: Path | None = None) -> bool:
    """Verify a local model when a trusted catalog hash is registered.

    Models not present in the catalog (e.g. a custom local GGUF such as
    ``qwen-heretic.gguf``) have no trust anchor, so they are accepted without
    verification; a sidecar ``.sha256`` digest is still enforced when present.
    """
    model = _find_model(model_id)
    if model is None:
        return True
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

    try:
        return _download_artifact(
            model,
            source_filename=model.hf_file,
            target_filename=model.filename,
            sha_field="sha256",
            size_gb=model.size_gb,
            fn_status=fn_status,
        )
    except ImportError:
        raise
    except Exception as error:
        if fn_status:
            fn_status(f"Erro ao baixar modelo: {error}")
        return None


def download_mmproj(
    model_id: str,
    fn_status: Callable[[str], None] | None = None,
) -> Path | None:
    """Download mmproj file for a model (vision support)."""
    model = _find_model(model_id)
    if not model or not model.has_mmproj:
        return None

    try:
        return _download_artifact(
            model,
            source_filename=model.mmproj_file,
            target_filename=model.mmproj_file,
            sha_field="mmproj_sha256",
            size_gb=0.0,
            fn_status=fn_status,
        )
    except ImportError:
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
