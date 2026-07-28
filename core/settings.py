"""Application settings with pydantic-settings for external configuration."""

import sys
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class AssistantSettings(BaseSettings):
    """Assistant identity and behavior settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_ASSISTANT_")

    name: str = "Celsius"
    owner_name: str = ""
    profile: str = "agente multimodal de IA local"


class HardwareSettings(BaseSettings):
    """Hardware detection and performance mode settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_HARDWARE_")

    auto_detect: bool = True
    force_mode: Literal["auto", "leve", "completo", "custom"] = "auto"
    force_model: str = ""
    prefer_multimodal: bool = True


class ModelSettings(BaseSettings):
    """Model-related settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_MODEL_")

    default_llm_model: str = "qwen2.5-vl-7b-q4km"
    llm_model: str = "qwen2.5-vl-7b-q4km"
    fast_llm_model: str = "llama3.2-3b-q5km"
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    whisper_model: str = "small"
    num_ctx: int = 16384
    num_predict: int = 2500
    n_gpu_layers: int = -1
    n_batch: int = 1024
    n_threads: int = 0
    use_mmap: bool = True
    use_mlock: bool = True
    offload_kqv: bool = True
    flash_attn: bool = True
    auto_configured: bool = False


class RagSettings(BaseSettings):
    """RAG-related settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_RAG_")

    chunk_size: int = 600
    chunk_overlap: int = 80
    top_k: int = 5
    final_top_k: int = 3
    distance_threshold: float = 1.5
    enable_hybrid_search: bool = True
    bm25_weight: float = 0.3
    dense_weight: float = 0.7
    enable_reranking: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_top_k: int = 10


class MemorySettings(BaseSettings):
    """Memory-related settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_MEMORY_")

    max_history_session: int = 16
    memory_threshold: float = 0.15
    top_memories: int = 10
    inject_all_memories_limit: int = 15


class FileSettings(BaseSettings):
    """File processing settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_FILE_")

    max_file_size_mb: int = 50
    doc_text_limit: int = 12000
    doc_extensions: tuple[str, ...] = (".pdf", ".docx", ".odt", ".ods", ".odp")
    image_extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
    audio_extensions: tuple[str, ...] = (".mp3", ".wav", ".ogg", ".m4a", ".flac")


class InventorySettings(BaseSettings):
    """Inventory management settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_INVENTORY_")

    enabled: bool = True
    data_file: str = "inventory.json"
    kanban_columns: tuple[str, ...] = ("estoque", "em_falta", "encomendado", "arquivado")
    default_min_stock: int = 5
    default_max_stock: int = 100


class SecuritySettings(BaseSettings):
    """Security settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_SECURITY_")

    sandbox_enabled: bool = True
    sandbox_max_memory_mb: int = 256
    sandbox_max_cpu_seconds: int = 30
    sandbox_allowed_imports: tuple[str, ...] = (
        "math",
        "random",
        "datetime",
        "json",
        "re",
        "collections",
        "itertools",
        "statistics",
        "decimal",
        "fractions",
        "typing",
    )
    sandbox_blocked_imports: tuple[str, ...] = (
        "os",
        "sys",
        "subprocess",
        "shutil",
        "pathlib",
        "socket",
        "urllib",
        "requests",
        "http",
        "ftplib",
        "telnetlib",
        "smtplib",
        "poplib",
        "imaplib",
        "email",
        "pickle",
        "marshal",
        "shelve",
        "dbm",
        "sqlite3",
        "ctypes",
        "multiprocessing",
        "threading",
        "asyncio",
        "importlib",
        "pkgutil",
        "runpy",
        "code",
        "codeop",
        "exec",
        "eval",
        "compile",
    )
    path_traversal_protection: bool = True
    allowed_file_roots: tuple[str, ...] = ()


class TelemetrySettings(BaseSettings):
    """Telemetry/observability settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_TELEMETRY_")

    enabled: bool = False
    otlp_endpoint: str = "http://localhost:4317"
    otlp_insecure: bool = True
    service_name: str = "celsius"
    service_version: str = "1.0.0"
    sample_rate: float = 1.0
    log_level: LogLevel = LogLevel.INFO
    metrics_enabled: bool = True
    metrics_port: int = 9090


class UiSettings(BaseSettings):
    """UI settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_UI_")

    theme: Literal["light", "dark", "system"] = "system"
    language: str = "pt-BR"
    font_size: int = 10
    show_sidebar: bool = True
    animation_enabled: bool = True
    command_palette_enabled: bool = True
    jarvis_enabled: bool = True
    jarvis_particle_count: int = 800
    jarvis_fps: int = 30


