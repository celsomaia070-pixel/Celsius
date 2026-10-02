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
from ai.interruption import INTERRUPTED_MARKER


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


def test_explicit_memory_read_skips_team_orchestration_and_old_topics(
    chat_settings, tmp_path, monkeypatch
):
    from types import SimpleNamespace

    import ai.multi_agent as team

    chat_settings.features.memory = True
    queries = []
    prompts = []

    def search_multi(items):
        queries.extend(items)
        return ["Fato registrado no teste sobre TecUnimar"]

    def respond(prompt, **kwargs):
        prompts.append(prompt)
        return "Resposta com a memoria local"

    coordinator = _coordinator(chat_settings, tmp_path, respond)
    coordinator._ensure_model_ready_callback = lambda _status: pytest.fail("model loaded")
    coordinator.memory_service = SimpleNamespace(search_multi=search_multi)
    monkeypatch.setattr(team, "run_multi_agent_work", lambda *a, **k: pytest.fail("team"))
    conversation = coordinator.conversations.create()
    cid = conversation["id"]
    coordinator.conversations.add_message(cid, "user", "outro assunto antigo")
    question = "o celsius tem alguma relação com o tecunimar, procure nas memorias"
    try:
        job = coordinator.submit(
            message=question,
            conversation_id=cid,
            work_agents=["pesquisador", "documentos"],
        )
        finished = _wait_for_terminal(coordinator, job["id"])
        assert finished["status"] == "completed"
        assert queries == [question]
        assert prompts[0]["memorias_relevantes"] == ["Fato registrado no teste sobre TecUnimar"]
        assert prompts[0]["memorias_consultadas"] is True
    finally:
        coordinator.shutdown()


@pytest.mark.parametrize(
    "message", ["TAREFA: Boa tarde", "TAREFA: Olá Celsius, tudo bem?", "Boa tarde"]
)
def test_greetings_from_old_work_clients_do_not_enter_task_runner(chat_settings, tmp_path, message):
    prompts = []

    def responder(prompt, **kwargs):
        from ai.task_runtime import is_task_command

        prompts.append(prompt)
        assert not is_task_command(prompt["pergunta"])
        return "Boa tarde! Como posso ajudar?"

    coordinator = _coordinator(chat_settings, tmp_path, responder)
    try:
        job = coordinator.submit(
            message=message, agent_mode="executor", work_agents=["executor", "documentos"]
        )
        result = _wait_for_terminal(coordinator, job["id"])
        assert result["status"] == "completed"
        assert not prompts
        assert result["agent_mode"] == "assistente"
        assert not result["work_agents"]
        conversation = coordinator.conversations.load(job["conversation_id"])
        assert not conversation["messages"][0]["content"].startswith("TAREFA:")
    finally:
        coordinator.shutdown()


def test_greeting_followed_by_work_is_not_stripped(chat_settings, tmp_path):
    prompts = []

    def responder(prompt, **kwargs):
        prompts.append(prompt)
        return "Solicitação de trabalho recebida."

    coordinator = _coordinator(chat_settings, tmp_path, responder)
    try:
        job = coordinator.submit(
            message="TAREFA: Boa tarde, gere um relatório de estoque", agent_mode="estoque"
        )
        assert _wait_for_terminal(coordinator, job["id"])["status"] == "completed"
        assert prompts[0]["pergunta"].startswith("TAREFA:")
        assert prompts[0]["agent_mode"] == "estoque"
    finally:
        coordinator.shutdown()


@pytest.mark.parametrize(
    "message",
    [
        "quem é voce?",
        "olá me diga as suas capacidades",
        "TAREFA: Quem é você?!",
        "TAREFA: Olá, quais são suas capacidades?",
        "O que você pode realizar quais suas ferramentas?",
        "TAREFA: Olá, quais são suas ferramentas?",
    ],
)
def test_fast_replies_skip_all_expensive_paths(chat_settings, tmp_path, monkeypatch, message):
    import core.chat_service as service
    import core.embeddings as embeddings
    import core.memory as memory
    import ai.react as react
    import ai.task_runtime as tasks

    def forbidden(*args, **kwargs):
        pytest.fail("quick reply entered heavy path")

    chat_settings.features.memory = True
    coordinator = _coordinator(chat_settings, tmp_path, forbidden)
    monkeypatch.setattr(coordinator, "_ensure_model_ready_callback", forbidden)
    monkeypatch.setattr(coordinator, "_load_memories", forbidden)
    monkeypatch.setattr(coordinator._executor, "submit", forbidden)
    monkeypatch.setattr(embeddings, "create_sentence_transformer", forbidden)
    monkeypatch.setattr(memory, "buscar_memorias", forbidden)
    monkeypatch.setattr(react, "loop_react", forbidden)
    monkeypatch.setattr(tasks, "handle_task_command", forbidden)
    monkeypatch.setattr(service, "resolve_mode", forbidden)
    try:
        job = coordinator.submit(
            message=message,
            work_mode=True,
            agent_mode="executor",
            work_agents=["executor", "documentos"],
        )
        assert job["status"] == "completed"
        assert job["intent"] == "conversation" and not job["work_agents"]
        assert job["timings"]["model_state"] == "not_used"
        assert job["timings"]["first_token_ms"] is not None
        stored = coordinator.conversations.load(job["conversation_id"])
        assert stored["messages"][-1]["content"] == job["response"]
    finally:
        coordinator.shutdown()


