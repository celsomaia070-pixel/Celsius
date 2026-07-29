"""Tests for core.settings (pydantic-settings configuration)."""

from pathlib import Path
from unittest.mock import patch

from core.settings import (
    AssistantSettings,
    CompanyModulesSettings,
    CustomerSettings,
    Environment,
    FeatureFlags,
    FileSettings,
    InventorySettings,
    LogLevel,
    MemorySettings,
    MobileAccessSettings,
    ModelSettings,
    RagSettings,
    ResponseStyleSettings,
    SecuritySettings,
    Settings,
    TelemetrySettings,
    UiSettings,
    VoiceSettings,
    _get_base_dir,
    get_feature_flags,
    get_settings,
    reset_settings,
)


class TestGetBaseDir:
    def test_not_frozen(self, monkeypatch):
        monkeypatch.delattr("sys.frozen", raising=False)
        result = _get_base_dir()
        assert result.is_dir()

    def test_frozen(self, monkeypatch):
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setattr("sys.executable", "/fake/app/main.exe", raising=False)
        result = _get_base_dir()
        assert result == Path("/fake/app")


class TestModelSettingsDefaults:
    def test_default_llm_model(self):
        s = ModelSettings()
        assert s.default_llm_model == "qwen2.5-vl-7b-q4km"

    def test_llm_model(self):
        s = ModelSettings()
        assert s.llm_model == "qwen2.5-vl-7b-q4km"

    def test_fast_llm_model(self):
        s = ModelSettings()
        assert s.fast_llm_model == "llama3.2-3b-q5km"

    def test_embedding_model(self):
        s = ModelSettings()
        assert s.embedding_model == "paraphrase-multilingual-MiniLM-L12-v2"

    def test_whisper_model(self):
        s = ModelSettings()
        assert s.whisper_model == "small"

    def test_num_ctx(self):
        s = ModelSettings()
        assert s.num_ctx == 16384

    def test_num_predict(self):
        s = ModelSettings()
        assert s.num_predict == 2500

    def test_n_gpu_layers(self):
        s = ModelSettings()
        assert s.n_gpu_layers == -1

    def test_n_batch(self):
        s = ModelSettings()
        assert s.n_batch == 1024

    def test_booleans(self):
        s = ModelSettings()
        assert s.use_mmap is True
        assert s.use_mlock is True
        assert s.offload_kqv is True
        assert s.flash_attn is True


class TestResponseStyleSettingsDefaults:
    def test_defaults_are_natural(self):
        s = ResponseStyleSettings()
        assert s.mode == "natural"
        assert s.temperature == 0.45
        assert s.top_p == 0.9

    def test_prompt_context_encourages_natural_answers(self):
        context = ResponseStyleSettings().prompt_context()
        assert "Estilo de Conversa" in context
        assert "perguntas simples" in context
        assert "Modo atual: natural" in context


class TestAssistantSettingsDefaults:
    def test_identity_defaults(self):
        s = AssistantSettings()
        assert s.name == "Celsius"
        assert s.owner_name == ""
        assert s.profile == "Agente Multimodal Local de IA"

    def test_identity_is_fixed(self, monkeypatch):
        monkeypatch.setenv("CELSIUS_ASSISTANT_NAME", "EmpresaBot")
        monkeypatch.setenv("CELSIUS_ASSISTANT_PROFILE", "Outro perfil")
        s = AssistantSettings()
        assert s.name == "Celsius"
        assert s.profile == "Agente Multimodal Local de IA"


