"""Hardware detection and profiling for automatic model selection.

Detects CPU, RAM, and GPU capabilities to recommend optimal model configuration.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PerformanceMode(str, Enum):
    """Operating performance modes."""

    LEVE = "leve"
    COMPLETO = "completo"
    CUSTOM = "custom"


@dataclass(frozen=True)
class CpuInfo:
    """Detected CPU information."""

    physical_cores: int
    logical_cores: int
    architecture: str
    brand: str


@dataclass(frozen=True)
class GpuInfo:
    """Detected GPU information."""

    name: str
    vram_mb: int
    api: str  # "vulkan", "cuda", "none"


@dataclass(frozen=True)
class HardwareProfile:
    """Complete hardware profile."""

    cpu: CpuInfo
    ram_mb: int
    gpu: GpuInfo
    mode: PerformanceMode

    @property
    def ram_gb(self) -> float:
        return self.ram_mb / 1024

    @property
    def has_gpu(self) -> bool:
        return self.gpu.vram_mb > 0

    @property
    def summary(self) -> str:
        gpu_str = f"{self.gpu.name} ({self.gpu.vram_mb}MB)" if self.has_gpu else "Sem GPU"
        return (
            f"CPU: {self.cpu.brand} ({self.cpu.physical_cores}C/{self.cpu.logical_cores}T) | "
            f"RAM: {self.ram_gb:.0f}GB | GPU: {gpu_str} | Modo: {self.mode.value}"
        )


def detect_cpu() -> CpuInfo:
    """Detect CPU information."""
    try:
        logical = os.cpu_count() or 4
        physical = min(_get_physical_cores(), logical)
        architecture = platform.machine()
        brand = platform.processor() or "Unknown CPU"
        return CpuInfo(
            physical_cores=physical,
            logical_cores=logical,
            architecture=architecture,
            brand=brand,
        )
    except Exception as e:
        logger.warning("CPU detection failed: %s", e)
        return CpuInfo(
            physical_cores=4, logical_cores=8, architecture="x86_64", brand="Unknown CPU"
        )


def _get_physical_cores() -> int:
    """Get physical core count (not logical/hyperthreaded)."""
    try:
        import psutil

        return psutil.cpu_count(logical=False) or 4
    except ImportError:
        pass

    system = platform.system()
    try:
        if system == "Windows":
            result = subprocess.run(
                ["wmic", "cpu", "get", "NumberOfCores"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.isdigit():
                    return int(line)
        elif system == "Linux":
            result = subprocess.run(
                ["lscpu", "-p"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            cores = set()
            for line in result.stdout.strip().split("\n"):
                if line.startswith("#"):
                    continue
                parts = line.split(",")
                if len(parts) >= 4:
                    cores.add(parts[3])
            return len(cores) if cores else 4
        elif system == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.physicalcpu"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return int(result.stdout.strip())
    except Exception:
        pass

    return 4


def detect_ram_mb() -> int:
    """Detect total system RAM in MB."""
    try:
        import psutil

        return psutil.virtual_memory().total // (1024 * 1024)
    except ImportError:
        pass

    system = platform.system()
    try:
        if system == "Windows":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_ComputerSystem | "
                    "Select-Object -ExpandProperty TotalPhysicalMemory",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.isdigit():
                    return int(line) // (1024 * 1024)

            result = subprocess.run(
                ["wmic", "memorychip", "get", "Capacity"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            total = 0
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.isdigit():
                    total += int(line) // (1024 * 1024)
            if total > 0:
                return total
        elif system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) // 1024
        elif system == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return int(result.stdout.strip()) // (1024 * 1024)
    except Exception:
        pass

    return 16384  # Conservative default: 16GB


def detect_gpu() -> GpuInfo:
    """Detect GPU information. Tries Vulkan, CUDA, then WMI (Windows)."""
    gpu = _detect_gpu_vulkan()
    if gpu and gpu.name != "Unknown GPU":
        return gpu

    gpu = _detect_gpu_cuda()
    if gpu:
        return gpu

    gpu = _detect_gpu_wmi()
    if gpu:
        return gpu

    if gpu and gpu.name != "Unknown GPU":
        return gpu

    return GpuInfo(name="Nenhum", vram_mb=0, api="none")


def _detect_gpu_vulkan() -> GpuInfo | None:
    """Detect GPU via Vulkan (works for AMD and NVIDIA)."""
    try:
        result = subprocess.run(
            ["vulkaninfo", "--summary"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        stdout = result.stdout
        if not stdout:
            return None

        name = "Unknown GPU"
        vram_mb = 0

        for line in stdout.split("\n"):
            line = line.strip()
            low = line.lower()
            if "devicename" in low:
                name = line.split("=", 1)[-1].strip().strip('"')
            elif "vram" in low or "dedicatedmemory" in low or "dedicated memory" in low:
                for part in line.split():
                    if part.isdigit():
                        vram_mb = int(part)
                        break

        if name == "Unknown GPU":
            return None

        if vram_mb == 0:
            vram_mb = _estimate_vram_from_name(name)

        return GpuInfo(name=name, vram_mb=vram_mb, api="vulkan")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _detect_gpu_cuda() -> GpuInfo | None:
    """Detect GPU via NVIDIA CUDA."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        line = result.stdout.strip()
        if not line:
            return None

        parts = line.split(",")
        name = parts[0].strip()
        vram_mb = int(parts[1].strip()) if len(parts) > 1 else 0

        return GpuInfo(name=name, vram_mb=vram_mb, api="cuda")
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def _detect_gpu_wmi() -> GpuInfo | None:
    """Detect GPU via WMI/PowerShell on Windows (fallback)."""
    if platform.system() != "Windows":
        return None
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name, AdapterRAM | "
                "ConvertTo-Json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        data = json.loads(result.stdout)
        if isinstance(data, list):
            gpu = data[0] if data else None
        elif isinstance(data, dict):
            gpu = data
        else:
            return None

        if not gpu or not gpu.get("Name"):
            return None

        name = gpu["Name"]
        vram_mb = gpu.get("AdapterRAM", 0)
        if isinstance(vram_mb, (int, float)):
            vram_mb = int(vram_mb // (1024 * 1024))
        else:
            vram_mb = _estimate_vram_from_name(name)

        if vram_mb == 0:
            vram_mb = _estimate_vram_from_name(name)

        api = "cuda" if "nvidia" in name.lower() else "vulkan"
        return GpuInfo(name=name, vram_mb=vram_mb, api=api)
    except (
        OSError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        return None


def _estimate_vram_from_name(name: str) -> int:
    """Estimate VRAM from GPU model name using common knowledge."""
    name_lower = name.lower()
    estimates = {
        "rx 7600": 8192,
        "rx 6600": 8192,
        "rx 6700": 12288,
        "rx 6800": 16384,
        "rx 7800": 16384,
        "rx 7900": 24576,
        "rtx 3060": 12288,
        "rtx 3070": 8192,
        "rtx 3080": 10240,
        "rtx 3090": 24576,
        "rtx 4060": 8192,
        "rtx 4070": 12288,
        "rtx 4080": 16384,
        "rtx 4090": 24576,
    }
    for model, vram in estimates.items():
        if model in name_lower:
            return vram
    return 4096


def detect_hardware() -> HardwareProfile:
    """Detect complete hardware profile and determine optimal mode."""
    cpu = detect_cpu()
    ram_mb = detect_ram_mb()
    gpu = detect_gpu()
    mode = _determine_mode(cpu, ram_mb, gpu)

    profile = HardwareProfile(cpu=cpu, ram_mb=ram_mb, gpu=gpu, mode=mode)
    logger.info("Hardware detected: %s", profile.summary)
    return profile


def _determine_mode(cpu: CpuInfo, ram_mb: int, gpu: GpuInfo) -> PerformanceMode:
    """Determine performance mode based on hardware capabilities."""
    ram_gb = ram_mb / 1024

    # Tier 1: completo — 7B models, full features
    if ram_gb >= 24 and cpu.physical_cores >= 6 and gpu.vram_mb >= 6000:
        return PerformanceMode.COMPLETO

    # Tier 2: completo with reduced context — 7B on GPU
    if ram_gb >= 16 and gpu.vram_mb >= 6000:
        return PerformanceMode.COMPLETO

    # Tier 3: leve — 3B models for limited hardware
    if ram_gb >= 8 and cpu.physical_cores >= 2:
        return PerformanceMode.LEVE

    # Tier 4: very limited — 3B with small context
    if ram_gb >= 6:
        return PerformanceMode.LEVE

    return PerformanceMode.LEVE


# Hardware thresholds for model selection
@dataclass(frozen=True)
class ModelRequirements:
    """Minimum and recommended hardware requirements for a model."""

    min_ram_gb: float
    recommended_ram_gb: float
    min_vram_mb: int
    recommended_vram_mb: int
    min_cpu_cores: int
    estimated_tokens_per_sec_cpu: int
    estimated_tokens_per_sec_gpu: int


MODEL_REQUIREMENTS: dict[str, ModelRequirements] = {
    "qwen3-4b-q4km": ModelRequirements(
        min_ram_gb=8,
        recommended_ram_gb=12,
        min_vram_mb=2500,
        recommended_vram_mb=4096,
        min_cpu_cores=2,
        estimated_tokens_per_sec_cpu=12,
        estimated_tokens_per_sec_gpu=42,
    ),
    "qwen3-8b-q4km": ModelRequirements(
        min_ram_gb=12,
        recommended_ram_gb=24,
        min_vram_mb=5000,
        recommended_vram_mb=8192,
        min_cpu_cores=4,
        estimated_tokens_per_sec_cpu=7,
        estimated_tokens_per_sec_gpu=28,
    ),
    "qwen3-14b-q4km": ModelRequirements(
        min_ram_gb=20,
        recommended_ram_gb=32,
        min_vram_mb=7000,
        recommended_vram_mb=12288,
        min_cpu_cores=6,
        estimated_tokens_per_sec_cpu=4,
        estimated_tokens_per_sec_gpu=16,
    ),
    "qwen2.5-vl-3b-q4km": ModelRequirements(
        min_ram_gb=8,
        recommended_ram_gb=16,
        min_vram_mb=3000,
        recommended_vram_mb=4096,
        min_cpu_cores=2,
        estimated_tokens_per_sec_cpu=10,
        estimated_tokens_per_sec_gpu=34,
    ),
    "deepseek-r1-distill-qwen-7b-q4km": ModelRequirements(
        min_ram_gb=12,
        recommended_ram_gb=24,
        min_vram_mb=5000,
        recommended_vram_mb=8192,
        min_cpu_cores=4,
        estimated_tokens_per_sec_cpu=5,
        estimated_tokens_per_sec_gpu=20,
    ),
    "deepseek-r1-distill-qwen-14b-q4km": ModelRequirements(
        min_ram_gb=20,
        recommended_ram_gb=32,
        min_vram_mb=7000,
        recommended_vram_mb=12288,
        min_cpu_cores=6,
        estimated_tokens_per_sec_cpu=3,
        estimated_tokens_per_sec_gpu=12,
    ),
    "qwen2.5-vl-7b-q4km": ModelRequirements(
        min_ram_gb=12,
        recommended_ram_gb=24,
        min_vram_mb=4096,
        recommended_vram_mb=6000,
        min_cpu_cores=4,
        estimated_tokens_per_sec_cpu=6,
        estimated_tokens_per_sec_gpu=30,
    ),
    "qwen2.5-vl-7b-q5km": ModelRequirements(
        min_ram_gb=14,
        recommended_ram_gb=24,
        min_vram_mb=5000,
        recommended_vram_mb=6000,
        min_cpu_cores=4,
        estimated_tokens_per_sec_cpu=5,
        estimated_tokens_per_sec_gpu=28,
    ),
    "qwen2.5-vl-7b-q6k": ModelRequirements(
        min_ram_gb=16,
        recommended_ram_gb=32,
        min_vram_mb=6000,
        recommended_vram_mb=8000,
        min_cpu_cores=6,
        estimated_tokens_per_sec_cpu=4,
        estimated_tokens_per_sec_gpu=25,
    ),
    "gemma3-4b-q4km": ModelRequirements(
        min_ram_gb=8,
        recommended_ram_gb=16,
        min_vram_mb=3000,
        recommended_vram_mb=4096,
        min_cpu_cores=2,
        estimated_tokens_per_sec_cpu=10,
        estimated_tokens_per_sec_gpu=35,
    ),
    "qwen2.5-3b-q8": ModelRequirements(
        min_ram_gb=6,
        recommended_ram_gb=12,
        min_vram_mb=3000,
        recommended_vram_mb=4096,
        min_cpu_cores=2,
        estimated_tokens_per_sec_cpu=12,
        estimated_tokens_per_sec_gpu=40,
    ),
    "llama3.2-3b-q5km": ModelRequirements(
        min_ram_gb=6,
        recommended_ram_gb=12,
        min_vram_mb=2500,
        recommended_vram_mb=4096,
        min_cpu_cores=2,
        estimated_tokens_per_sec_cpu=14,
        estimated_tokens_per_sec_gpu=45,
    ),
    "qwen3.5-35b-a3b-q4km": ModelRequirements(
        min_ram_gb=16,
        recommended_ram_gb=32,
        min_vram_mb=4096,
        recommended_vram_mb=8000,
        min_cpu_cores=6,
        estimated_tokens_per_sec_cpu=3,
        estimated_tokens_per_sec_gpu=20,
    ),
}


def get_model_requirements(model_id: str) -> ModelRequirements | None:
    """Get hardware requirements for a specific model."""
    return MODEL_REQUIREMENTS.get(model_id)


def estimate_tokens_per_sec(model_id: str, profile: HardwareProfile) -> int:
    """Estimate tokens per second for a model on given hardware."""
    reqs = get_model_requirements(model_id)
    if reqs is None:
        return 5

    if profile.has_gpu and profile.gpu.vram_mb >= reqs.min_vram_mb:
        ratio = min(profile.gpu.vram_mb / reqs.recommended_vram_mb, 1.0)
        return int(reqs.estimated_tokens_per_sec_gpu * ratio)

    if profile.ram_mb >= reqs.min_ram_gb * 1024:
        ratio = min(profile.cpu.physical_cores / 4, 1.0)
        return int(reqs.estimated_tokens_per_sec_cpu * ratio)

    return 3
