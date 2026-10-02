"""Application settings with pydantic-settings for external configuration."""

import json
import os
import sys
from collections.abc import Iterable, Mapping
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.file_security import restrict_private_file
from core.json_persistence import atomic_write_json
from core.model_catalog import DEFAULT_LLM_MODEL
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
    "detail_level",
    "temperature",
    "top_p",
    "short_answer_max_chars",
    "max_simple_sentences",
)
VOICE_FIELDS = (
    "enabled",
    "provider",
    "profile",
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
    "pairing_token_issued_at",
    "token_rotation_days",
    "session_ttl_seconds",
    "pairing_ttl_seconds",
    "max_browser_sessions",
    "allow_lan",
    "voice_commands_enabled",
    "use_https",
)
NOTIFICATION_FIELDS = (
    "enabled",
    "external_services_allowed",
    "require_confirmation",
    "default_channel",
    "whatsapp_provider",
    "whatsapp_phone_number_id",
    "whatsapp_token_env_var",
    "email_provider",
    "email_from",
    "sms_provider",
    "sms_sender_id",
)
SECURITY_FIELDS = (
    "sandbox_enabled",
    "path_traversal_protection",
    "allowed_file_roots",
)

APP_DATA_DIR_NAME = "Celsius"


def _get_install_dir() -> Path:
    """Return the read-only application directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _get_bundle_dir() -> Path:
    """Return the directory containing PyInstaller data files."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return _get_install_dir()


