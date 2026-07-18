import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
    id: str
    name: str


@dataclass
class Settings:
    base_dir: Path = field(default_factory=lambda: _get_base_dir())
    memorias_file: Path = field(init=False)
    chats_file: Path = field(init=False)
    audio_temp_file: Path = field(init=False)
    audio_mic_file: Path = field(init=False)

    default_llm_model: str = "gemma3:12b"
    llm_model: str = "gemma3:12b"
    embedding_model: str = "all-MiniLM-L6-v2"
    whisper_model: str = "base"

    available_models: list[ModelConfig] = field(default_factory=lambda: [
        ModelConfig("gemma3:12b", "Gemma 3 12B"),
        ModelConfig("phi3.5:latest", "Phi 3.5 (Rapido)"),
        ModelConfig("qwen2.5-coder:14b", "Qwen 2.5 Coder 14B (Codigo)"),
        ModelConfig("llama3.2:1b", "Llama 3.2 1B (Leve)"),
        ModelConfig("gemma3:1b", "Gemma 3 1B (Leve)"),
        ModelConfig("qwen2.5vl:7b", "Qwen 2.5 VL 7B (Visao)"),
        ModelConfig("qwen3-coder:30b", "Qwen 3 Coder 30B (Codigo)"),
    ])

    doc_text_limit: int = 12000
    num_ctx: int = 8192
    num_predict: int = 2500
    max_history_session: int = 16
    memory_threshold: float = 0.30
    top_memories: int = 4

    doc_extensions: tuple[str, ...] = (".pdf", ".docx", ".odt", ".ods", ".odp")
    image_extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
    audio_extensions: tuple[str, ...] = (".mp3", ".wav", ".ogg", ".m4a", ".flac")

    def __post_init__(self):
        self.memorias_file = self.base_dir / "memorias.json"
        self.chats_file = self.base_dir / "chats.json"
        self.audio_temp_file = self.base_dir / "temp_kfu_voice.mp3"
        self.audio_mic_file = self.base_dir / "temp_audio.wav"

    @property
    def all_extensions(self) -> tuple[str, ...]:
        return self.doc_extensions + self.image_extensions + self.audio_extensions

    @property
    def file_filter(self) -> str:
        return " ".join(f"*{e}" for e in self.all_extensions)

    def set_llm_model(self, model_id: str) -> None:
        self.llm_model = model_id


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


settings = Settings()


def get_settings() -> Settings:
    return settings


# Backwards compatibility
DIRETORIO_BASE = settings.base_dir
ARQUIVO_MEMORIAS = settings.memorias_file
ARQUIVO_CHATS = settings.chats_file
ARQUIVO_AUDIO_TEMP = settings.audio_temp_file
ARQUIVO_AUDIO_MIC = settings.audio_mic_file
MODELO_LLM_PADRAO = settings.default_llm_model
MODELO_LLM = settings.llm_model
MODELO_EMBEDDING = settings.embedding_model
MODELO_WHISPER = settings.whisper_model
MODELOS_DISPONIVEIS = [(m.id, m.name) for m in settings.available_models]
LIMITE_TEXTO_DOCUMENTO = settings.doc_text_limit
NUM_CTX = settings.num_ctx
NUM_PREDICT = settings.num_predict
MAX_HISTORICO_SESSION = settings.max_history_session
THRESHOLD_MEMORIA = settings.memory_threshold
TOP_MEMORIAS = settings.top_memories
EXTENSOES_DOCUMENTO = list(settings.doc_extensions)
EXTENSOES_IMAGEM = list(settings.image_extensions)
EXTENSOES_AUDIO = list(settings.audio_extensions)
TODAS_EXTENSOES = list(settings.all_extensions)
FILTRO_ARQUIVOS = settings.file_filter
