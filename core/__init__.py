"""Core module — lazy imports to avoid circular dependencies."""

# Backwards compatibility — these re-export the original config values
from core.config import (
    ARQUIVO_AUDIO_TEMP,
    ARQUIVO_MEMORIAS,
    DIRETORIO_BASE,
    GGUF_MODELS,
    LIMITE_TEXTO_DOCUMENTO,
    MAX_HISTORICO_SESSION,
    MODELO_LLM,
    NUM_CTX,
    NUM_PREDICT,
    THRESHOLD_MEMORIA,
    TOP_MEMORIAS,
    GGUFModel,
    get_model_by_id,
)
from core.container import get_container, reset_container
from core.logging_config import get_logger, setup_logging
from core.settings import (
    FeatureFlags,
    FileSettings,
    InventorySettings,
    MemorySettings,
    ModelSettings,
    RagSettings,
    SecuritySettings,
    Settings,
    TelemetrySettings,
    UiSettings,
    get_settings,
    reset_settings,
)