class TestCustomerSettingsDefaults:
    def test_defaults(self):
        s = CustomerSettings()
        assert s.user_name == ""
        assert s.company_name == ""
        assert s.company_description == ""
        assert s.main_needs == ""
        assert s.preferred_tone == "profissional e direto"
        assert s.timezone == "America/Sao_Paulo"
        assert s.local_offline_required is True
        assert s.is_configured() is False

    def test_prompt_context_when_configured(self):
        s = CustomerSettings(
            user_name="Celso",
            company_name="Celsius Sistemas",
            company_sector="Gestao empresarial",
            user_role="Proprietario",
            business_context="Controla estoque, fornecedores e financeiro.",
        )

        context = s.prompt_context()

        assert "Perfil do Cliente/Empresa" in context
        assert "Usuario principal: Celso" in context
        assert "Empresa: Celsius Sistemas" in context
        assert "Controla estoque" in context
        assert "nao limite o escopo do Celsius ao setor cadastrado" in context
        assert "assuntos gerais" in context

    def test_prompt_context_does_not_restrict_general_topics(self):
        s = CustomerSettings(
            company_name="Maia Servicos Automotivos",
            company_sector="Oficina mecanica",
            main_needs="Gerenciar estoque e fornecedores.",
        )

        context = s.prompt_context()

        assert "Oficina mecanica" in context
        assert "Nao trate o setor da empresa como regra fixa" in context
        assert "redacao" in context


class TestCompanyModulesSettingsDefaults:
    def test_mandatory_modules_stay_enabled(self):
        from core.modules import MODULE_CHAT, MODULE_SETTINGS

        s = CompanyModulesSettings(enabled=[])

        assert MODULE_CHAT in s.enabled
        assert MODULE_SETTINGS in s.enabled

    def test_set_enabled_ignores_unknown_modules(self):
        from core.modules import MODULE_CHAT, MODULE_SETTINGS, MODULE_SUPPLIERS

        s = CompanyModulesSettings()
        s.set_enabled(["unknown", MODULE_SUPPLIERS])

        assert "unknown" not in s.enabled
        assert MODULE_SUPPLIERS in s.enabled
        assert MODULE_CHAT in s.enabled
        assert MODULE_SETTINGS in s.enabled


class TestFeatureFlagsDefaults:
    def test_all_true_by_default(self):
        flags = FeatureFlags()
        assert flags.conversations is True
        assert flags.inventory is True
        assert flags.rag is True
        assert flags.memory is True
        assert flags.web_search is True
        assert flags.web_browser is True
        assert flags.code_execution is True
        assert flags.voice_input is True
        assert flags.voice_output is True
        assert flags.image_analysis is True
        assert flags.document_processing is True
        assert flags.report_generation is True
        assert flags.multi_agent is True
        assert flags.model_router is True


class TestRagSettingsDefaults:
    def test_chunk_size(self):
        s = RagSettings()
        assert s.chunk_size == 600

    def test_chunk_overlap(self):
        s = RagSettings()
        assert s.chunk_overlap == 80

    def test_top_k(self):
        s = RagSettings()
        assert s.top_k == 5

    def test_final_top_k(self):
        s = RagSettings()
        assert s.final_top_k == 3

    def test_distance_threshold(self):
        s = RagSettings()
        assert s.distance_threshold == 1.5

    def test_hybrid_search_enabled(self):
        s = RagSettings()
        assert s.enable_hybrid_search is True

    def test_bm25_weight(self):
        s = RagSettings()
        assert s.bm25_weight == 0.3

    def test_dense_weight(self):
        s = RagSettings()
        assert s.dense_weight == 0.7

    def test_reranking_enabled(self):
        s = RagSettings()
        assert s.enable_reranking is True

    def test_reranker_model(self):
        s = RagSettings()
        assert "ms-marco" in s.reranker_model

    def test_rerank_top_k(self):
        s = RagSettings()
        assert s.rerank_top_k == 10


class TestSecuritySettingsDefaults:
    def test_sandbox_enabled(self):
        s = SecuritySettings()
        assert s.sandbox_enabled is True

    def test_sandbox_limits(self):
        s = SecuritySettings()
        assert s.sandbox_max_memory_mb == 256
        assert s.sandbox_max_cpu_seconds == 30

    def test_allowed_imports(self):
        s = SecuritySettings()
        assert "math" in s.sandbox_allowed_imports
        assert "json" in s.sandbox_allowed_imports
        assert "re" in s.sandbox_allowed_imports

    def test_blocked_imports(self):
        s = SecuritySettings()
        assert "os" in s.sandbox_blocked_imports
        assert "subprocess" in s.sandbox_blocked_imports
        assert "sys" in s.sandbox_blocked_imports
        assert "ctypes" in s.sandbox_blocked_imports

    def test_path_traversal_protection(self):
        s = SecuritySettings()
        assert s.path_traversal_protection is True


