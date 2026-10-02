"""Tests for memory service."""

import pytest

from core.config import Settings
from core.memory import (
    ORIGEM_CONVERSA,
    ORIGEM_USUARIO,
    MemoryService,
    _is_near_duplicate,
    _parse_facts,
    get_memory_service,
    memory_query_context,
    remember_from_turn,
)


@pytest.fixture(autouse=True)
def isolate_memory_singleton(tmp_path, monkeypatch):
    import core.memory as memory

    isolated = Settings(base_dir=tmp_path)
    monkeypatch.setattr(memory, "get_settings", lambda: isolated)
    monkeypatch.setattr(memory, "_memory_service", None)


class TestMemoryService:
    @pytest.fixture
    def temp_settings(self, tmp_path):
        return Settings(base_dir=tmp_path)

    @pytest.fixture
    def memory_service(self, temp_settings):
        return MemoryService(temp_settings)

    def test_add_and_get_memory(self, memory_service):
        memory_service.add("Test memory 1")
        memory_service.add("Test memory 2")

        memories = memory_service.get_all()
        assert len(memories) == 2
        assert memories[0]["texto"] == "Test memory 1"
        assert memories[1]["texto"] == "Test memory 2"
        assert "data" in memories[0]

    def test_search_memory(self, memory_service):
        memory_service.add("O usuario gosta de pizza")
        memory_service.add("O usuario odeia brocolis")
        memory_service.add("O usuario programa em Python")

        # Only relevant memories are returned, even when the collection is small.
        results = memory_service.search("pizza")
        assert results == ["O usuario gosta de pizza"]

        # Test with enough memories to trigger semantic search
        memory_service.clear()
        for i in range(20):
            memory_service.add(f"Memoria numero {i} sobre assunto {chr(65 + i % 26)}")
        results = memory_service.search("Memoria numero 5")
        assert len(results) <= 10  # top_memories limit

    def test_unrelated_query_does_not_load_embedding_model(self, temp_settings, monkeypatch):
        service = MemoryService(temp_settings)
        service._memories = [{"texto": "O usuario gosta de cafe"}]
        service._file_signature = service._signature()
        monkeypatch.setattr(
            MemoryService,
            "_model_instance",
            property(lambda _self: pytest.fail("embedding model should stay lazy")),
        )

        assert service.search("explique energia solar") == []

    def test_search_empty(self, memory_service):
        results = memory_service.search("anything")
        assert results == []

    def test_clear_memory(self, memory_service):
        memory_service.add("Test")
        memory_service.clear()
        assert memory_service.get_all() == []
        assert memory_service.search("test") == []

    def test_persistence(self, temp_settings):
        service1 = MemoryService(temp_settings)
        service1.add("Persistent memory")

        # Create new service - should load from file
        service2 = MemoryService(temp_settings)
        memories = service2.get_all()
        assert len(memories) == 1
        assert memories[0]["texto"] == "Persistent memory"

    def test_multiple_instances_do_not_overwrite_recent_memories(self, temp_settings):
        service1 = MemoryService(temp_settings)
        service2 = MemoryService(temp_settings)

        service1.add("Memoria da janela desktop")
        service2.add("Memoria da interface web")

        assert [item["texto"] for item in service1.get_all()] == [
            "Memoria da janela desktop",
            "Memoria da interface web",
        ]

    def test_thread_safety(self, memory_service):
        import threading
        import time

        def add_memories(prefix, count):
            for i in range(count):
                memory_service.add(f"{prefix} memory {i}")
                time.sleep(0.001)

        threads = [
            threading.Thread(target=add_memories, args=(f"thread_{i}", 10)) for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        memories = memory_service.get_all()
        assert len(memories) == 50

    def test_get_memory_service_singleton(self, temp_settings):
        # Reset global
        import core.memory

        core.memory._memory_service = None

        service1 = get_memory_service()
        # Can't easily test singleton with different settings, but verify it works
        assert service1 is not None


class TestMemoryOrigins:
    @pytest.fixture
    def temp_settings(self, tmp_path):
        return Settings(base_dir=tmp_path)

    @pytest.fixture
    def memory_service(self, temp_settings):
        return MemoryService(temp_settings)

    def test_user_memory_defaults_to_user_origin(self, memory_service):
        memoria = memory_service.add("Memo do usuario")
        assert memoria["origem"] == ORIGEM_USUARIO
        assert memoria["conversation_id"] == ""

    def test_conversation_memory_keeps_origin_and_id(self, memory_service):
        memoria = memory_service.add_unique(
            "Fato da conversa",
            origem=ORIGEM_CONVERSA,
            conversation_id="abc123",
        )
        assert memoria is not None
        assert memoria["origem"] == ORIGEM_CONVERSA
        assert memoria["conversation_id"] == "abc123"

    def test_user_memories_exclude_conversation_facts(self, memory_service):
        memory_service.add("Memo do usuario")
        memory_service.add_unique(
            "Fato da conversa",
            origem=ORIGEM_CONVERSA,
            conversation_id="abc123",
        )
        user = memory_service.get_user_memories()
        assert [item["texto"] for item in user] == ["Memo do usuario"]

    def test_get_conversation_memories_filters_by_id(self, memory_service):
        memory_service.add_unique(
            "O usuario gosta de churrasco na cidade",
            origem=ORIGEM_CONVERSA,
            conversation_id="conv-a",
        )
        memory_service.add_unique(
            "O usuario estuda violao aos fins de semana",
            origem=ORIGEM_CONVERSA,
            conversation_id="conv-b",
        )
        assert memory_service.get_conversation_memories("conv-a") == [
            "O usuario gosta de churrasco na cidade"
        ]
        assert memory_service.get_conversation_memories("conv-b") == [
            "O usuario estuda violao aos fins de semana"
        ]

    def test_delete_for_conversation_removes_only_its_facts(self, memory_service):
        memory_service.add("Memo do usuario")
        memory_service.add_unique(
            "O usuario gosta de churrasco na cidade",
            origem=ORIGEM_CONVERSA,
            conversation_id="conv-a",
        )
        memory_service.add_unique(
            "O usuario estuda violao aos fins de semana",
            origem=ORIGEM_CONVERSA,
            conversation_id="conv-b",
        )

        removed = memory_service.delete_for_conversation("conv-a")

        assert removed == 1
        all_texts = [item["texto"] for item in memory_service.get_all()]
        assert all_texts == [
            "Memo do usuario",
            "O usuario estuda violao aos fins de semana",
        ]

    def test_delete_for_conversation_is_idempotent(self, memory_service):
        memory_service.add_unique(
            "Fato da conversa",
            origem=ORIGEM_CONVERSA,
            conversation_id="conv-a",
        )
        assert memory_service.delete_for_conversation("conv-a") == 1
        assert memory_service.delete_for_conversation("conv-a") == 0

    def test_persistence_keeps_origin(self, temp_settings):
        service = MemoryService(temp_settings)
        service.add_unique(
            "Fato da conversa",
            origem=ORIGEM_CONVERSA,
            conversation_id="conv-xyz",
        )
        reloaded = MemoryService(temp_settings)
        item = reloaded.get_all()[0]
        assert item["origem"] == ORIGEM_CONVERSA
        assert item["conversation_id"] == "conv-xyz"


class TestLongTermMemory:
    @pytest.fixture
    def temp_settings(self, tmp_path):
        return Settings(base_dir=tmp_path)

    @pytest.fixture
    def memory_service(self, temp_settings):
        return MemoryService(temp_settings)

    def test_add_unique_skips_near_duplicate(self, memory_service):
        memory_service.add("O usuario gosta de cafe")
        assert memory_service.add_unique("O usuario gosta de cafe e leite") is None
        assert memory_service.add_unique("O usuario mora em Curitiba") is not None
        assert len(memory_service.get_all()) == 2

    def test_search_multi_merges_queries(self, memory_service):
        memory_service.add("O usuario gosta de pizza")
        memory_service.add("O usuario programa em Python")
        results = memory_service.search_multi(["pizza", "python"])
        assert results == ["O usuario gosta de pizza", "O usuario programa em Python"]

    def test_memory_query_context_dedupes_and_orders(self):
        queries = memory_query_context(["como estou?", "preciso de ajuda"])
        assert queries == ["como estou?", "preciso de ajuda"]
        assert memory_query_context(["duplicado", "duplicado"]) == ["duplicado"]
        assert memory_query_context([], extra_queries=["tema x"]) == ["tema x"]

    def test_parse_facts_extracts_json_array(self):
        assert _parse_facts('fora {"a":1} ["fato um", "fato dois"] lixo', 5) == [
            "fato um",
            "fato dois",
        ]
        assert _parse_facts("sem array", 5) == []
        assert _parse_facts('["a"]', 1) == ["a"]

    def test_remember_from_turn_stores_new_facts(self, temp_settings, monkeypatch):
        import core.memory

        service = MemoryService(temp_settings)
        monkeypatch.setattr(core.memory, "get_settings", lambda: temp_settings)
        monkeypatch.setattr(core.memory, "get_memory_service", lambda: service)
        monkeypatch.setattr(
            core.memory,
            "_extract_facts_from_llm",
            lambda dialogo, max_facts: [
                "O usuario adora cafe",
                "O usuario mora em Sao Paulo",
            ],
        )

        added = remember_from_turn(
            [{"role": "user", "content": "Eu adoro cafe e moro em Sao Paulo"}],
            max_facts=5,
        )
        assert added == 2
        assert len(service.get_all()) == 2

    def test_remember_from_turn_drops_duplicates(self, temp_settings, monkeypatch):
        import core.memory

        service = MemoryService(temp_settings)
        service.add("O usuario gosta de cafe")
        monkeypatch.setattr(core.memory, "get_settings", lambda: temp_settings)
        monkeypatch.setattr(core.memory, "get_memory_service", lambda: service)
        monkeypatch.setattr(
            core.memory,
            "_extract_facts_from_llm",
            lambda dialogo, max_facts: ["O usuario gosta de cafe e leite"],
        )

        assert remember_from_turn([{"role": "user", "content": "cafe"}], max_facts=5) == 0
        assert len(service.get_all()) == 1

    def test_remember_from_turn_tags_facts_with_conversation(self, temp_settings, monkeypatch):
        import core.memory

        service = MemoryService(temp_settings)
        monkeypatch.setattr(core.memory, "get_settings", lambda: temp_settings)
        monkeypatch.setattr(core.memory, "get_memory_service", lambda: service)
        monkeypatch.setattr(
            core.memory,
            "_extract_facts_from_llm",
            lambda dialogo, max_facts: ["O usuario adora churrasco"],
        )

        added = remember_from_turn(
            [{"role": "user", "content": "Gosto de churrasco"}],
            max_facts=5,
            conversation_id="conv-xpto",
        )
        assert added == 1
        facts = service.get_conversation_memories("conv-xpto")
        assert facts == ["O usuario adora churrasco"]
        assert [item["texto"] for item in service.get_user_memories()] == []

    def test_is_near_duplicate(self):
        assert _is_near_duplicate("O usuario gosta de cafe", ["O usuario gosta de cafe e leite"])
        assert not _is_near_duplicate("O usuario gosta de cafe", ["O usuario mora em Curitiba"])
        assert not _is_near_duplicate("", [])


class TestBackwardCompatibility:
    @pytest.fixture
    def temp_settings(self, tmp_path):
        return Settings(base_dir=tmp_path)

    def test_carregar_memorias(self, temp_settings):
        from core.memory import carregar_memorias, salvar_memorias

        salvar_memorias([{"texto": "Test 1"}, {"texto": "Test 2"}])
        memorias = carregar_memorias()
        assert len(memorias) == 2

    def test_buscar_memorias(self, temp_settings):
        from core.memory import buscar_memorias, salvar_memorias

        salvar_memorias([{"texto": "Usuario gosta de cafe"}])
        results = buscar_memorias("cafe")
        assert len(results) == 1
        assert "cafe" in results[0]