def test_work_general_question_uses_model_without_task_or_memory(
    chat_settings, tmp_path, monkeypatch
):
    captured = []
    coordinator = _coordinator(
        chat_settings,
        tmp_path,
        lambda prompt, **kwargs: captured.append(prompt) or "Resposta pelo modelo",
    )
    monkeypatch.setattr(coordinator, "_load_memories", lambda *a: pytest.fail("memory"))
    prepared = []
    monkeypatch.setattr(
        coordinator, "_ensure_model_ready_callback", lambda *a: prepared.append(True)
    )
    try:
        job = coordinator.submit(
            message="Explique energia solar",
            work_mode=True,
            agent_mode="executor",
            work_agents=["executor", "documentos"],
        )
        result = _wait_for_terminal(coordinator, job["id"])
        assert result["status"] == "completed" and prepared
        assert captured[0]["pergunta"] == "Explique energia solar"
        assert captured[0]["agent_mode"] == "assistente"
        assert not captured[0]["work_agents"] and not captured[0]["memorias_relevantes"]
    finally:
        coordinator.shutdown()


def test_common_responder_observes_cancellation_without_emitting_chunks(chat_settings, tmp_path):
    entered = threading.Event()

    def responder(prompt, *, should_cancel, **kwargs):
        from core.operation_control import check_control

        entered.set()
        while not should_cancel():
            time.sleep(0.005)
        check_control()

    coordinator = _coordinator(chat_settings, tmp_path, responder)
    try:
        job = coordinator.submit(message="Explique energia solar")
        assert entered.wait(1)
        coordinator.cancel(job["id"])
        result = _wait_for_terminal(coordinator, job["id"])
        assert result["status"] == "cancelled"
        assert result["response"]
        assert (
            coordinator.conversations.load(job["conversation_id"])["messages"][-1]["role"]
            == "assistant"
        )
    finally:
        coordinator.shutdown()


def test_timeout_is_explicit_and_preserves_partial_answer(chat_settings, tmp_path):
    from core.operation_control import OperationTimeoutError

    def responder(prompt, *, fn_chunk, **kwargs):
        fn_chunk("Parte concluída.")
        raise OperationTimeoutError("Limite de tempo atingido; progresso parcial.")

    coordinator = _coordinator(chat_settings, tmp_path, responder)
    try:
        job = coordinator.submit(message="Explique energia solar")
        result = _wait_for_terminal(coordinator, job["id"])
        assert result["status"] == "failed"
        assert "Limite" in result["response"] and "Parte concluída" in result["response"]
        assert coordinator.conversations.load(job["conversation_id"])["messages"][-1]["metadata"][
            "incomplete"
        ]
    finally:
        coordinator.shutdown()


def test_ensure_model_ready_applies_profile_runtime_kwargs(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from core.model_router import get_model_profile

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"gguf")
    settings = SimpleNamespace(
        llm_model="qwen2.5-vl-7b-q4km",
        get_model_path=lambda _mid: model_file,
        model=SimpleNamespace(
            num_ctx=2048,
            n_gpu_layers=0,
            n_batch=512,
            n_threads=4,
            use_mmap=True,
            use_mlock=False,
        ),
    )

    class _Manager:
        def is_healthy(self):
            return False

        def start(self, **kwargs):
            self.kwargs = kwargs
            return True

    manager = _Manager()
    import core.llama_cpp as llama_cpp_module

    monkeypatch.setattr(llama_cpp_module, "get_llama_manager", lambda: manager)

    coordinator = ChatCoordinator.__new__(ChatCoordinator)
    coordinator.settings = settings
    coordinator._ensure_model_ready(lambda *_: None)

    profile = get_model_profile("qwen2.5-vl-7b-q4km")
    assert manager.kwargs["n_ctx"] == profile.default_n_ctx
    assert manager.kwargs["n_gpu_layers"] == profile.default_n_gpu_layers


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
        def responder(_prompt, *, fn_status, fn_passo, fn_chunk, should_cancel):
            assert fn_passo is None
            fn_status("Pensando...")
            fn_chunk("Resposta ")
            fn_chunk("local")
            return "Resposta local"

        coordinator = _coordinator(chat_settings, tmp_path, responder)
        try:
            submitted = coordinator.submit(message="Explique energia solar")
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

    def test_cancel_preserves_marked_partial_response(self, chat_settings, tmp_path):
        started = threading.Event()

        def responder(_prompt, *, fn_status, fn_chunk, **_kwargs):
            started.set()
            fn_chunk("Trecho parcial")
            while True:
                fn_status("Elaborando...")
                time.sleep(0.01)

        coordinator = _coordinator(chat_settings, tmp_path, responder)
        try:
            first = coordinator.submit(message="Pergunta longa")
            assert started.wait(timeout=1)
            coordinator.cancel(first["id"])
            cancelled = _wait_for_terminal(coordinator, first["id"])
            conversation = coordinator.get_conversation(cancelled["conversation_id"])
        finally:
            coordinator.shutdown()

        assert cancelled["status"] == "cancelled"
        assert "Trecho parcial" in cancelled["response"]
        assert INTERRUPTED_MARKER in cancelled["response"]
        assistant_messages = [m for m in conversation["messages"] if m["role"] == "assistant"]
        assert assistant_messages
        assert INTERRUPTED_MARKER in assistant_messages[-1]["content"]


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