class TestMemorySettingsDefaults:
    def test_max_history_session(self):
        s = MemorySettings()
        assert s.max_history_session == 16

    def test_memory_threshold(self):
        s = MemorySettings()
        assert s.memory_threshold == 0.15

    def test_top_memories(self):
        s = MemorySettings()
        assert s.top_memories == 10


class TestFileSettingsDefaults:
    def test_max_file_size_mb(self):
        s = FileSettings()
        assert s.max_file_size_mb == 50

    def test_large_pdf_defaults(self):
        s = FileSettings()
        assert s.max_pdf_size_mb == 300
        assert s.large_pdf_page_limit == 80

    def test_doc_text_limit(self):
        s = FileSettings()
        assert s.doc_text_limit == 12000

    def test_doc_extensions(self):
        s = FileSettings()
        assert ".pdf" in s.doc_extensions
        assert ".docx" in s.doc_extensions

    def test_image_extensions(self):
        s = FileSettings()
        assert ".png" in s.image_extensions
        assert ".jpg" in s.image_extensions

    def test_audio_extensions(self):
        s = FileSettings()
        assert ".mp3" in s.audio_extensions
        assert ".wav" in s.audio_extensions
        assert ".webm" in s.audio_extensions


class TestInventorySettingsDefaults:
    def test_enabled(self):
        s = InventorySettings()
        assert s.enabled is True

    def test_data_file(self):
        s = InventorySettings()
        assert s.data_file == "inventory.json"

    def test_kanban_columns(self):
        s = InventorySettings()
        assert "estoque" in s.kanban_columns
        assert "em_falta" in s.kanban_columns

    def test_default_stocks(self):
        s = InventorySettings()
        assert s.default_min_stock == 5
        assert s.default_max_stock == 100


class TestTelemetrySettingsDefaults:
    def test_enabled(self):
        s = TelemetrySettings()
        assert s.enabled is False

    def test_otlp_endpoint(self):
        s = TelemetrySettings()
        assert "localhost" in s.otlp_endpoint

    def test_service_name(self):
        s = TelemetrySettings()
        assert s.service_name == "celsius"

    def test_sample_rate(self):
        s = TelemetrySettings()
        assert s.sample_rate == 1.0

    def test_log_level(self):
        s = TelemetrySettings()
        assert s.log_level == LogLevel.INFO

    def test_metrics_enabled(self):
        s = TelemetrySettings()
        assert s.metrics_enabled is True
        assert s.metrics_port == 9090

    def test_init_telemetry_disabled_uses_noop(self):
        import core.telemetry as telemetry

        telemetry.shutdown_telemetry()
        tracer, meter = telemetry.init_telemetry(enabled=False)

        assert type(tracer).__name__ == "_NoOpTracer"
        assert type(meter).__name__ == "_NoOpMeter"


class TestUiSettingsDefaults:
    def test_theme(self):
        s = UiSettings()
        assert s.theme == "light"

    def test_language(self):
        s = UiSettings()
        assert s.language == "pt-BR"

    def test_font_size(self):
        s = UiSettings()
        assert s.font_size == 10

    def test_show_sidebar(self):
        s = UiSettings()
        assert s.show_sidebar is True

    def test_jarvis_defaults(self):
        s = UiSettings()
        assert s.jarvis_enabled is True
        assert s.jarvis_particle_count == 800
        assert s.jarvis_fps == 60


class TestVoiceSettingsDefaults:
    def test_voice_defaults(self):
        s = VoiceSettings()
        assert s.enabled is True
        assert s.provider == "edge-tts"
        assert s.voice == "pt-BR-AntonioNeural"
        assert s.rate == "+5%"
        assert s.pitch == "-2Hz"
        assert s.volume == "+0%"