class FeatureFlags(BaseSettings):
    """Feature flags for enabling/disabling modules."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_FEATURE_")

    conversations: bool = True
    inventory: bool = True
    rag: bool = True
    memory: bool = True
    web_search: bool = True
    web_browser: bool = True
    code_execution: bool = True
    voice_input: bool = True
    voice_output: bool = True
    image_analysis: bool = True
    document_processing: bool = True
    report_generation: bool = True
    multi_agent: bool = True
    model_router: bool = True


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    base_dir: Path = Field(default_factory=_get_base_dir)
    data_dir: Path = Field(default_factory=lambda: _get_base_dir() / "data")
    resources_dir: Path = Field(default_factory=lambda: _get_base_dir() / "resources")
    logs_dir: Path = Field(default_factory=lambda: _get_base_dir() / "logs")

    assistant: AssistantSettings = Field(default_factory=AssistantSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    file: FileSettings = Field(default_factory=FileSettings)
    inventory: InventorySettings = Field(default_factory=InventorySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    ui: UiSettings = Field(default_factory=UiSettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)

    memorias_file: Path = Field(default_factory=lambda: _get_base_dir() / "memorias.json")
    chats_file: Path = Field(default_factory=lambda: _get_base_dir() / "chats.json")
    inventory_file: Path = Field(default_factory=lambda: _get_base_dir() / "inventory.json")
    audio_temp_file: Path = Field(default_factory=lambda: _get_base_dir() / "temp_kfu_voice.mp3")
    audio_mic_file: Path = Field(default_factory=lambda: _get_base_dir() / "temp_audio.wav")

    def model_post_init(self, __context) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def default_llm_model(self) -> str:
        return self.model.default_llm_model

    @property
    def llm_model(self) -> str:
        return self.model.llm_model

    @llm_model.setter
    def llm_model(self, value: str) -> None:
        self.model.llm_model = value

    @property
    def fast_llm_model(self) -> str:
        return self.model.fast_llm_model

    @fast_llm_model.setter
    def fast_llm_model(self, value: str) -> None:
        self.model.fast_llm_model = value

    @property
    def embedding_model(self) -> str:
        return self.model.embedding_model

    @property
    def whisper_model(self) -> str:
        return self.model.whisper_model

    @property
    def num_ctx(self) -> int:
        return self.model.num_ctx

    @property
    def num_predict(self) -> int:
        return self.model.num_predict

    @property
    def max_history_session(self) -> int:
        return self.memory.max_history_session

    @property
    def memory_threshold(self) -> float:
        return self.memory.memory_threshold

    @property
    def top_memories(self) -> int:
        return self.memory.top_memories

    @property
    def inject_all_memories_limit(self) -> int:
        return self.memory.inject_all_memories_limit

    @property
    def max_file_size_mb(self) -> int:
        return self.file.max_file_size_mb

    @property
    def doc_text_limit(self) -> int:
        return self.file.doc_text_limit

    @property
    def doc_extensions(self) -> tuple[str, ...]:
        return self.file.doc_extensions

    @property
    def image_extensions(self) -> tuple[str, ...]:
        return self.file.image_extensions

    @property
    def audio_extensions(self) -> tuple[str, ...]:
        return self.file.audio_extensions

    @property
    def all_extensions(self) -> tuple[str, ...]:
        return self.doc_extensions + self.image_extensions + self.audio_extensions

    @property
    def file_filter(self) -> str:
        return " ".join(f"*{ext}" for ext in self.all_extensions)

    @property
    def assistant_name(self) -> str:
        return self.assistant.name

    @property
    def assistant_profile(self) -> str:
        return self.assistant.profile

    def is_module_enabled(self, module: str) -> bool:
        return bool(getattr(self.features, module, False))

    def get_resources_dir(self) -> Path:
        return self.resources_dir

    def get_model_path(self, model_id: str | None = None) -> Path:
        model_id = model_id or self.model.llm_model
        from core.config import get_model_by_id

        model = get_model_by_id(model_id)
        if model:
            return self.resources_dir / model.filename
        return self.resources_dir / "model.gguf"

    def get_mmproj_path(self, model_id: str | None = None) -> Path | None:
        model_id = model_id or self.model.llm_model
        from core.config import get_model_by_id

        model = get_model_by_id(model_id)
        if model and model.has_mmproj:
            path = self.resources_dir / model.mmproj_file
            return path if path.exists() else None
        return None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None


def get_feature_flags() -> FeatureFlags:
    return get_settings().features
