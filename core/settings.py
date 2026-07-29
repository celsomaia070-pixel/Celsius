"""Application settings with pydantic-settings for external configuration."""

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.modules import default_enabled_module_ids, normalize_module_ids

ASSISTANT_NAME = "Celsius"
ASSISTANT_PROFILE = "Agente Multimodal Local de IA"
CUSTOMER_PROFILE_FIELDS = (
    "user_name",
    "company_name",
    "company_sector",
    "company_size",
    "company_description",
    "user_role",
    "preferred_tone",
    "business_context",
    "main_needs",
    "timezone",
    "local_offline_required",
)
MODULES_FIELDS = (
    "enabled",
    "sidebar_visible",
    "first_setup_completed",
    "module_configs",
)
RESPONSE_STYLE_FIELDS = (
    "mode",
    "temperature",
    "top_p",
    "short_answer_max_chars",
    "max_simple_sentences",
)
VOICE_FIELDS = (
    "enabled",
    "provider",
    "voice",
    "rate",
    "pitch",
    "volume",
    "max_playback_ms",
)
MOBILE_ACCESS_FIELDS = (
    "enabled",
    "host",
    "port",
    "pairing_token",
    "allow_lan",
    "voice_commands_enabled",
    "use_https",
)


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

    owner_name: str = ""

    @property
    def name(self) -> str:
        return ASSISTANT_NAME

    @property
    def profile(self) -> str:
        return ASSISTANT_PROFILE


class CustomerSettings(BaseSettings):
    """Customer/company context for this local Celsius installation."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_CUSTOMER_")

    user_name: str = ""
    company_name: str = ""
    company_sector: str = ""
    company_size: str = ""
    company_description: str = ""
    user_role: str = ""
    preferred_tone: str = "profissional e direto"
    business_context: str = ""
    main_needs: str = ""
    timezone: str = "America/Sao_Paulo"
    local_offline_required: bool = True

    def is_configured(self) -> bool:
        return any(
            (
                self.user_name.strip(),
                self.company_name.strip(),
                self.company_sector.strip(),
                self.company_description.strip(),
                self.user_role.strip(),
                self.business_context.strip(),
                self.main_needs.strip(),
            )
        )

    def to_storage(self) -> dict[str, str | bool]:
        return {field: getattr(self, field) for field in CUSTOMER_PROFILE_FIELDS}

    def apply_storage(self, data: dict, *, preserve_explicit: bool = True) -> None:
        explicit_fields = self.model_fields_set if preserve_explicit else set()
        for field in CUSTOMER_PROFILE_FIELDS:
            if preserve_explicit and field in explicit_fields:
                continue
            if field in data:
                setattr(self, field, data[field])

    def prompt_context(self) -> str:
        if not self.is_configured():
            return ""

        lines = [
            "## Perfil do Cliente/Empresa",
            "O Celsius esta trabalhando para este usuario ou empresa nesta instalacao local.",
        ]
        if self.user_name.strip():
            lines.append(f"- Usuario principal: {self.user_name.strip()}")
        if self.company_name.strip():
            lines.append(f"- Empresa: {self.company_name.strip()}")
        if self.company_sector.strip():
            lines.append(f"- Setor/atividade: {self.company_sector.strip()}")
        if self.company_size.strip():
            lines.append(f"- Porte da empresa: {self.company_size.strip()}")
        if self.company_description.strip():
            lines.append(f"- Descricao da empresa: {self.company_description.strip()}")
        if self.user_role.strip():
            lines.append(f"- Papel do usuario: {self.user_role.strip()}")
        if self.preferred_tone.strip():
            lines.append(f"- Tom preferido: {self.preferred_tone.strip()}")
        if self.timezone.strip():
            lines.append(f"- Fuso horario local: {self.timezone.strip()}")
        if self.local_offline_required:
            lines.append(
                "- Privacidade: priorize processamento local/offline e nao exponha dados da empresa."
            )
        if self.business_context.strip():
            lines.append("- Contexto de negocio:")
            lines.append(self.business_context.strip())
        if self.main_needs.strip():
            lines.append("- Necessidades principais:")
            lines.append(self.main_needs.strip())
        lines.append(
            "Use esse perfil como contexto preferencial para exemplos, prioridades e dados da empresa, "
            "mas nao limite o escopo do Celsius ao setor cadastrado."
        )
        lines.append(
            "Quando o usuario pedir assuntos gerais, estudos, redacao, tecnologia, cultura, "
            "programacao ou explicacoes fora do negocio, responda normalmente sem recusar por nao ser "
            "o segmento da empresa."
        )
        lines.append(
            "Nao trate o setor da empresa como regra fixa de permissao; ele apenas orienta contexto."
        )
        return "\n".join(lines)


class CompanyModulesSettings(BaseSettings):
    """Enabled modules for the current company profile."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_MODULES_")

    enabled: list[str] = Field(default_factory=default_enabled_module_ids)
    sidebar_visible: dict[str, bool] = Field(default_factory=dict)
    first_setup_completed: bool = False
    module_configs: dict[str, dict] = Field(default_factory=dict)

    def model_post_init(self, __context) -> None:
        self.enabled = normalize_module_ids(self.enabled)

    def to_storage(self) -> dict:
        return {field: getattr(self, field) for field in MODULES_FIELDS}

    def apply_storage(self, data: dict, *, preserve_explicit: bool = True) -> None:
        explicit_fields = self.model_fields_set if preserve_explicit else set()
        for field in MODULES_FIELDS:
            if preserve_explicit and field in explicit_fields:
                continue
            if field in data:
                setattr(self, field, data[field])
        self.enabled = normalize_module_ids(self.enabled)

    def set_enabled(self, module_ids) -> None:
        self.enabled = normalize_module_ids(module_ids)

    def is_enabled(self, module_id: str) -> bool:
        return module_id in set(normalize_module_ids(self.enabled))


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


