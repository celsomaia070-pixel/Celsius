"""Tests for asynchronous local web chat coordination."""

import asyncio
import threading
import time

import pytest

from core.chat_attachments import AttachmentError, AttachmentStore
from core.chat_service import ChatBusyError, ChatCoordinator
from core.conversations import ConversationManager
from core.settings import Settings
from core.web_api.events import EventHub


@pytest.fixture
def chat_settings(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        logs_dir=tmp_path / "logs",
    )
    settings.features.memory = False
    return settings


def _wait_for_terminal(coordinator: ChatCoordinator, job_id: str, timeout: float = 3) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = coordinator.get_job(job_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("A tarefa de chat nao terminou no prazo do teste.")


def _coordinator(chat_settings, tmp_path, responder) -> ChatCoordinator:
    return ChatCoordinator(
        settings=chat_settings,
        event_hub=EventHub(),
        conversation_manager=ConversationManager(tmp_path / "conversations"),
        attachment_store=AttachmentStore(
            tmp_path / "uploads",
            allowed_extensions=chat_settings.all_extensions,
            max_size_mb=1,
        ),
        responder=responder,
        ensure_model_ready=lambda _status: None,
    )


class TestAttachmentStore:
    def test_accepts_supported_file_and_removes_it(self, chat_settings, tmp_path):
        store = AttachmentStore(
            tmp_path / "uploads",
            allowed_extensions=chat_settings.all_extensions,
            max_size_mb=1,
        )
        attachment = store.save("relatorio.txt", b"conteudo local")

        assert store.resolve([attachment.id]) == [attachment]
        assert attachment.path.is_file()

        store.discard([attachment.id])
        assert not attachment.path.exists()

    def test_rejects_traversal_and_unsupported_extension(self, chat_settings, tmp_path):
        store = AttachmentStore(
            tmp_path / "uploads",
            allowed_extensions=chat_settings.all_extensions,
            max_size_mb=1,
        )

        with pytest.raises(AttachmentError, match="nao suportado"):
            store.save("../programa.exe", b"binario")


class TestChatCoordinator:
    def test_uses_injected_memory_service(self, chat_settings, tmp_path):
        chat_settings.features.memory = True
        captured = {}

        class Memories:
            @staticmethod
            def search(query):
                assert query == "Quem sou eu?"
                return ["O usuario prefere respostas detalhadas"]

        def responder(prompt, **_kwargs):
            captured.update(prompt)
            return "Certo"

        coordinator = ChatCoordinator(
            settings=chat_settings,
            event_hub=EventHub(),
            conversation_manager=ConversationManager(tmp_path / "conversations"),
            responder=responder,
            ensure_model_ready=lambda _status: None,
            memory_service=Memories(),
        )
        try:
            submitted = coordinator.submit(message="Quem sou eu?")
            job = _wait_for_terminal(coordinator, submitted["id"])
        finally:
            coordinator.shutdown()

        assert job["status"] == "completed"
        assert captured["documento"] == ""
        assert captured["memorias_relevantes"] == ["O usuario prefere respostas detalhadas"]

    def test_streams_and_persists_response(self, chat_settings, tmp_path):
        def responder(_prompt, *, fn_status, fn_passo, fn_chunk):
            assert fn_passo is None
            fn_status("Pensando...")
            fn_chunk("Resposta ")
            fn_chunk("local")
            return "Resposta local"

        coordinator = _coordinator(chat_settings, tmp_path, responder)
        try:
            submitted = coordinator.submit(message="Ola Celsius")
            job = _wait_for_terminal(coordinator, submitted["id"])
            conversation = coordinator.get_conversation(job["conversation_id"])
        finally:
            coordinator.shutdown()

        assert job["status"] == "completed"
        assert job["response"] == "Resposta local"
        assert job["chunk_count"] == 2
        assert [message["role"] for message in conversation["messages"]] == [
            "user",
            "assistant",
        ]

    def test_attachment_content_reaches_prompt(self, chat_settings, tmp_path):
        captured = {}

        def responder(prompt, **_kwargs):
            captured.update(prompt)
            return "Documento analisado"

        coordinator = _coordinator(chat_settings, tmp_path, responder)
        attachment = coordinator.attachments.save("dados.txt", b"faturamento 2500")
        try:
            submitted = coordinator.submit(
                message="Analise o arquivo",
                attachment_ids=[attachment.id],
            )
            job = _wait_for_terminal(coordinator, submitted["id"])
        finally:
            coordinator.shutdown()

        assert job["status"] == "completed"
        assert "faturamento 2500" in captured["documento"]
        assert not attachment.path.exists()

    def test_rejects_second_inference_and_cancels_first(self, chat_settings, tmp_path):
        started = threading.Event()

        def responder(_prompt, *, fn_status, **_kwargs):
            started.set()
            while True:
                fn_status("Elaborando...")
                time.sleep(0.01)

        coordinator = _coordinator(chat_settings, tmp_path, responder)
        try:
            first = coordinator.submit(message="Primeira pergunta")
            assert started.wait(timeout=1)
            with pytest.raises(ChatBusyError):
                coordinator.submit(message="Segunda pergunta")
            coordinator.cancel(first["id"])
            cancelled = _wait_for_terminal(coordinator, first["id"])
        finally:
            coordinator.shutdown()

        assert cancelled["status"] == "cancelled"


@pytest.mark.asyncio
async def test_chat_events_keep_lifecycle_order(chat_settings, tmp_path):
    hub = EventHub()

    def responder(_prompt, *, fn_chunk, **_kwargs):
        fn_chunk("Certo")
        return "Certo"

    coordinator = ChatCoordinator(
        settings=chat_settings,
        event_hub=hub,
        conversation_manager=ConversationManager(tmp_path / "conversations"),
        responder=responder,
        ensure_model_ready=lambda _status: None,
    )
    try:
        async with hub.subscribe() as queue:
            coordinator.submit(message="Teste de eventos")
            event_types = []
            while "chat.completed" not in event_types:
                event = await asyncio.wait_for(queue.get(), timeout=2)
                event_types.append(event["type"])
    finally:
        coordinator.shutdown()

    assert event_types[0] == "chat.accepted"
    assert "chat.started" in event_types
    assert "chat.chunk" in event_types
    assert event_types[-1] == "chat.completed"
