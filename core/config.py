import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GGUFModel:
    """Represents a downloadable GGUF model."""

    id: str
    name: str
    category: str  # "multimodal", "code", "fast"
    filename: str
    hf_repo: str
    hf_file: str
    size_gb: float
    quant: str
    has_mmproj: bool = False
    mmproj_file: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.quant}, {self.size_gb}GB)"


# ── Model registry ──────────────────────────────────────────────

GGUF_MODELS: list[GGUFModel] = [
    # Multimodal (visão + texto)
    GGUFModel(
        id="qwen2.5-vl-7b-q4km",
        name="Qwen2.5 VL 7B",
        category="multimodal",
        filename="qwen2.5-vl-7b-q4_k_m.gguf",
        hf_repo="ggml-org/Qwen2.5-VL-7B-Instruct-GGUF",
        hf_file="Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
        size_gb=4.5,
        quant="Q4_K_M",
        has_mmproj=True,
        mmproj_file="mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf",
    ),
    GGUFModel(
        id="qwen2.5-vl-7b-q5km",
        name="Qwen2.5 VL 7B",
        category="multimodal",
        filename="qwen2.5-vl-7b-q5_k_m.gguf",
        hf_repo="ggml-org/Qwen2.5-VL-7B-Instruct-GGUF",
        hf_file="Qwen2.5-VL-7B-Instruct-Q5_K_M.gguf",
        size_gb=5.4,
        quant="Q5_K_M",
        has_mmproj=True,
        mmproj_file="mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf",
    ),
    GGUFModel(
        id="qwen2.5-vl-7b-q6k",
        name="Qwen2.5 VL 7B",
        category="multimodal",
        filename="qwen2.5-vl-7b-q6_k.gguf",
        hf_repo="ggml-org/Qwen2.5-VL-7B-Instruct-GGUF",
        hf_file="Qwen2.5-VL-7B-Instruct-Q6_K.gguf",
        size_gb=6.2,
        quant="Q6_K",
        has_mmproj=True,
        mmproj_file="mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf",
    ),
    GGUFModel(
        id="gemma3-4b-q4km",
        name="Gemma 3 4B",
        category="multimodal",
        filename="gemma-3-4b-it-Q4_K_M.gguf",
        hf_repo="bartowski/gemma-3-4b-it-GGUF",
        hf_file="gemma-3-4b-it-Q4_K_M.gguf",
        size_gb=3.2,
        quant="Q4_K_M",
        has_mmproj=True,
        mmproj_file="mmproj-gemma-3-4b-it-Q4_K_M.gguf",
    ),
    GGUFModel(
        id="qwen2.5-omni-7b-q4km",
        name="Qwen2.5 Omni 7B",
        category="multimodal",
        filename="qwen2.5-omni-7b-q4_k_m.gguf",
        hf_repo="ggml-org/Qwen2.5-Omni-7B-GGUF",
        hf_file="qwen2.5-omni-7b-q4_k_m.gguf",
        size_gb=4.5,
        quant="Q4_K_M",
        has_mmproj=False,
    ),
    # Código
    GGUFModel(
        id="qwen2.5-coder-7b-q5km",
        name="Qwen2.5 Coder 7B",
        category="code",
        filename="qwen2.5-coder-7b-q5_k_m.gguf",
        hf_repo="bartowski/Qwen2.5-Coder-7B-Instruct-GGUF",
        hf_file="Qwen2.5-Coder-7B-Instruct-Q5_K_M.gguf",
        size_gb=5.4,
        quant="Q5_K_M",
    ),
    GGUFModel(
        id="qwen2.5-coder-14b-q4km",
        name="Qwen2.5 Coder 14B",
        category="code",
        filename="qwen2.5-coder-14b-q4_k_m.gguf",
        hf_repo="bartowski/Qwen2.5-Coder-14B-Instruct-GGUF",
        hf_file="Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf",
        size_gb=8.7,
        quant="Q4_K_M",
    ),
    # Rápidos (leves)
    GGUFModel(
        id="qwen2.5-3b-q8",
        name="Qwen2.5 3B",
        category="fast",
        filename="qwen2.5-3b-instruct-q8_0.gguf",
        hf_repo="bartowski/Qwen2.5-3B-Instruct-GGUF",
        hf_file="Qwen2.5-3B-Instruct-Q8_0.gguf",
        size_gb=3.4,
        quant="Q8_0",
    ),
    GGUFModel(
        id="llama3.2-3b-q5km",
        name="Llama 3.2 3B",
        category="fast",
        filename="llama-3.2-3b-instruct-q5_k_m.gguf",
        hf_repo="bartowski/Llama-3.2-3B-Instruct-GGUF",
        hf_file="Llama-3.2-3B-Instruct-Q5_K_M.gguf",
        size_gb=2.5,
        quant="Q5_K_M",
    ),
    # Potentes (MoE / grandes)
    GGUFModel(
        id="qwen3.5-35b-a3b-q4km",
        name="Qwen3.5 35B-A3B",
        category="fast",
        filename="Qwen3.5-35B-A3B-Q4_K_M.gguf",
        hf_repo="bartowski/Qwen_Qwen3.5-35B-A3B-GGUF",
        hf_file="Qwen_Qwen3.5-35B-A3B-Q4_K_M.gguf",
        size_gb=19.0,
        quant="Q4_K_M",
    ),
]