class ResponseStyleSettings(BaseSettings):
    """Response tone and sampling settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_RESPONSE_")

    mode: Literal["natural", "tecnico", "relatorio"] = "natural"
    temperature: float = 0.45
    top_p: float = 0.9
    short_answer_max_chars: int = 180
    max_simple_sentences: int = 3

    def prompt_context(self) -> str:
        lines = [
            "## Estilo de Conversa",
            "- Fale de forma natural, como um parceiro de trabalho competente.",
            "- Para perguntas simples, responda em 1 a 3 frases, sem estrutura desnecessaria.",
            "- Para tarefas tecnicas, use passos claros e exemplos curtos quando ajudarem.",
            "- Para relatorios, analises e documentos, use topicos, tabelas e conclusoes praticas.",
            "- Evite soar como manual, contrato ou texto engessado.",
            "- Nao comece toda resposta com confirmacoes genericas.",
            "- Use o historico recente para manter continuidade de conversa.",
        ]
        if self.mode == "tecnico":
            lines.extend(
                [
                    "- Modo atual: tecnico.",
                    "- Priorize precisao, criterios, riscos e verificacao.",
                ]
            )
        elif self.mode == "relatorio":
            lines.extend(
                [
                    "- Modo atual: relatorio.",
                    "- Priorize estrutura executiva, comparativos, indicadores e proximas acoes.",
                ]
            )
        else:
            lines.extend(
                [
                    "- Modo atual: natural.",
                    "- Priorize respostas humanas, diretas e proporcionais ao tamanho da pergunta.",
                ]
            )
        return "\n".join(lines)

    def to_storage(self) -> dict[str, str | int | float]:
        return {field: getattr(self, field) for field in RESPONSE_STYLE_FIELDS}

    def apply_storage(self, data: dict, *, preserve_explicit: bool = True) -> None:
        explicit_fields = self.model_fields_set if preserve_explicit else set()
        for field in RESPONSE_STYLE_FIELDS:
            if preserve_explicit and field in explicit_fields:
                continue
            if field in data:
                setattr(self, field, data[field])


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
    max_pdf_size_mb: int = 300
    large_pdf_page_limit: int = 80
    doc_text_limit: int = 12000
    doc_extensions: tuple[str, ...] = (".pdf", ".docx", ".odt", ".ods", ".odp")
    image_extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
    audio_extensions: tuple[str, ...] = (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".webm")


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

    theme: Literal["light", "dark", "system"] = "light"
    language: str = "pt-BR"
    font_size: int = 10
    show_sidebar: bool = True
    animation_enabled: bool = True
    command_palette_enabled: bool = True
    jarvis_enabled: bool = True
    jarvis_particle_count: int = 800
    jarvis_fps: int = 60


class VoiceSettings(BaseSettings):
    """Voice output settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_VOICE_")

    enabled: bool = True
    provider: str = "edge-tts"
    voice: str = "pt-BR-AntonioNeural"
    rate: str = "+5%"
    pitch: str = "-2Hz"
    volume: str = "+0%"
    max_playback_ms: int = 120000

    def to_storage(self) -> dict[str, str | int | bool]:
        return {field: getattr(self, field) for field in VOICE_FIELDS}

    def apply_storage(self, data: dict, *, preserve_explicit: bool = True) -> None:
        explicit_fields = self.model_fields_set if preserve_explicit else set()
        for field in VOICE_FIELDS:
            if preserve_explicit and field in explicit_fields:
                continue
            if field in data:
                setattr(self, field, data[field])


