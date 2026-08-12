"""Product-oriented model catalog and routing presets for Celsius.

This module keeps the user-facing choices simple while preserving stable model
ids for the local runtime.  The UI can expose presets such as "Rapido" or
"Documentos e imagens"; the router can still resolve the actual GGUF model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelCapability(str, Enum):
    """Capabilities used by the model router and setup screens."""

    CHAT = "chat"
    FAST = "fast"
    QUALITY = "quality"
    REASONING = "reasoning"
    VISION = "vision"
    DOCUMENTS = "documents"
    CODE = "code"
    EMBEDDING = "embedding"


class ModelPreset(str, Enum):
    """User-facing model modes."""

    FAST = "rapido"
    BALANCED = "equilibrado"
    QUALITY = "qualidade"
    DEEP_ANALYSIS = "analise_profunda"
    DOCUMENTS = "documentos_imagens"


@dataclass(frozen=True)
class CelsiusModelSpec:
    """Stable metadata for an LLM or auxiliary model used by Celsius."""

    id: str
    name: str
    family: str
    role: str
    capabilities: tuple[ModelCapability, ...]
    recommended_quant: str
    size_gb: float
    context_tokens: int
    min_ram_gb: int
    recommended_ram_gb: int
    min_vram_mb: int
    recommended_vram_mb: int
    local_first: bool = True
    commercial_friendly: bool = True
    experimental: bool = False
    notes: str = ""

    def has(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities


CELSIUS_MODEL_CATALOG: dict[str, CelsiusModelSpec] = {
    "qwen3-4b-q4km": CelsiusModelSpec(
        id="qwen3-4b-q4km",
        name="Qwen3 4B Instruct",
        family="Qwen3",
        role="Modo leve e comandos rapidos",
        capabilities=(ModelCapability.CHAT, ModelCapability.FAST),
        recommended_quant="Q4_K_M",
        size_gb=2.8,
        context_tokens=32768,
        min_ram_gb=8,
        recommended_ram_gb=12,
        min_vram_mb=2500,
        recommended_vram_mb=4096,
        notes="Bom para comandos, agenda, estoque e respostas curtas.",
    ),
    "qwen3-8b-q4km": CelsiusModelSpec(
        id="qwen3-8b-q4km",
        name="Qwen3 8B Instruct",
        family="Qwen3",
        role="Modelo padrao equilibrado",
        capabilities=(ModelCapability.CHAT, ModelCapability.QUALITY),
        recommended_quant="Q4_K_M",
        size_gb=5.2,
        context_tokens=131072,
        min_ram_gb=12,
        recommended_ram_gb=24,
        min_vram_mb=5000,
        recommended_vram_mb=8192,
        notes="Melhor padrao para PME: portugues, contexto longo e bom custo local.",
    ),
    "qwen3-14b-q4km": CelsiusModelSpec(
        id="qwen3-14b-q4km",
        name="Qwen3 14B Instruct",
        family="Qwen3",
        role="Modo qualidade",
        capabilities=(ModelCapability.CHAT, ModelCapability.QUALITY),
        recommended_quant="Q4_K_M",
        size_gb=8.8,
        context_tokens=131072,
        min_ram_gb=20,
        recommended_ram_gb=32,
        min_vram_mb=7000,
        recommended_vram_mb=12288,
        notes="Mais qualidade, mas pode ser lento em GPU de 8GB.",
    ),
    "qwen2.5-vl-3b-q4km": CelsiusModelSpec(
        id="qwen2.5-vl-3b-q4km",
        name="Qwen2.5 VL 3B",
        family="Qwen2.5-VL",
        role="Documentos e imagens leve",
        capabilities=(ModelCapability.VISION, ModelCapability.DOCUMENTS, ModelCapability.FAST),
        recommended_quant="Q4_K_M",
        size_gb=2.7,
        context_tokens=32768,
        min_ram_gb=8,
        recommended_ram_gb=16,
        min_vram_mb=3000,
        recommended_vram_mb=4096,
        notes="Opcao leve para imagens, scans e PDFs com layout.",
    ),
    "qwen2.5-vl-7b-q4km": CelsiusModelSpec(
        id="qwen2.5-vl-7b-q4km",
        name="Qwen2.5 VL 7B",
        family="Qwen2.5-VL",
        role="Documentos e imagens",
        capabilities=(
            ModelCapability.CHAT,
            ModelCapability.VISION,
            ModelCapability.DOCUMENTS,
            ModelCapability.QUALITY,
        ),
        recommended_quant="Q4_K_M",
        size_gb=4.5,
        context_tokens=32768,
        min_ram_gb=12,
        recommended_ram_gb=24,
        min_vram_mb=4096,
        recommended_vram_mb=6000,
        notes="Bom para notas, tabelas, prints e documentos empresariais.",
    ),
    "deepseek-r1-distill-qwen-7b-q4km": CelsiusModelSpec(
        id="deepseek-r1-distill-qwen-7b-q4km",
        name="DeepSeek R1 Distill Qwen 7B",
        family="DeepSeek-R1",
        role="Analise profunda leve",
        capabilities=(ModelCapability.REASONING, ModelCapability.CHAT),
        recommended_quant="Q4_K_M",
        size_gb=4.7,
        context_tokens=32768,
        min_ram_gb=12,
        recommended_ram_gb=24,
        min_vram_mb=5000,
        recommended_vram_mb=8192,
        notes="Use apenas para raciocinio longo; pode soar menos natural.",
    ),
    "deepseek-r1-distill-qwen-14b-q4km": CelsiusModelSpec(
        id="deepseek-r1-distill-qwen-14b-q4km",
        name="DeepSeek R1 Distill Qwen 14B",
        family="DeepSeek-R1",
        role="Analise profunda qualidade",
        capabilities=(ModelCapability.REASONING, ModelCapability.QUALITY),
        recommended_quant="Q4_K_M",
        size_gb=8.8,
        context_tokens=32768,
        min_ram_gb=20,
        recommended_ram_gb=32,
        min_vram_mb=7000,
        recommended_vram_mb=12288,
        notes="Opcao futura para maquinas mais fortes.",
    ),
    "qwen3-embedding-0.6b": CelsiusModelSpec(
        id="qwen3-embedding-0.6b",
        name="Qwen3 Embedding 0.6B",
        family="Qwen3-Embedding",
        role="Memoria e busca semantica leve",
        capabilities=(ModelCapability.EMBEDDING,),
        recommended_quant="float16/int8",
        size_gb=1.2,
        context_tokens=32768,
        min_ram_gb=4,
        recommended_ram_gb=8,
        min_vram_mb=0,
        recommended_vram_mb=0,
        notes="Padrao recomendado para RAG/memoria com baixo custo.",
    ),
    "qwen3-embedding-4b": CelsiusModelSpec(
        id="qwen3-embedding-4b",
        name="Qwen3 Embedding 4B",
        family="Qwen3-Embedding",
        role="Memoria e busca semantica qualidade",
        capabilities=(ModelCapability.EMBEDDING,),
        recommended_quant="float16/int8",
        size_gb=7.5,
        context_tokens=32768,
        min_ram_gb=12,
        recommended_ram_gb=24,
        min_vram_mb=0,
        recommended_vram_mb=0,
        notes="Opcao de qualidade para bases de conhecimento maiores.",
    ),
    # Legacy models kept for compatibility with existing installations.
    "llama3.2-3b-q5km": CelsiusModelSpec(
        id="llama3.2-3b-q5km",
        name="Llama 3.2 3B",
        family="Llama",
        role="Legado rapido",
        capabilities=(ModelCapability.CHAT, ModelCapability.FAST),
        recommended_quant="Q5_K_M",
        size_gb=2.5,
        context_tokens=8192,
        min_ram_gb=6,
        recommended_ram_gb=12,
        min_vram_mb=2500,
        recommended_vram_mb=4096,
        commercial_friendly=False,
        notes="Mantido por compatibilidade; novo padrao leve e Qwen3 4B.",
    ),
    "qwen2.5-3b-q8": CelsiusModelSpec(
        id="qwen2.5-3b-q8",
        name="Qwen2.5 3B",
        family="Qwen2.5",
        role="Legado rapido",
        capabilities=(ModelCapability.CHAT, ModelCapability.FAST),
        recommended_quant="Q8_0",
        size_gb=3.4,
        context_tokens=32768,
        min_ram_gb=6,
        recommended_ram_gb=12,
        min_vram_mb=3000,
        recommended_vram_mb=4096,
        notes="Mantido por compatibilidade.",
    ),
    "gemma3-4b-q4km": CelsiusModelSpec(
        id="gemma3-4b-q4km",
        name="Gemma 3 4B",
        family="Gemma",
        role="Alternativa leve",
        capabilities=(ModelCapability.CHAT, ModelCapability.FAST, ModelCapability.VISION),
        recommended_quant="Q4_K_M",
        size_gb=3.2,
        context_tokens=131072,
        min_ram_gb=8,
        recommended_ram_gb=16,
        min_vram_mb=3000,
        recommended_vram_mb=4096,
        notes="Alternativa leve; manter como opcao, nao como unica base.",
    ),
}


MODEL_PRESETS: dict[ModelPreset, str] = {
    ModelPreset.FAST: "qwen3-4b-q4km",
    ModelPreset.BALANCED: "qwen2.5-vl-7b-q4km",
    ModelPreset.QUALITY: "qwen3-14b-q4km",
    ModelPreset.DEEP_ANALYSIS: "deepseek-r1-distill-qwen-7b-q4km",
    ModelPreset.DOCUMENTS: "qwen2.5-vl-7b-q4km",
}


DEFAULT_LLM_MODEL = MODEL_PRESETS[ModelPreset.BALANCED]
FAST_LLM_MODEL = MODEL_PRESETS[ModelPreset.FAST]
QUALITY_LLM_MODEL = MODEL_PRESETS[ModelPreset.QUALITY]
REASONING_LLM_MODEL = MODEL_PRESETS[ModelPreset.DEEP_ANALYSIS]
VISION_LLM_MODEL = MODEL_PRESETS[ModelPreset.DOCUMENTS]
DEFAULT_EMBEDDING_MODEL = "qwen3-embedding-0.6b"


def get_model_spec(model_id: str) -> CelsiusModelSpec | None:
    return CELSIUS_MODEL_CATALOG.get(model_id)


def get_preset_model(preset: ModelPreset | str) -> str:
    if isinstance(preset, str):
        preset = ModelPreset(preset)
    return MODEL_PRESETS[preset]


def models_with_capability(capability: ModelCapability | str) -> list[CelsiusModelSpec]:
    if isinstance(capability, str):
        capability = ModelCapability(capability)
    return [model for model in CELSIUS_MODEL_CATALOG.values() if model.has(capability)]


def user_facing_model_modes() -> dict[str, str]:
    return {
        ModelPreset.FAST.value: "Rapido",
        ModelPreset.BALANCED.value: "Equilibrado",
        ModelPreset.QUALITY.value: "Qualidade",
        ModelPreset.DEEP_ANALYSIS.value: "Analise profunda",
        ModelPreset.DOCUMENTS.value: "Documentos e imagens",
    }