def _get_frozen_data_dir() -> Path:
    """Return a per-user writable directory for installed builds."""
    configured = os.environ.get("CELSIUS_BASE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / APP_DATA_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_DATA_DIR_NAME


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return _get_frozen_data_dir()
    return _get_install_dir()


def _get_default_data_dir() -> Path:
    """Where persistent state lives when the caller supplies no ``data_dir``."""
    if getattr(sys, "frozen", False):
        return _get_frozen_data_dir()
    return _get_base_dir() / "data"


def _get_resources_dir() -> Path:
    if getattr(sys, "frozen", False):
        return _get_base_dir() / "models"
    return _get_install_dir() / "resources"


def _env_path(name: str) -> Path | None:
    """Read an absolute-path override from the environment, if set."""
    raw = os.environ.get(name, "").strip()
    return Path(raw).expanduser() if raw else None


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

    def model_post_init(self, __context: object) -> None:
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

    def set_enabled(self, module_ids: Iterable[str]) -> None:
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

    model_mode: str = "equilibrado"
    default_llm_model: str = DEFAULT_LLM_MODEL
    llm_model: str = DEFAULT_LLM_MODEL
    fast_llm_model: str = "gemma3-4b-q4km"
    quality_llm_model: str = "qwen3-14b-q4km"
    reasoning_llm_model: str = "deepseek-r1-distill-qwen-7b-q4km"
    vision_llm_model: str = "qwen2.5-vl-7b-q4km"
    embedding_model: str = "qwen3-embedding-0.6b"
    whisper_model: str = "small"
    num_ctx: int = 16384
    num_predict: int = 8192
    n_gpu_layers: int = -1
    n_batch: int = 1024
    n_threads: int = 0
    use_mmap: bool = True
    use_mlock: bool = True
    offload_kqv: bool = True
    flash_attn: bool = True
    auto_configured: bool = False
    model_client_choice: bool = False
    warm_up_on_load: bool = True

    def to_storage(self) -> dict[str, object]:
        return {
            "llm_model": self.llm_model,
            "model_client_choice": self.model_client_choice,
        }

    def apply_storage(self, data: Mapping[str, object], *, preserve_explicit: bool = True) -> None:
        explicit = self.model_fields_set if preserve_explicit else set()
        if "llm_model" not in explicit or not preserve_explicit:
            value = data.get("llm_model")
            if isinstance(value, str) and value:
                self.llm_model = value
        if "model_client_choice" not in explicit or not preserve_explicit:
            value = data.get("model_client_choice")
            if isinstance(value, bool):
                self.model_client_choice = value


class ResponseStyleSettings(BaseSettings):
    """Response tone and sampling settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_RESPONSE_")

    mode: Literal["natural", "tecnico", "relatorio"] = "natural"
    detail_level: Literal["conciso", "equilibrado", "detalhado"] = "detalhado"
    temperature: float = 0.45
    top_p: float = 0.9
    short_answer_max_chars: int = 320
    max_simple_sentences: int = 5

    def prompt_context(self) -> str:
        lines = [
            "## Estilo de Conversa",
            "- Fale com autoridade serena, clareza e dominio do assunto.",
            "- Comece pela resposta ou conclusao principal; depois desenvolva a explicacao.",
            "- Ajuste a profundidade ao assunto, nao apenas ao tamanho da pergunta.",
            "- Perguntas factuais muito simples podem ser breves, mas nunca vagas ou incompletas.",
            "- Em assuntos substanciais, explique o que e, por que importa e como aplicar.",
            "- Inclua exemplos concretos, comparacoes ou cenarios praticos quando agregarem valor.",
            "- Em orientacoes, apresente passos acionaveis e uma recomendacao final quando couber.",
            "- Aponte premissas, riscos, limites e incertezas relevantes sem inventar seguranca.",
            "- Para relatorios, analises e documentos, use secoes, tabelas e conclusoes praticas.",
            "- Use listas e titulos somente quando melhorarem a leitura.",
            "- Evite soar como manual, contrato ou texto engessado.",
            "- Evite respostas infladas, repetitivas ou cheias de frases genericas.",
            "- Nao comece toda resposta com confirmacoes genericas.",
            "- Use o historico recente para manter continuidade de conversa.",
        ]
        if self.detail_level == "conciso":
            lines.extend(
                [
                    "- Nivel de detalhe: conciso.",
                    "- Entregue primeiro o essencial e omita aprofundamentos opcionais.",
                ]
            )
        elif self.detail_level == "equilibrado":
            lines.extend(
                [
                    "- Nivel de detalhe: equilibrado.",
                    "- Cubra contexto, exemplo e acao pratica sem explorar ramificacoes secundarias.",
                ]
            )
        else:
            lines.extend(
                [
                    "- Nivel de detalhe: detalhado.",
                    "- Desenvolva os pontos importantes com contexto, exemplos e implicacoes praticas.",
                    "- Antecipe duvidas previsiveis e inclua detalhes que ajudem o usuario a decidir ou agir.",
                ]
            )
        if self.mode == "tecnico":
            lines.extend(
                [
                    "- Modo atual: tecnico.",
                    "- Priorize precisao, fundamentos, criterios, riscos e formas de verificacao.",
                    "- Mostre exemplos tecnicos ou operacionais suficientes para tornar a resposta aplicavel.",
                ]
            )
        elif self.mode == "relatorio":
            lines.extend(
                [
                    "- Modo atual: relatorio.",
                    "- Abra com um resumo executivo e desenvolva evidencias, comparativos e indicadores.",
                    "- Termine com conclusoes, prioridades e proximas acoes.",
                ]
            )
        else:
            lines.extend(
                [
                    "- Modo atual: natural.",
                    "- Priorize respostas humanas, completas e proporcionais a complexidade real do tema.",
                    "- Uma pergunta curta pode exigir uma resposta detalhada; nao a trate automaticamente como rasa.",
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


class DecisionLayerSettings(BaseSettings):
    """Local decision-model layer (Jev-style System One contracts).

    Disabled by default so existing behavior is preserved until the layer is
    explicitly turned on. Env vars use the ``CELSIUS_DECISION_`` prefix (the
    ``CELSIUS_DECISION__*`` nested form works too, e.g. in ``.env``).

    Safety posture enforced by this layer:

    * ``decisions.HealthCheck`` / ``DecisionClient.health()`` verify the local
      ``kev.serve`` is reachable; when it is not, every call degrades to a
      recorded fallback and Celsius keeps working unchanged.
    * The tool guard can only *add* confirmations. The deterministic policy in
      ``core.tool_policy`` owns the mandatory confirmations; the probabilistic
      model only ever suggests more.
    * The RAG gate scores chunks but never prunes unless explicitly enabled and
      calibrated, so no relevant passage is ever dropped by default.
    """

    model_config = SettingsConfigDict(env_prefix="CELSIUS_DECISION_")

    enabled: bool = False
    provider: Literal["off", "local"] = "local"
    base_url: str = "http://127.0.0.1:8009"
    model: str = "kev-latest"
    auto_start: bool = True
    timeout_ms: int = 4000
    guard_risk_threshold: float = 0.70
    guard_uncertainty_band: float = 0.15
    rag_relevance_threshold: float = 0.60
    rag_max_gated_chunks: int = 5
    # Auto model routing: when enabled, JEV chooses which downloaded LLM answers
    # each task (unless the client pinned a specific model in the UI).
    model_routing: bool = True
    # Record every gate/route outcome to a JSONL file so the user can measure
    # false-approval and pruning rates while calibrating (DECISION_LAYER §9).
    record_outcomes: bool = True
    # Health probing: seconds between two /v1/models probes used by the UI
    # status indicator (0 disables caching, i.e. probe on every call).
    health_cache_seconds: float = 15.0
    # Minimum separation (normalized score) between the best and the runner-up
    # model for the router to commit to a switch. A tie keeps the current model.
    model_route_min_margin: float = 0.15
    # Minimum confidence (0..1) required to commit to an automatic model swap.
    # Below this the current model is kept and the reason is logged.
    model_route_min_confidence: float = 0.35
    # RAG gate safety: while calibrating, chunks are only scored and recorded,
    # never removed. Pruning additionally requires ``rag_prune_enabled`` and at
    # least ``rag_min_samples`` labeled examples in the outcomes log.
    rag_calibration_mode: bool = True
    rag_prune_enabled: bool = False
    rag_min_samples: int = 30
    # Only prune a chunk when its score is clearly below the threshold.
    rag_prune_margin: float = 0.15

    def normalized_endpoint(self) -> str:
        return self.base_url.rstrip("/")


class AgentModeSettings(BaseSettings):
    """Selectable agentic modes (see ``core.agent_modes``).

    ``enabled`` keeps the whole feature optional: with it off the Celsius
    behaves exactly as the traditional single-mode chat.
    """

    model_config = SettingsConfigDict(env_prefix="CELSIUS_AGENT_")

    enabled: bool = True
    default_mode: str = "assistente"
    # Per-mode hard limits. A task may never exceed these, whatever the mode
    # declares, so a bad plan cannot loop forever. ``max_iterations`` is budgeted
    # apart from ``max_steps`` because a model turn and a tool call are different
    # resources; a document batch spends most of its turns writing prose.
    max_steps: int = 24
    max_iterations: int = 200
    max_seconds: int = 900
    max_attempts: int = 2
    max_plan_items: int = 6

    # ── Tool retrieval for a chat turn (see ``ai.tool_retrieval``) ──
    # The lexical keyword map in ``ai.react`` stays in place as one signal;
    # these knobs add the semantic ranking on top of it, so a request the
    # model understood correctly no longer reaches it with the required tool
    # hidden. Turning this off restores the previous lexical-only behaviour.
    tool_retrieval_enabled: bool = True
    #: How many tools the semantic ranker may contribute per turn.
    tool_retrieval_top_k: int = 6
    #: Minimum cosine similarity for a tool to be retrieved semantically.
    tool_retrieval_min_score: float = 0.38
    #: Minimum similarity to read the message as operational at all. Below
    #: this a general-knowledge question keeps receiving zero tools.
    operational_intent_min_score: float = 0.55

    # ── Automatic mode routing (see ``core.agent_modes.resolve_mode``) ──
    # An explicit "modo X" always wins and is unaffected by these knobs.
    auto_route_enabled: bool = True
    #: Minimum similarity for the automatic router to leave the current mode
    #: alone. Set high to keep mode switching deliberately manual.
    auto_route_min_score: float = 0.5

    # ── ReAct loop budget (see ``ai.loop_budget``) ──
    #: Safety ceiling applied to *every* turn, whatever a mode declares. This is
    #: the only number here that exists to stop a runaway, so it is the only one
    #: that must never be lowered by a class or a mode.
    loop_hard_cap: int = 200
    #: Tiers for a chat turn, chosen by request complexity. The previous code
    #: spent 5 iterations on every request including a greeting, which was not a
    #: safety limit but a leftover, and it truncated real multi-step work.
    loop_budget_conversa: int = 6
    loop_budget_ferramenta_simples: int = 14
    loop_budget_multi_step: int = 28
    #: Fallback for a task session whose mode declares nothing.
    loop_budget_task: int = 60
    #: Consecutive equivalent tool calls before the loop is broken for the
    #: model. 2 means: first repeat warns, second repeat stops.
    loop_repeat_threshold: int = 3

    # ── Model generation parameters (see ``ai.react``) ──
    #: Presence penalty for task turns. Lower values reduce unwanted repetition
    #: in structured outputs (tables, tool calls, reports).
    task_presence_penalty: float = 0.0
    #: Frequency penalty for task turns. Lower values allow legitimate token reuse.
    task_frequency_penalty: float = 0.1
    #: Max tokens for a task turn response. Increased from 1536 to allow longer
    #: multi-step executions without truncation.
    task_max_tokens: int = 3072
    #: Presence penalty for chat turns (non-task).
    chat_presence_penalty: float = 0.1
    #: Frequency penalty for chat turns (non-task).
    chat_frequency_penalty: float = 0.2
    #: Max tokens for a chat turn response.
    chat_max_tokens: int = 1536

    # ── Conditional reflection (see ``ai.reflection``) ──
    #: Enable the post-answer reflection step.
    reflection_enabled: bool = True
    #: Maximum reflection iterations per turn (prevents infinite reflection loop).
    reflection_max_turns: int = 1


class MemorySettings(BaseSettings):
    """Memory-related settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_MEMORY_")

    max_history_session: int = 16
    memory_threshold: float = 0.15
    top_memories: int = 10
    inject_all_memories_limit: int = 15
    auto_extract_facts: bool = True
    extraction_max_facts: int = 5
    extraction_recent_messages: int = 10


class FileSettings(BaseSettings):
    """File processing settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_FILE_")

    max_file_size_mb: int = 50
    max_pdf_size_mb: int = 300
    large_pdf_page_limit: int = 80
    doc_text_limit: int = 12000
    doc_extensions: tuple[str, ...] = (
        ".pdf",
        ".docx",
        ".odt",
        ".ods",
        ".odp",
        ".txt",
        ".md",
        ".py",
        ".json",
        ".csv",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".log",
    )
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
    sandbox_backend: Literal["local", "docker", "auto"] = "auto"
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

    def to_storage(self) -> dict[str, str | bool | list[str]]:
        data: dict[str, str | bool | list[str]] = {}
        for field in SECURITY_FIELDS:
            value = getattr(self, field)
            data[field] = list(value) if isinstance(value, (tuple, list)) else value
        return data

    def apply_storage(self, data: dict, *, preserve_explicit: bool = True) -> None:
        explicit_fields = self.model_fields_set if preserve_explicit else set()
        for field in SECURITY_FIELDS:
            if preserve_explicit and field in explicit_fields:
                continue
            if field not in data:
                continue
            value = data[field]
            if field == "allowed_file_roots":
                value = value if isinstance(value, (tuple, list)) else (value,)
                value = tuple(str(item) for item in value if str(item).strip())
            setattr(self, field, value)


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
    profile: str = "natural_male_br"
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
    host: str = "0.0.0.0"  # nosec B104 - used only with explicit LAN opt-in and HTTPS
    port: int = 8787
    pairing_token: str = ""
    pairing_token_issued_at: str = ""
    token_rotation_days: int = 30
    session_ttl_seconds: int = 12 * 60 * 60
    pairing_ttl_seconds: int = 120
    max_browser_sessions: int = 32
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


class NotificationSettings(BaseSettings):
    """External notification channel settings."""

    model_config = SettingsConfigDict(env_prefix="CELSIUS_NOTIFICATIONS_")

    enabled: bool = False
    external_services_allowed: bool = False
    require_confirmation: bool = True
    default_channel: Literal["whatsapp", "email", "sms"] = "whatsapp"
    whatsapp_provider: str = "meta_cloud_api"
    whatsapp_phone_number_id: str = ""
    whatsapp_token_env_var: str = "CELSIUS_WHATSAPP_TOKEN"
    email_provider: str = ""
    email_from: str = ""
    sms_provider: str = ""
    sms_sender_id: str = ""

    def to_storage(self) -> dict[str, str | bool]:
        return {field: getattr(self, field) for field in NOTIFICATION_FIELDS}

    def apply_storage(self, data: dict, *, preserve_explicit: bool = True) -> None:
        explicit_fields = self.model_fields_set if preserve_explicit else set()
        for field in NOTIFICATION_FIELDS:
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


class WebSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CELSIUS_WEB_")

    host: str = "127.0.0.1"
    port: int = Field(default=8790, ge=1, le=65535)


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_prefix="CELSIUS_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    base_dir: Path = Field(default_factory=_get_base_dir)
    data_dir: Path = Field(default_factory=lambda: _get_default_data_dir())
    resources_dir: Path = Field(default_factory=_get_resources_dir)
    logs_dir: Path = Field(default_factory=lambda: _get_base_dir() / "logs")

    assistant: AssistantSettings = Field(default_factory=AssistantSettings)
    customer: CustomerSettings = Field(default_factory=CustomerSettings)
    modules: CompanyModulesSettings = Field(default_factory=CompanyModulesSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)
    response: ResponseStyleSettings = Field(default_factory=ResponseStyleSettings)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    decision: DecisionLayerSettings = Field(default_factory=DecisionLayerSettings)
    agent: AgentModeSettings = Field(default_factory=AgentModeSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    file: FileSettings = Field(default_factory=FileSettings)
    inventory: InventorySettings = Field(default_factory=InventorySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    ui: UiSettings = Field(default_factory=UiSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    mobile: MobileAccessSettings = Field(default_factory=MobileAccessSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    web: WebSettings = Field(default_factory=WebSettings)

    memorias_file: Path = Field(default_factory=lambda: _get_base_dir() / "memorias.json")
    chats_file: Path = Field(default_factory=lambda: _get_base_dir() / "chats.json")
    inventory_file: Path = Field(default_factory=lambda: _get_base_dir() / "inventory.json")
    audio_temp_file: Path = Field(default_factory=lambda: _get_base_dir() / "temp_kfu_voice.mp3")
    audio_mic_file: Path = Field(default_factory=lambda: _get_base_dir() / "temp_audio.wav")

    def model_post_init(self, __context: object) -> None:
        pass

    def initialize(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.resources_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._load_customer_profile()
        self._load_local_preferences()
        self._sync_legacy_owner_name()

    @property
    def _relocation_target(self) -> Path | None:
        """Path an env override may relocate persistent files to.

        An explicitly supplied ``data_dir`` always wins, so callers that point
        the settings at a scratch directory (tests, portable installs) keep full
        control over where their files live.
        """
        if self.data_dir != _get_default_data_dir():
            return None
        return self.data_dir

    def _relocated(self, env_name: str) -> Path | None:
        if self._relocation_target is None:
            return None
        return _env_path(env_name)

    @property
    def customer_profile_file(self) -> Path:
        """Persistent customer profile.

        ``CELSIUS_CUSTOMER_PROFILE_FILE`` relocates it unless ``data_dir`` was
        passed explicitly.
        """
        relocated = self._relocated("CELSIUS_CUSTOMER_PROFILE_FILE")
        return relocated or (self.data_dir / "customer_profile.json")

    @property
    def local_preferences_file(self) -> Path:
        """Persistent local preferences (``celsius_settings.json``).

        ``CELSIUS_PREFERENCES_FILE`` relocates the file unless ``data_dir`` was
        passed explicitly. This keeps test runs and portable/secondary
        installations from reading or writing the main installation's config.
        """
        relocated = self._relocated("CELSIUS_PREFERENCES_FILE")
        return relocated or (self.data_dir / "celsius_settings.json")

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
        if isinstance(data.get("notifications"), dict):
            self.notifications.apply_storage(data["notifications"], preserve_explicit=True)
        if isinstance(data.get("security"), dict):
            self.security.apply_storage(data["security"], preserve_explicit=True)
        if isinstance(data.get("model"), dict):
            self.model.apply_storage(data["model"], preserve_explicit=True)

    def _sync_legacy_owner_name(self) -> None:
        if self.assistant.owner_name and not self.customer.user_name:
            self.customer.user_name = self.assistant.owner_name
        elif self.customer.user_name and not self.assistant.owner_name:
            self.assistant.owner_name = self.customer.user_name

    def save_customer_profile(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.assistant.owner_name = self.customer.user_name
        path = self.customer_profile_file
        atomic_write_json(path, self.customer.to_storage())
        restrict_private_file(path)
        self.save_local_preferences()
        return path

    def save_local_preferences(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.assistant.owner_name = self.customer.user_name
        path = self.local_preferences_file
        atomic_write_json(
            path,
            {
                "customer": self.customer.to_storage(),
                "modules": self.modules.to_storage(),
                "response": self.response.to_storage(),
                "voice": self.voice.to_storage(),
                "mobile": self.mobile.to_storage(),
                "notifications": self.notifications.to_storage(),
                "security": self.security.to_storage(),
                "model": self.model.to_storage(),
            },
        )
        restrict_private_file(path)
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
    def quality_llm_model(self) -> str:
        return self.model.quality_llm_model

    @property
    def reasoning_llm_model(self) -> str:
        return self.model.reasoning_llm_model

    @property
    def vision_llm_model(self) -> str:
        return self.model.vision_llm_model

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

    @property
    def bundled_resources_dir(self) -> Path:
        return _get_bundle_dir() / "resources"

    def get_asset_path(self, relative_path: str | Path) -> Path:
        return _get_bundle_dir() / Path(relative_path)

    def _resolve_model_resource(self, filename: str) -> Path:
        writable_path = self.resources_dir / filename
        if writable_path.exists():
            return writable_path
        bundled_path = self.bundled_resources_dir / filename
        return bundled_path if bundled_path.exists() else writable_path

    def get_model_path(self, model_id: str | None = None) -> Path:
        model_id = model_id or self.model.llm_model
        from core.config import discover_installed_models, get_model_by_id

        model = get_model_by_id(model_id)
        if model:
            return self._resolve_model_resource(model.filename)
        search_dirs = [self.resources_dir]
        if self.bundled_resources_dir.is_dir():
            search_dirs.append(self.bundled_resources_dir)
        for candidate in discover_installed_models(*search_dirs):
            if candidate.id == model_id:
                return self._resolve_model_resource(candidate.filename)
        return self._resolve_model_resource("model.gguf")

    def get_mmproj_path(self, model_id: str | None = None) -> Path | None:
        model_id = model_id or self.model.llm_model
        from core.config import get_model_by_id

        model = get_model_by_id(model_id)
        if model and model.has_mmproj:
            path = self._resolve_model_resource(model.mmproj_file)
            return path if path.exists() else None
        return None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        env_file = None
        if not getattr(sys, "frozen", False):
            candidate = _get_install_dir() / ".env"
            env_file = candidate if candidate.is_file() else None
        _settings = Settings(_env_file=env_file)
        _settings.initialize()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None


def get_feature_flags() -> FeatureFlags:
    return get_settings().features