def get_model_by_id(model_id: str) -> GGUFModel | None:
    return next((m for m in GGUF_MODELS if m.id == model_id), None)


# ── Settings ────────────────────────────────────────────────────


@dataclass
class Settings:
    base_dir: Path = field(default_factory=lambda: _get_base_dir())
    memorias_file: Path = field(init=False)
    chats_file: Path = field(init=False)
    inventory_file: Path = field(init=False)
    audio_temp_file: Path = field(init=False)
    audio_mic_file: Path = field(init=False)

    enabled_modules: tuple[str, ...] = ("conversas", "estoque")

    default_llm_model: str = "qwen2.5-vl-7b-q4km"
    llm_model: str = "qwen2.5-vl-7b-q4km"
    fast_llm_model: str = "llama3.2-3b-q5km"  # Small fast model for simple tasks
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    whisper_model: str = "small"

    max_file_size_mb: int = 50
    doc_text_limit: int = 12000
    num_ctx: int = 16384
    num_predict: int = 2500
    max_history_session: int = 16
    memory_threshold: float = 0.15
    top_memories: int = 10
    inject_all_memories_limit: int = 15

    doc_extensions: tuple[str, ...] = (".pdf", ".docx", ".odt", ".ods", ".odp")
    image_extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
    audio_extensions: tuple[str, ...] = (".mp3", ".wav", ".ogg", ".m4a", ".flac")

    def __post_init__(self):
        self.memorias_file = self.base_dir / "memorias.json"
        self.chats_file = self.base_dir / "chats.json"
        self.inventory_file = self.base_dir / "inventory.json"
        self.audio_temp_file = self.base_dir / "temp_kfu_voice.mp3"
        self.audio_mic_file = self.base_dir / "temp_audio.wav"

    def is_module_enabled(self, module: str) -> bool:
        return module in self.enabled_modules

    @property
    def all_extensions(self) -> tuple[str, ...]:
        return self.doc_extensions + self.image_extensions + self.audio_extensions

    @property
    def file_filter(self) -> str:
        return " ".join(f"*{e}" for e in self.all_extensions)

    def set_llm_model(self, model_id: str) -> None:
        self.llm_model = model_id
        # Update backwards compat
        globals()["MODELO_LLM"] = model_id

    def get_resources_dir(self) -> Path:
        """Get path to resources directory (works with PyInstaller)."""
        return _get_base_dir() / "resources"

    def get_model_path(self, model_id: str | None = None) -> Path:
        """Get path to a GGUF model file by id. Defaults to current llm_model."""
        model_id = model_id or self.llm_model
        model = get_model_by_id(model_id)
        if model:
            return self.get_resources_dir() / model.filename
        # Fallback for legacy
        return self.get_resources_dir() / "model.gguf"

    def get_mmproj_path(self, model_id: str | None = None) -> Path | None:
        """Get path to mmproj file for vision support, if available."""
        model_id = model_id or self.llm_model
        model = get_model_by_id(model_id)
        if model and model.has_mmproj:
            path = self.get_resources_dir() / model.mmproj_file
            return path if path.exists() else None
        return None


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


settings = Settings()


def get_settings():
    """Return the canonical pydantic settings object.

    The legacy dataclass above is kept for constants and old imports, but
    runtime code should read from core.settings so .env overrides apply
    consistently across the app.
    """
    from core.settings import get_settings as _get_canonical_settings

    return _get_canonical_settings()


# Backwards compatibility
DIRETORIO_BASE = settings.base_dir
ARQUIVO_MEMORIAS = settings.memorias_file
ARQUIVO_AUDIO_TEMP = settings.audio_temp_file
ARQUIVO_AUDIO_MIC = settings.audio_mic_file
MODELO_LLM = settings.llm_model
MODELO_WHISPER = settings.whisper_model
LIMITE_TEXTO_DOCUMENTO = settings.doc_text_limit
NUM_CTX = settings.num_ctx
NUM_PREDICT = settings.num_predict
MAX_HISTORICO_SESSION = settings.max_history_session
THRESHOLD_MEMORIA = settings.memory_threshold
TOP_MEMORIAS = settings.top_memories
MAX_FILE_SIZE_BYTES = settings.max_file_size_mb * 1024 * 1024
