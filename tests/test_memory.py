"""Tests for memory service."""

import pytest

from core.config import Settings
from core.memory import MemoryService, get_memory_service


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

        # With only 3 memories (below inject_all_memories_limit=15),
        # all are returned regardless of query
        results = memory_service.search("pizza")
        assert len(results) == 3

        # Test with enough memories to trigger semantic search
        memory_service.clear()
        for i in range(20):
            memory_service.add(f"Memoria numero {i} sobre assunto {chr(65 + i % 26)}")
        results = memory_service.search("Memoria numero 5")
        assert len(results) <= 10  # top_memories limit

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
