"""Automatic model selection based on hardware profile.

Maps detected hardware to optimal model configuration for the Celsius application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.config import GGUF_MODELS, GGUFModel, get_model_by_id
from core.hardware import (
    HardwareProfile,
    PerformanceMode,
    detect_hardware,
    estimate_tokens_per_sec,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelRecommendation:
    """Recommended model configuration for detected hardware."""

    main_model_id: str
    fast_model_id: str
    n_gpu_layers: int
    n_ctx: int
    n_batch: int
    n_threads: int
    mode: PerformanceMode
    profile: HardwareProfile

    @property
    def main_model(self) -> GGUFModel | None:
        return get_model_by_id(self.main_model_id)

    @property
    def fast_model(self) -> GGUFModel | None:
        return get_model_by_id(self.fast_model_id)

    @property
    def estimated_main_tokens_per_sec(self) -> int:
        return estimate_tokens_per_sec(self.main_model_id, self.profile)

    @property
    def estimated_fast_tokens_per_sec(self) -> int:
        return estimate_tokens_per_sec(self.fast_model_id, self.profile)

    @property
    def summary(self) -> str:
        main = self.main_model
        fast = self.fast_model
        main_name = main.display_name if main else self.main_model_id
        fast_name = fast.display_name if fast else self.fast_model_id
        return (
            f"Modo: {self.mode.value.upper()}\n"
            f"Modelo principal: {main_name}\n"
            f"Modelo rapido: {fast_name}\n"
            f"GPU layers: {self.n_gpu_layers}\n"
            f"Contexto: {self.n_ctx} tokens\n"
            f"Est. velocidade: ~{self.estimated_main_tokens_per_sec} tok/s (principal)"
        )


# ── Hardware profiles ────────────────────────────────────────────


@dataclass(frozen=True)
class HardwareTier:
    """Hardware tier thresholds for model selection."""

    name: str
    min_ram_gb: float
    min_vram_mb: int
    min_cpu_cores: int
    main_model_id: str
    fast_model_id: str
    n_gpu_layers: int
    n_ctx: int
    n_batch: int


TIER_COMPLETO = HardwareTier(
    name="completo",
    min_ram_gb=24,
    min_vram_mb=6000,
    min_cpu_cores=6,
    main_model_id="qwen2.5-vl-7b-q4km",
    fast_model_id="llama3.2-3b-q5km",
    n_gpu_layers=-1,
    n_ctx=16384,
    n_batch=1024,
)

TIER_COMPLETO_GPU = HardwareTier(
    name="completo_gpu",
    min_ram_gb=16,
    min_vram_mb=6000,
    min_cpu_cores=4,
    main_model_id="qwen2.5-vl-7b-q4km",
    fast_model_id="llama3.2-3b-q5km",
    n_gpu_layers=-1,
    n_ctx=8192,
    n_batch=1024,
)

TIER_LEVE_RAM = HardwareTier(
    name="leve_ram",
    min_ram_gb=12,
    min_vram_mb=0,
    min_cpu_cores=4,
    main_model_id="gemma3-4b-q4km",
    fast_model_id="llama3.2-3b-q5km",
    n_gpu_layers=0,
    n_ctx=4096,
    n_batch=512,
)

TIER_LEVE = HardwareTier(
    name="leve",
    min_ram_gb=8,
    min_vram_mb=0,
    min_cpu_cores=2,
    main_model_id="llama3.2-3b-q5km",
    fast_model_id="llama3.2-3b-q5km",
    n_gpu_layers=0,
    n_ctx=2048,
    n_batch=256,
)

TIER_MINIMO = HardwareTier(
    name="minimo",
    min_ram_gb=0,
    min_vram_mb=0,
    min_cpu_cores=0,
    main_model_id="llama3.2-3b-q5km",
    fast_model_id="llama3.2-3b-q5km",
    n_gpu_layers=0,
    n_ctx=1024,
    n_batch=128,
)

TIERS = [TIER_COMPLETO, TIER_COMPLETO_GPU, TIER_LEVE_RAM, TIER_LEVE, TIER_MINIMO]


def select_tier(profile: HardwareProfile) -> HardwareTier:
    """Select the best hardware tier for the detected profile."""
    for tier in TIERS:
        if (
            profile.ram_gb >= tier.min_ram_gb
            and (not profile.has_gpu or profile.gpu.vram_mb >= tier.min_vram_mb)
            and profile.cpu.physical_cores >= tier.min_cpu_cores
        ):
            return tier
    return TIER_MINIMO


def select_optimal_model(
    profile: HardwareProfile,
    prefer_multimodal: bool = True,
    force_model: str | None = None,
) -> ModelRecommendation:
    """Select optimal model configuration based on hardware profile.

    Args:
        profile: Detected hardware profile
        prefer_multimodal: Prefer multimodal (vision) models when possible
        force_model: Override automatic selection with specific model ID
    """
    if force_model and get_model_by_id(force_model):
        tier = select_tier(profile)
        return ModelRecommendation(
            main_model_id=force_model,
            fast_model_id=tier.fast_model_id,
            n_gpu_layers=-1 if profile.has_gpu else 0,
            n_ctx=tier.n_ctx,
            n_batch=tier.n_batch,
            n_threads=profile.cpu.physical_cores,
            mode=PerformanceMode.CUSTOM,
            profile=profile,
        )

    tier = select_tier(profile)

    main_model_id = tier.main_model_id
    if not prefer_multimodal:
        fast_models = [m for m in GGUF_MODELS if m.category == "fast"]
        if fast_models:
            main_model_id = fast_models[0].id

    n_gpu_layers = tier.n_gpu_layers
    if n_gpu_layers == -1 and profile.has_gpu:
        main_model = get_model_by_id(main_model_id)
        if main_model:
            reqs_vram = main_model.size_gb * 1024
            if profile.gpu.vram_mb < reqs_vram * 0.7:
                n_gpu_layers = 0
                logger.info("GPU VRAM insufficient for full offload, using CPU")

    return ModelRecommendation(
        main_model_id=main_model_id,
        fast_model_id=tier.fast_model_id,
        n_gpu_layers=n_gpu_layers,
        n_ctx=tier.n_ctx,
        n_batch=tier.n_batch,
        n_threads=profile.cpu.physical_cores,
        mode=profile.mode,
        profile=profile,
    )


def auto_configure(
    prefer_multimodal: bool = True,
    force_model: str | None = None,
) -> ModelRecommendation:
    """Detect hardware and return optimal model configuration.

    This is the main entry point for automatic hardware-based configuration.
    """
    profile = detect_hardware()
    recommendation = select_optimal_model(
        profile=profile,
        prefer_multimodal=prefer_multimodal,
        force_model=force_model,
    )

    logger.info(
        "Auto-configuration: mode=%s, main=%s, fast=%s, gpu_layers=%d, ctx=%d",
        recommendation.mode.value,
        recommendation.main_model_id,
        recommendation.fast_model_id,
        recommendation.n_gpu_layers,
        recommendation.n_ctx,
    )

    return recommendation