class TestMobileAccessSettingsDefaults:
    def test_mobile_access_is_disabled_by_default(self):
        s = MobileAccessSettings()

        assert s.enabled is False
        assert s.port == 8787
        assert s.allow_lan is False
        assert s.voice_commands_enabled is True
        assert s.use_https is True


class TestEnums:
    def test_log_level_values(self):
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.CRITICAL == "CRITICAL"

    def test_environment_values(self):
        assert Environment.DEVELOPMENT == "development"
        assert Environment.STAGING == "staging"
        assert Environment.PRODUCTION == "production"
        assert Environment.TEST == "test"


class TestSettingsMain:
    def test_environment_default(self):
        s = Settings()
        assert s.environment == Environment.DEVELOPMENT

    def test_nested_model_settings(self):
        s = Settings()
        assert isinstance(s.model, ModelSettings)
        assert s.model.llm_model == "qwen2.5-vl-7b-q4km"

    def test_nested_customer_settings(self):
        s = Settings()
        assert isinstance(s.customer, CustomerSettings)

    def test_nested_response_and_voice_settings(self):
        s = Settings()
        assert isinstance(s.response, ResponseStyleSettings)
        assert isinstance(s.voice, VoiceSettings)
        assert isinstance(s.mobile, MobileAccessSettings)

    def test_nested_rag_settings(self):
        s = Settings()
        assert isinstance(s.rag, RagSettings)
        assert s.rag.chunk_size == 600

    def test_nested_feature_flags(self):
        s = Settings()
        assert isinstance(s.features, FeatureFlags)
        assert s.features.rag is True

    def test_memorias_file(self):
        s = Settings()
        assert s.memorias_file.name == "memorias.json"
        assert isinstance(s.memorias_file, Path)

    def test_chats_file(self):
        s = Settings()
        assert s.chats_file.name == "chats.json"

    def test_inventory_file(self):
        s = Settings()
        assert s.inventory_file.name == "inventory.json"

    def test_audio_temp_file(self):
        s = Settings()
        assert s.audio_temp_file.name == "temp_kfu_voice.mp3"

    def test_audio_mic_file(self):
        s = Settings()
        assert s.audio_mic_file.name == "temp_audio.wav"

    def test_data_dir_field(self, tmp_path):
        with patch("core.settings._get_base_dir", return_value=tmp_path):
            reset_settings()
            s = Settings()
            assert s.data_dir == tmp_path / "data"

    def test_logs_dir_field(self, tmp_path):
        with patch("core.settings._get_base_dir", return_value=tmp_path):
            reset_settings()
            s = Settings()
            assert s.logs_dir == tmp_path / "logs"

    def test_base_dir_is_path(self):
        s = Settings()
        assert isinstance(s.base_dir, Path)

    def test_get_settings_singleton(self):
        reset_settings()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reset_settings(self):
        reset_settings()
        s1 = get_settings()
        reset_settings()
        s2 = get_settings()
        assert s1 is not s2

    def test_get_feature_flags(self):
        reset_settings()
        flags = get_feature_flags()
        assert isinstance(flags, FeatureFlags)
        assert flags.conversations is True

    def test_loads_customer_profile_file(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "customer_profile.json").write_text(
            '{"user_name":"Celso","company_name":"Celsius Sistemas"}',
            encoding="utf-8",
        )

        s = Settings(data_dir=data_dir)

        assert s.customer.user_name == "Celso"
        assert s.customer.company_name == "Celsius Sistemas"
        assert s.assistant.owner_name == "Celso"

    def test_loads_legacy_customer_profile_with_new_defaults(self, tmp_path):
        from core.modules import MODULE_CHAT, MODULE_SETTINGS

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "customer_profile.json").write_text(
            '{"company_name":"Empresa antiga"}',
            encoding="utf-8",
        )

        s = Settings(data_dir=data_dir)

        assert s.customer.company_name == "Empresa antiga"
        assert s.customer.company_description == ""
        assert s.customer.main_needs == ""
        assert MODULE_CHAT in s.modules.enabled
        assert MODULE_SETTINGS in s.modules.enabled

    def test_customer_env_wins_over_profile_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CELSIUS_CUSTOMER_USER_NAME", "Nome via env")
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "customer_profile.json").write_text(
            '{"user_name":"Nome salvo","company_name":"Empresa salva"}',
            encoding="utf-8",
        )

        s = Settings(data_dir=data_dir)

        assert s.customer.user_name == "Nome via env"
        assert s.customer.company_name == "Empresa salva"

    def test_loads_local_response_and_voice_preferences(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "celsius_settings.json").write_text(
            """
            {
              "response": {"mode": "tecnico", "temperature": 0.35, "top_p": 0.85},
              "voice": {"voice": "pt-BR-FranciscaNeural", "rate": "+8%", "pitch": "+0Hz"},
              "mobile": {
                "enabled": true,
                "allow_lan": true,
                "pairing_token": "abc123",
                "use_https": false
              }
            }
            """,
            encoding="utf-8",
        )

        s = Settings(data_dir=data_dir)

        assert s.response.mode == "tecnico"
        assert s.response.temperature == 0.35
        assert s.voice.voice == "pt-BR-FranciscaNeural"
        assert s.voice.rate == "+8%"
        assert s.mobile.enabled is True
        assert s.mobile.allow_lan is True
        assert s.mobile.pairing_token == "abc123"
        assert s.mobile.use_https is False

    def test_save_local_preferences(self, tmp_path):
        s = Settings(data_dir=tmp_path)
        s.response.mode = "relatorio"
        s.voice.voice = "pt-BR-FranciscaNeural"
        s.modules.set_enabled(["suppliers"])

        path = s.save_local_preferences()

        data = path.read_text(encoding="utf-8")
        assert "relatorio" in data
        assert "pt-BR-FranciscaNeural" in data
        assert "suppliers" in data
        assert "modules" in data
        assert "mobile" in data

    def test_loads_module_preferences(self, tmp_path):
        from core.modules import MODULE_CHAT, MODULE_SETTINGS, MODULE_SUPPLIERS

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "celsius_settings.json").write_text(
            """
            {
              "modules": {
                "enabled": ["suppliers", "unknown"],
                "first_setup_completed": true
              }
            }
            """,
            encoding="utf-8",
        )

        s = Settings(data_dir=data_dir)

        assert MODULE_SUPPLIERS in s.modules.enabled
        assert MODULE_CHAT in s.modules.enabled
        assert MODULE_SETTINGS in s.modules.enabled
        assert "unknown" not in s.modules.enabled
        assert s.modules.first_setup_completed is True


