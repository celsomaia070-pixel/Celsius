"""Slow-model detection and lighter-model suggestion.

When the model chosen by the user responds too slowly on the current machine,
Celsius suggests a lighter installed model (without forcing the switch).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from core.config import GGUF_MODELS, GGUFModel, get_model_by_id

logger = logging.getLogger(__name__)

#: Minimum generation time (in seconds) before evaluating slowness.
DEFAULT_MIN_ELAPSED_SECONDS = 5.0

#: Suggest a lighter model when real tokens-per-second drops below this
#: fraction of the hardware-expected value.
DEFAULT_SLOWNESS_MULTIPLIER = 0.5

#: Rough long texts use ~4 chars per token.
CHARS_PER_TOKEN = 4.0


@dataclass(frozen=True)
class ModelSuggestion:
    """Outcome of the slowness evaluation."""

    used_model_id: str
    used_model_name: str
    used_size_gb: float
    suggested_model_id: str
    suggested_model_name: str
    suggested_size_gb: float
    estimated_output_tokens: int
    elapsed_seconds: float
    real_tokens_per_sec: float
    expected_tokens_per_sec: int

    @property
    def message(self) -> str:
        """Human-friendly suggestion in Portuguese."""
        return (
            f"Percebi que o modelo **{self.used_model_name}** esta respondendo "
            f"lento na sua maquina (~{self.real_tokens_per_sec:.1f} tokens/s, "
            f"esperado ~{self.expected_tokens_per_sec} tokens/s). "
            f"Que tal trocar para o modelo mais leve **{self.suggested_model_name}** "
            f"({self.suggested_size_gb:.1f}GB) para respostas mais rapidas?"
        )


def suggest_lighter_model(
    used_model_id: str,
    elapsed_seconds: float,
    estimated_output_tokens: int,
    expected_tokens_per_sec: int,
    catalog: list[GGUFModel] | None = None,
    installed_ids: set[str] | None = None,
    resources_dir: Path | None = None,
    min_elapsed_seconds: float = DEFAULT_MIN_ELAPSED_SECONDS,
    slowness_multiplier: float = DEFAULT_SLOWNESS_MULTIPLIER,
) -> ModelSuggestion | None:
    """Return a lighter model suggestion when the current model is too slow.

    Args:
        used_model_id: Which model produced the response.
        elapsed_seconds: Generation time for that response.
        estimated_output_tokens: Rough number of output tokens produced.
        expected_tokens_per_sec: Expected tps on this machine for the used model.
        catalog: Model registry to search for lighter alternatives.
        installed_ids: Model ids whose GGUF files exist locally. When omitted,
            derived from ``resources_dir``.
        resources_dir: Directory with the GGUF files (needed only when
            ``installed_ids`` is omitted). Non-frozen builds use
            ``<projeto>/resources``.
        min_elapsed_seconds: Ignore responses faster than this.
        slowness_multiplier: Suggest when real tps falls below this fraction.

    Returns:
        A ``ModelSuggestion`` when a lighter installed model exists and the
        speed ratio triggers it; ``None`` otherwise.
    """
    if elapsed_seconds < min_elapsed_seconds:
        return None

    used_model = (
        get_model_by_id(used_model_id)
        if catalog is None
        else _find_in_catalog(catalog, used_model_id)
    )
    if used_model is None:
        return None

    if estimated_output_tokens <= 0 or expected_tokens_per_sec <= 0:
        return None

    real_tps = estimated_output_tokens / elapsed_seconds
    if real_tps >= expected_tokens_per_sec * slowness_multiplier:
        return None

    if installed_ids is None:
        installed_ids = _discover_installed_ids(catalog or GGUF_MODELS, resources_dir)
    lighter_installed = [
        m
        for m in (catalog or GGUF_MODELS)
        if m.id in installed_ids and m.id != used_model_id and m.size_gb < used_model.size_gb
    ]
    if not lighter_installed:
        return None

    suggested = min(lighter_installed, key=lambda m: m.size_gb)
    return ModelSuggestion(
        used_model_id=used_model.id,
        used_model_name=used_model.name,
        used_size_gb=used_model.size_gb,
        suggested_model_id=suggested.id,
        suggested_model_name=suggested.name,
        suggested_size_gb=suggested.size_gb,
        estimated_output_tokens=estimated_output_tokens,
        elapsed_seconds=elapsed_seconds,
        real_tokens_per_sec=real_tps,
        expected_tokens_per_sec=expected_tokens_per_sec,
    )


def _find_in_catalog(catalog: list[GGUFModel], model_id: str) -> GGUFModel | None:
    return next((m for m in catalog if m.id == model_id), None)


def _discover_installed_ids(catalog: list[GGUFModel], resources_dir: Path | None) -> set[str]:
    if resources_dir is None:
        return set()
    installed: set[str] = set()
    for model in catalog:
        path = resources_dir / model.filename
        if path.exists():
            installed.add(model.id)
    return installed


def estimate_output_tokens(text: str) -> int:
    """Rough token estimate from output length (~4 chars per token)."""
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def suggestions_enabled(settings) -> bool:
    """Whether slow-model suggestions are enabled.

    Checks ``settings.slow_model_suggestions`` (or the feature flag under
    ``settings.features.slow_model_suggestions``) when present.  Defaults to
    True so the feature works out of the box.
    """
    flag = getattr(settings, "slow_model_suggestions", None)
    if flag is None:
        features = getattr(settings, "features", None)
        flag = getattr(features, "slow_model_suggestions", None) if features is not None else None
    return True if flag is None else bool(flag)