class MobileAccessSettings(BaseSettings):
    """Local mobile access settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_MOBILE_")

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8787
    pairing_token: str = ""
    allow_lan: bool = False
    voice_commands_enabled: bool = True
    use_https: bool = True

    def to_storage(self) -> dict[str, str | int | bool]:
        return {field: getattr(self, field) for field in MOBILE_ACCESS_FIELDS}

    def apply_storage(self, data: dict, *, preserve_explicit: bool = True) -> None:
        explicit_fields = self.model_fields_set if preserve_explicit else set()
        for field in MOBILE_ACCESS_FIELDS:
            if preserve_explicit and field in explicit_fields:
                continue
            if field in data:
                setattr(self, field, data[field])


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
    customer: CustomerSettings = Field(default_factory=CustomerSettings)
    modules: CompanyModulesSettings = Field(default_factory=CompanyModulesSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)
    response: ResponseStyleSettings = Field(default_factory=ResponseStyleSettings)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    file: FileSettings = Field(default_factory=FileSettings)
    inventory: InventorySettings = Field(default_factory=InventorySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    ui: UiSettings = Field(default_factory=UiSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    mobile: MobileAccessSettings = Field(default_factory=MobileAccessSettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)

    memorias_file: Path = Field(default_factory=lambda: _get_base_dir() / "memorias.json")
    chats_file: Path = Field(default_factory=lambda: _get_base_dir() / "chats.json")
    inventory_file: Path = Field(default_factory=lambda: _get_base_dir() / "inventory.json")
    audio_temp_file: Path = Field(default_factory=lambda: _get_base_dir() / "temp_kfu_voice.mp3")
    audio_mic_file: Path = Field(default_factory=lambda: _get_base_dir() / "temp_audio.wav")

    def model_post_init(self, __context) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._load_customer_profile()
        self._load_local_preferences()
        self._sync_legacy_owner_name()

    @property
    def customer_profile_file(self) -> Path:
        return self.data_dir / "customer_profile.json"

    @property
    def local_preferences_file(self) -> Path:
        return self.data_dir / "celsius_settings.json"

    def _load_customer_profile(self) -> None:
        path = self.customer_profile_file
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            self.customer.apply_storage(data, preserve_explicit=True)

    def _load_local_preferences(self) -> None:
        path = self.local_preferences_file
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        if isinstance(data.get("customer"), dict):
            self.customer.apply_storage(data["customer"], preserve_explicit=True)
        if isinstance(data.get("response"), dict):
            self.response.apply_storage(data["response"], preserve_explicit=True)
        if isinstance(data.get("voice"), dict):
            self.voice.apply_storage(data["voice"], preserve_explicit=True)
        if isinstance(data.get("modules"), dict):
            self.modules.apply_storage(data["modules"], preserve_explicit=True)
        if isinstance(data.get("mobile"), dict):
            self.mobile.apply_storage(data["mobile"], preserve_explicit=True)

    def _sync_legacy_owner_name(self) -> None:
        if self.assistant.owner_name and not self.customer.user_name:
            self.customer.user_name = self.assistant.owner_name
        elif self.customer.user_name and not self.assistant.owner_name:
            self.assistant.owner_name = self.customer.user_name

    def save_customer_profile(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.assistant.owner_name = self.customer.user_name
        path = self.customer_profile_file
        path.write_text(
            json.dumps(self.customer.to_storage(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.save_local_preferences()
        return path

    def save_local_preferences(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.assistant.owner_name = self.customer.user_name
        path = self.local_preferences_file
        path.write_text(
            json.dumps(
                {
                    "customer": self.customer.to_storage(),
                    "modules": self.modules.to_storage(),
                    "response": self.response.to_storage(),
                    "voice": self.voice.to_storage(),
                    "mobile": self.mobile.to_storage(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

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

    @property
    def customer_prompt_context(self) -> str:
        return self.customer.prompt_context()

    @property
    def response_style_prompt_context(self) -> str:
        return self.response.prompt_context()

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