class TestEnvVarOverride:
    def test_model_settings_env_override(self, monkeypatch):
        monkeypatch.setenv("CELSIUS_MODEL_LLM_MODEL", "custom-model")
        s = ModelSettings()
        assert s.llm_model == "custom-model"

    def test_rag_settings_env_override(self, monkeypatch):
        monkeypatch.setenv("CELSIUS_RAG_CHUNK_SIZE", "1000")
        s = RagSettings()
        assert s.chunk_size == 1000

    def test_feature_flags_env_override(self, monkeypatch):
        monkeypatch.setenv("CELSIUS_FEATURE_RAG", "false")
        s = FeatureFlags()
        assert s.rag is False

    def test_security_env_override(self, monkeypatch):
        monkeypatch.setenv("CELSIUS_SECURITY_SANDBOX_ENABLED", "false")
        s = SecuritySettings()
        assert s.sandbox_enabled is False

    def test_customer_env_override(self, monkeypatch):
        monkeypatch.setenv("CELSIUS_CUSTOMER_COMPANY_NAME", "Empresa Teste")
        s = CustomerSettings()
        assert s.company_name == "Empresa Teste"

    def test_response_env_override(self, monkeypatch):
        monkeypatch.setenv("CELSIUS_RESPONSE_MODE", "tecnico")
        s = ResponseStyleSettings()
        assert s.mode == "tecnico"

    def test_voice_env_override(self, monkeypatch):
        monkeypatch.setenv("CELSIUS_VOICE_VOICE", "pt-BR-FranciscaNeural")
        s = VoiceSettings()
        assert s.voice == "pt-BR-FranciscaNeural"
