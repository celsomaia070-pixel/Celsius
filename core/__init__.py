from core.commands import executar_comando, pesquisar_web
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
    Settings,
    get_model_by_id,
    get_settings,
)
from core.llama_cpp import (
    get_llama,
    get_llama_client_config,
    start_llama_server,
    stop_llama_server,
    switch_llama_model,
)
from core.logging_config import get_logger, setup_logging
from core.memory import (
    MemoryService,
    buscar_memorias,
    carregar_memorias,
    get_memory_service,
    salvar_memorias,
)
