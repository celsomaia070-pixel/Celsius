"""Tests for hardware detection and model selection."""

import builtins
from types import SimpleNamespace
from unittest.mock import patch

from core.hardware import (
    CpuInfo,
    GpuInfo,
    HardwareProfile,
    PerformanceMode,
    _determine_mode,
    _estimate_vram_from_name,
    detect_cpu,
    detect_gpu,
    detect_ram_mb,
    estimate_tokens_per_sec,
    get_model_requirements,
)
from core.model_selector import (
    TIER_COMPLETO,
    TIER_LEVE,
    TIER_MINIMO,
    TIERS,
    ModelRecommendation,
    auto_configure,
    select_optimal_model,
    select_tier,
)


class TestCpuDetection:
    def test_detect_cpu_returns_valid_info(self):
        cpu = detect_cpu()
        assert isinstance(cpu, CpuInfo)
        assert cpu.physical_cores > 0
        assert cpu.logical_cores > 0
        assert cpu.logical_cores >= cpu.physical_cores
        assert cpu.architecture != ""

    def test_detect_cpu_fallback(self):
        with patch("core.hardware.os.cpu_count", return_value=None):
            cpu = detect_cpu()
            assert cpu.physical_cores >= 1


class TestRamDetection:
    def test_detect_ram_returns_positive(self):
        ram = detect_ram_mb()
        assert ram > 0
        assert ram >= 4096  # At least 4GB

    def test_detect_ram_reasonable_range(self):
        ram = detect_ram_mb()
        assert 4096 <= ram <= 1048576  # 4GB to 1TB

    def test_detect_ram_windows_powershell_fallback(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError
            return original_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=fake_import),
            patch("core.hardware.platform.system", return_value="Windows"),
            patch(
                "core.hardware.subprocess.run",
                return_value=SimpleNamespace(stdout=str(32 * 1024 * 1024 * 1024), returncode=0),
            ),
        ):
            assert detect_ram_mb() == 32768

    def test_detect_ram_windows_wmic_fallback(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError
            return original_import(name, *args, **kwargs)

        command_results = [
            SimpleNamespace(stdout="", returncode=1),
            SimpleNamespace(
                stdout=("Capacity\n17179869184\n17179869184\n"),
                returncode=0,
            ),
        ]

        with (
            patch("builtins.__import__", side_effect=fake_import),
            patch("core.hardware.platform.system", return_value="Windows"),
            patch("core.hardware.subprocess.run", side_effect=command_results),
        ):
            assert detect_ram_mb() == 32768


class TestGpuDetection:
    def test_detect_gpu_returns_valid_info(self):
        gpu = detect_gpu()
        assert isinstance(gpu, GpuInfo)
        assert gpu.name != ""
        assert gpu.api in ("vulkan", "cuda", "none")

    def test_estimate_vram_from_name_known_gpu(self):
        assert _estimate_vram_from_name("AMD Radeon RX 7600") == 8192
        assert _estimate_vram_from_name("NVIDIA GeForce RTX 3060") == 12288
        assert _estimate_vram_from_name("NVIDIA GeForce RTX 4090") == 24576

    def test_estimate_vram_from_name_unknown_gpu(self):
        assert _estimate_vram_from_name("Unknown GPU Model") == 4096


class TestHardwareProfile:
    def test_hardware_profile_properties(self):
        cpu = CpuInfo(physical_cores=6, logical_cores=12, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="Test GPU", vram_mb=8192, api="vulkan")
        profile = HardwareProfile(cpu=cpu, ram_mb=32768, gpu=gpu, mode=PerformanceMode.COMPLETO)

        assert profile.ram_gb == 32.0
        assert profile.has_gpu is True
        assert "Test CPU" in profile.summary
        assert "Test GPU" in profile.summary

    def test_hardware_profile_no_gpu(self):
        cpu = CpuInfo(physical_cores=4, logical_cores=8, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="Nenhum", vram_mb=0, api="none")
        profile = HardwareProfile(cpu=cpu, ram_mb=16384, gpu=gpu, mode=PerformanceMode.LEVE)

        assert profile.has_gpu is False
        assert "Sem GPU" in profile.summary


class TestModeDetermination:
    def test_completo_mode_high_end(self):
        cpu = CpuInfo(physical_cores=8, logical_cores=16, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="RX 7600", vram_mb=8192, api="vulkan")
        mode = _determine_mode(cpu, 32768, gpu)
        assert mode == PerformanceMode.COMPLETO

    def test_completo_mode_with_gpu(self):
        cpu = CpuInfo(physical_cores=4, logical_cores=8, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="RTX 3060", vram_mb=12288, api="cuda")
        mode = _determine_mode(cpu, 16384, gpu)
        assert mode == PerformanceMode.COMPLETO

    def test_leve_mode_low_ram(self):
        cpu = CpuInfo(physical_cores=4, logical_cores=8, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="Nenhum", vram_mb=0, api="none")
        mode = _determine_mode(cpu, 8192, gpu)
        assert mode == PerformanceMode.LEVE

    def test_leve_mode_minimal(self):
        cpu = CpuInfo(physical_cores=2, logical_cores=4, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="Nenhum", vram_mb=0, api="none")
        mode = _determine_mode(cpu, 6144, gpu)
        assert mode == PerformanceMode.LEVE


class TestModelRequirements:
    def test_model_requirements_exist(self):
        for model_id in ["qwen3-8b-q4km", "qwen3-4b-q4km", "qwen2.5-vl-7b-q4km"]:
            reqs = get_model_requirements(model_id)
            assert reqs is not None
            assert reqs.min_ram_gb > 0
            assert reqs.recommended_ram_gb >= reqs.min_ram_gb

    def test_7b_needs_more_ram_than_3b(self):
        reqs_8b = get_model_requirements("qwen3-8b-q4km")
        reqs_4b = get_model_requirements("qwen3-4b-q4km")
        assert reqs_8b.min_ram_gb > reqs_4b.min_ram_gb


class TestEstimateTokensPerSec:
    def test_estimate_with_gpu(self):
        cpu = CpuInfo(physical_cores=6, logical_cores=12, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="RX 7600", vram_mb=8192, api="vulkan")
        profile = HardwareProfile(cpu=cpu, ram_mb=32768, gpu=gpu, mode=PerformanceMode.COMPLETO)

        tps = estimate_tokens_per_sec("qwen3-8b-q4km", profile)
        assert tps > 0
        assert tps >= 10  # Should be reasonably fast with GPU

    def test_estimate_without_gpu(self):
        cpu = CpuInfo(physical_cores=4, logical_cores=8, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="Nenhum", vram_mb=0, api="none")
        profile = HardwareProfile(cpu=cpu, ram_mb=16384, gpu=gpu, mode=PerformanceMode.LEVE)

        tps = estimate_tokens_per_sec("qwen3-4b-q4km", profile)
        assert tps > 0
        assert tps >= 3  # Should be usable on CPU


class TestTierSelection:
    def test_select_tier_high_end(self):
        cpu = CpuInfo(physical_cores=8, logical_cores=16, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="RX 7600", vram_mb=8192, api="vulkan")
        profile = HardwareProfile(cpu=cpu, ram_mb=32768, gpu=gpu, mode=PerformanceMode.COMPLETO)

        tier = select_tier(profile)
        assert tier == TIER_COMPLETO

    def test_select_tier_low_end(self):
        cpu = CpuInfo(physical_cores=2, logical_cores=4, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="Nenhum", vram_mb=0, api="none")
        profile = HardwareProfile(cpu=cpu, ram_mb=8192, gpu=gpu, mode=PerformanceMode.LEVE)

        tier = select_tier(profile)
        assert tier in (TIER_LEVE, TIER_MINIMO)

    def test_all_tiers_have_models(self):
        for tier in TIERS:
            assert tier.main_model_id != ""
            assert tier.fast_model_id != ""
            assert tier.n_ctx > 0


class TestModelSelection:
    def test_select_optimal_model_completo(self):
        cpu = CpuInfo(physical_cores=8, logical_cores=16, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="RX 7600", vram_mb=8192, api="vulkan")
        profile = HardwareProfile(cpu=cpu, ram_mb=32768, gpu=gpu, mode=PerformanceMode.COMPLETO)

        rec = select_optimal_model(profile)
        assert isinstance(rec, ModelRecommendation)
        assert rec.n_gpu_layers == -1  # Full GPU offload
        assert rec.n_ctx >= 8192
        assert rec.estimated_main_tokens_per_sec > 0

    def test_select_optimal_model_leve(self):
        cpu = CpuInfo(physical_cores=2, logical_cores=4, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="Nenhum", vram_mb=0, api="none")
        profile = HardwareProfile(cpu=cpu, ram_mb=8192, gpu=gpu, mode=PerformanceMode.LEVE)

        rec = select_optimal_model(profile)
        assert isinstance(rec, ModelRecommendation)
        assert rec.n_gpu_layers == 0  # CPU only
        assert "4b" in rec.main_model_id or "qwen3" in rec.main_model_id

    def test_select_optimal_model_force(self):
        cpu = CpuInfo(physical_cores=4, logical_cores=8, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="Nenhum", vram_mb=0, api="none")
        profile = HardwareProfile(cpu=cpu, ram_mb=16384, gpu=gpu, mode=PerformanceMode.LEVE)

        rec = select_optimal_model(profile, force_model="qwen2.5-vl-7b-q4km")
        assert rec.main_model_id == "qwen2.5-vl-7b-q4km"
        assert rec.mode == PerformanceMode.CUSTOM

    def test_recommendation_summary(self):
        cpu = CpuInfo(physical_cores=6, logical_cores=12, architecture="x86_64", brand="Test CPU")
        gpu = GpuInfo(name="RTX 3060", vram_mb=12288, api="cuda")
        profile = HardwareProfile(cpu=cpu, ram_mb=24576, gpu=gpu, mode=PerformanceMode.COMPLETO)

        rec = select_optimal_model(profile)
        summary = rec.summary
        assert "Modo:" in summary
        assert "Modelo principal:" in summary
        assert "GPU layers:" in summary


class TestAutoConfigure:
    def test_auto_configure_returns_recommendation(self):
        rec = auto_configure()
        assert isinstance(rec, ModelRecommendation)
        assert rec.main_model_id != ""
        assert rec.fast_model_id != ""
        assert rec.n_ctx > 0

    def test_auto_configure_no_multimodal(self):
        rec = auto_configure(prefer_multimodal=False)
        assert isinstance(rec, ModelRecommendation)
        # Fast model should be selected as main
        from core.config import get_model_by_id

        model = get_model_by_id(rec.main_model_id)
        assert model is not None
