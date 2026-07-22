"""Downloads GGUF models from HuggingFace."""
import os
from pathlib import Path
from typing import Callable, Optional

from core.config import GGUFModel, get_settings


def get_downloaded_models() -> set[str]:
    """Return set of model ids that are already downloaded."""
    resources = get_settings().get_resources_dir()
    downloaded = set()
    for model_file in resources.glob("*.gguf"):
        if model_file.name.startswith("mmproj"):
            continue
        # Match by filename
        for m in _get_all_models():
            if m.filename == model_file.name:
                downloaded.add(m.id)
    return downloaded


def is_model_downloaded(model_id: str) -> bool:
    """Check if a specific model is already downloaded."""
    settings = get_settings()
    model = _find_model(model_id)
    if not model:
        return False
    return (settings.get_resources_dir() / model.filename).exists()


def is_mmproj_downloaded(model_id: str) -> bool:
    """Check if mmproj file is downloaded for a model."""
    settings = get_settings()
    model = _find_model(model_id)
    if not model or not model.has_mmproj:
        return False
    return (settings.get_resources_dir() / model.mmproj_file).exists()


def download_model(
    model_id: str,
    fn_progress: Optional[Callable[[str, int], None]] = None,
    fn_status: Optional[Callable[[str], None]] = None,
) -> Path | None:
    """Download a GGUF model from HuggingFace. Returns the local path on success."""
    model = _find_model(model_id)
    if not model:
        raise ValueError(f"Model '{model_id}' not found in registry")

    resources = get_settings().get_resources_dir()
    resources.mkdir(parents=True, exist_ok=True)

    dest = resources / model.filename
    if dest.exists():
        if fn_status:
            fn_status(f"Modelo ja existe: {dest.name}")
        return dest

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise ImportError("huggingface_hub nao esta instalado. Execute: pip install huggingface_hub")

    if fn_status:
        fn_status(f"Baixando {model.name} ({model.quant})...")

    try:
        path = hf_hub_download(
            repo_id=model.hf_repo,
            filename=model.hf_file,
            local_dir=str(resources),
            local_dir_use_symlinks=False,
        )
        result = Path(path)

        # Rename if needed (hf_hub_download keeps original name)
        if result.name != model.filename:
            target = resources / model.filename
            result.rename(target)
            result = target

        if fn_status:
            fn_status(f"Download concluido: {result.name}")

        return result
    except Exception as e:
        if fn_status:
            fn_status(f"Erro ao baixar modelo: {e}")
        return None


def download_mmproj(
    model_id: str,
    fn_status: Optional[Callable[[str], None]] = None,
) -> Path | None:
    """Download mmproj file for a model (vision support)."""
    model = _find_model(model_id)
    if not model or not model.has_mmproj:
        return None

    resources = get_settings().get_resources_dir()
    dest = resources / model.mmproj_file
    if dest.exists():
        return dest

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return None

    if fn_status:
        fn_status(f"Baixando mmproj (suporte a visao)...")

    try:
        path = hf_hub_download(
            repo_id=model.hf_repo,
            filename=model.mmproj_file,
            local_dir=str(resources),
            local_dir_use_symlinks=False,
        )
        result = Path(path)
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
