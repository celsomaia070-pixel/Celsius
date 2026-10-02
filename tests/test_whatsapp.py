"""Remote commands use the same coordinator without replaying mutations or trusting contacts."""

from types import SimpleNamespace
import time

import pytest
from fastapi.testclient import TestClient

from core.chat_service import ChatBusyError, ChatCoordinator
from core.settings import Settings
from core.users import UserRole, UserService
from core.web_api import EventHub, create_app
from core.whatsapp import WhatsAppService, command_text, parse_contact_message, route_whatsapp_message

SELF = "5514999999999@s.whatsapp.net"


class FakeCoordinator:
    def __init__(self):
        self.submissions = []
        self.busy = False
        self.job = {"id": "job1", "status": "running", "conversation_id": "abcdef123456", "attachments": []}

    def submit(self, **kwargs):
        if self.busy:
            raise ChatBusyError("Busy")
        self.submissions.append(kwargs)
        return dict(self.job)

    def get_job(self, job_id):
        return dict(self.job)

    def cancel(self, job_id):
        self.job["status"] = "cancelled"


@pytest.fixture
def service(tmp_path):
    settings = Settings(base_dir=tmp_path, data_dir=tmp_path / "data")
    users = UserService(settings.data_dir)
    user = users.register("owner@example.test", "test-password-123")
    coordinator = FakeCoordinator()
    instance = WhatsAppService(settings=settings, coordinator=coordinator, user_service=users, event_hub=EventHub())
    instance.config["owner_id"] = user.id
    instance._state = "connected"
    instance._self_ids = {SELF}
    calls = []

    def rpc(action, **kwargs):
        calls.append((action, kwargs))
        if action == "resolve":
            return {"matches": [{"jid": "5514888888888@s.whatsapp.net", "name": "João"}]}
        return {"message_id": "out1"}

    instance._rpc = rpc
    instance.test_calls = calls
    yield instance
    instance.shutdown()
    instance.db.close()


def receive(service, text="Celsius, gere um relatório", **changes):
    service.receive({"type": "message", "id": "msg1", "jid": SELF, "from_me": True, "text": text, **changes})


def count(service):
    return service.db.execute("SELECT COUNT(*) FROM inbox").fetchone()[0]


def test_optional_wake_name_and_contact_parsing():
    assert command_text("Celsius, gere relatório") == "gere relatório"
    assert command_text("AUTORIZAR 1234") == "AUTORIZAR 1234"
    assert parse_contact_message("mande mensagem para meu contato João: olá") == ("João", "olá")
    assert parse_contact_message("mande mensagem para o meu contato João: olá") == ("João", "olá")
    assert parse_contact_message("Envie uma mensagem para Maria dizendo que chegou") == ("Maria", "chegou")
    assert parse_contact_message("Gere um relatório") is None


@pytest.mark.parametrize("changes", [
    {"from_me": False}, {"jid": "5514111111111@s.whatsapp.net"},
    {"jid": "group@g.us"}, {"text": "Celsius\nResposta do agente"},
    {"text": "x" * 20001},
])
def test_rejects_contacts_groups_echoes_and_oversized_commands(service, changes):
    receive(service, **changes)
    assert count(service) == 0


def test_deduplication_and_agent_job_use_shared_conversation(service):
    receive(service)
    receive(service)
    assert count(service) == 1
    service._tick()
    assert service.coordinator.submissions[0]["source"] == "whatsapp"
    assert service.coordinator.submissions[0]["message"] == "TAREFA: gere um relatório"
    assert service.coordinator.submissions[0]["agent_mode"] == "executor"
    service._tick()
    assert len(service.coordinator.submissions) == 1
    service.coordinator.job.update(status="completed", response="Relatório concluído")
    service._tick()
    assert service.db.execute("SELECT state FROM inbox").fetchone()[0] == "completed"
    assert service.test_calls[-1][1]["text"] == "Celsius\nRelatório concluído"
    receive(service, "AUTORIZAR 1234", id="msg2")
    service._tick()
    assert service.coordinator.submissions[-1]["message"] == "AUTORIZAR 1234"
    assert service.coordinator.submissions[-1]["conversation_id"] == "abcdef123456"


def test_busy_desktop_preserves_pending_request(service):
    service.coordinator.busy = True
    receive(service, "dê entrada de 10 peças")
    service._tick()
    assert service.db.execute("SELECT state FROM inbox").fetchone()[0] == "queued"
    assert not service.coordinator.submissions
    assert "entrou na fila" in service.test_calls[-1][1]["text"]
    count_before = len(service.test_calls)
    service._tick()
    assert len(service.test_calls) == count_before
    service.coordinator.busy = False
    service._tick()
    assert len(service.coordinator.submissions) == 1


def test_generated_documents_are_sent_from_registered_outputs(service, tmp_path):
    path = tmp_path / "report.docx"
    path.write_bytes(b"test-generated-report")
    service.coordinator.outputs = SimpleNamespace(get=lambda _: SimpleNamespace(path=path, name="Relatório.docx"))
    receive(service)
    service._tick()
    service.coordinator.job.update(status="completed", response="Pronto", attachments=[{"id": "output1"}])
    service._tick()
    action, payload = service.test_calls[-1]
    assert action == "send" and payload["path"] == str(path)
    assert payload["name"] == "Relatório.docx"
    assert payload["jid"] == SELF


def test_contact_send_requires_single_use_confirmation(service):
    row = ("msg1", SELF, "mande mensagem para João: relatório pronto")
    receive(service, row[2])
    assert service._control(row)
    assert not any(payload.get("jid", "").startswith("551488") for _, payload in service.test_calls)
    code = service.db.execute("SELECT code FROM confirmations").fetchone()[0]
    service._control(("msg2", SELF, "CONFIRMAR " + code))
    sent = [payload for action, payload in service.test_calls if action == "send" and payload.get("jid", "").startswith("551488")]
    assert len(sent) == 1 and sent[0]["text"] == "relatório pronto"
    service._control(("msg3", SELF, "CONFIRMAR " + code))
    assert len([payload for action, payload in service.test_calls if action == "send" and payload.get("jid", "").startswith("551488")]) == 1


def test_deactivated_owner_cannot_submit_queued_task(service):
    receive(service)
    service.users.update_user(service.config["owner_id"], is_active=False)
    service._tick()
    assert not service.coordinator.submissions
    receive(service, id="msg2")
    assert count(service) == 1


def test_restart_marks_running_request_interrupted_without_replay(service):
    receive(service)
    service._tick()
    replacement = WhatsAppService(settings=service.settings, coordinator=service.coordinator,
                                  user_service=service.users, event_hub=EventHub())
    assert replacement.db.execute("SELECT state FROM inbox").fetchone()[0] == "interrupted"
    replacement._state = "connected"
    replacement._tick()
    assert len(service.coordinator.submissions) == 1
    replacement.db.close()


def test_dispatch_intent_is_persisted_before_starting_mutation(service):
    receive(service, "dê entrada de 10 peças")
    original = service.coordinator.submit

    def submit(**kwargs):
        assert service.db.execute("SELECT state FROM inbox").fetchone()[0] == "dispatching"
        return original(**kwargs)

    service.coordinator.submit = submit
    service._tick()
    assert service.db.execute("SELECT state FROM inbox").fetchone()[0] == "running"


def test_pairing_another_phone_does_not_execute_old_inbox(service):
    receive(service)
    service._self_ids = {"5514999990000@s.whatsapp.net"}
    service._tick()
    assert not service.coordinator.submissions
    assert service.db.execute("SELECT state FROM inbox").fetchone()[0] == "interrupted"


def test_api_protects_qr_and_connection_owner(tmp_path):
    settings = Settings(base_dir=tmp_path, data_dir=tmp_path / "data")
    app = create_app(settings=settings, event_hub=EventHub())
    service = app.state.whatsapp_service
    users = app.state.user_service
    owner = users.register("owner@example.test", "test-password-123")
    second = users.register("other@example.test", "test-password-123")
    service.config["owner_id"] = owner.id
    service._qr = "private-pairing-code"
    with TestClient(app) as client:
        assert client.get("/api/v1/whatsapp/status").status_code == 401
        client.post("/api/v1/auth/login", json={"email": owner.email, "password": "test-password-123"})
        response = client.get("/api/v1/whatsapp/status")
        assert response.status_code == 200 and response.json()["qr_image"].startswith("data:image/png;base64,")
        client.post("/api/v1/auth/login", json={"email": second.email, "password": "test-password-123"})
        assert client.get("/api/v1/whatsapp/status").status_code == 403
        assert client.post("/api/v1/whatsapp/connect").status_code == 403
        assert client.post("/api/v1/whatsapp/self-chat").status_code == 403
        users.update_user(second.id, role=UserRole.VIEWER)
        assert client.post("/api/v1/whatsapp/connect").status_code == 403


def test_initial_message_is_created_once_for_self_not_contacts(service):
    service.receive({"type": "connected", "self_ids": [SELF, "123456789012345@lid"]})
    assert service._welcome_pending
    assert not service.test_calls  # Reader must remain free to process RPC responses.
    status = service.open_self_chat()
    assert status["welcome_sent"]
    assert status["self_chat_url"] == "https://wa.me/5514999999999"
    assert len(service.test_calls) == 1
    assert service.test_calls[0][1]["jid"] == SELF
    assert service.test_calls[0][1]["text"].startswith("Celsius\n")
    service.receive({"type": "connected", "self_ids": [SELF]})
    assert not service._welcome_pending
    service.open_self_chat()
    assert len(service.test_calls) == 1
    service.open_self_chat(resend=True)
    assert len(service.test_calls) == 2
    # A second phone gets its own welcome, with no message to the old account.
    other = "5514999990000@s.whatsapp.net"
    service.receive({"type": "connected", "self_ids": [other]})
    service.open_self_chat()
    assert service.test_calls[-1][1]["jid"] == other


def test_failed_welcome_is_not_reported_as_sent_and_does_not_block_commands(service):
    def failed_rpc(*args, **kwargs):
        raise RuntimeError("delivery unknown")
    service._rpc = failed_rpc
    service.receive({"type": "connected", "self_ids": [SELF]})
    with pytest.raises(RuntimeError):
        service.open_self_chat()
    assert not service._welcome_pending
    assert not service.status()["welcome_sent"]
    assert service.status()["welcome_error"]
    receive(service, "AJUDA")
    assert count(service) == 1
    service.receive({"type": "reconnecting", "code": 515})
    assert not service.status()["self_chat_url"]
    diagnostic = __import__('json').loads((service.root / "status.json").read_text())
    assert diagnostic["disconnect_code"] == 515
    assert SELF not in str(diagnostic)


def test_self_chat_cannot_use_lid_as_phone_or_send_when_disconnected(service):
    service._self_ids = {"123456789012345@lid"}
    assert not service.status()["self_chat_url"]
    with pytest.raises(RuntimeError):
        service.open_self_chat()
    service._self_ids = {SELF}
    service._state = "disconnected"
    with pytest.raises(RuntimeError):
        service.open_self_chat()
    assert not service.test_calls


@pytest.mark.parametrize(("text", "mode", "task"), [
    ("Olá celsius, tudo bem?", "assistente", False),
    ("Oi", "assistente", False),
    ("Boa tarde", "assistente", False),
    ("Obrigado!", "assistente", False),
    ("Me explique como você funciona", "assistente", False),
    ("Celsius, gere um relatório", "executor", True),
    ("Por favor, dê entrada de 10 peças no estoque", "estoque", True),
    ("Pode gerar um relatório de estoque?", "estoque", True),
    ("Quero que preencha meu documento Word", "documentos", True),
    ("Olá Celsius, gere um novo PAEE", "documentos", True),
    ("Pesquise as notícias de IA da semana passada", "pesquisador", True),
    ("Qual é a previsão para os próximos 5 dias em Marília?", "pesquisador", True),
    ("Crie um script Python", "desenvolvedor", True),
    ("TAREFA: organize minha agenda", "executor", True),
])
def test_messages_choose_chat_or_capable_task_mode(service, text, mode, task):
    receive(service, text)
    service._tick()
    submitted = service.coordinator.submissions[0]
    assert submitted["agent_mode"] == mode
    assert submitted["message"].startswith("TAREFA:") is task
    assert submitted["source"] == "whatsapp"
    if not task:
        assert submitted["message"] == command_text(text)


def test_greeting_does_not_reset_task_lane_and_approval_stays_in_same_conversation(service):
    service._agent_mode = "documentos"
    service._conversation_id = "abcdef123456"
    receive(service, "Olá celsius, tudo bem?")
    service._tick()
    assert service.coordinator.submissions[0]["agent_mode"] == "assistente"
    assert service._agent_mode == "documentos"
    assert route_whatsapp_message("AUTORIZAR ABC123", service._agent_mode) == ("AUTORIZAR ABC123", "documentos")
    assert route_whatsapp_message("RETOMAR abcdef123456", service._agent_mode) == ("RETOMAR abcdef123456", "documentos")
    assert route_whatsapp_message("TAREFAS", service._agent_mode) == ("TAREFAS", "documentos")
    service.coordinator.job.update(status="completed", response="Olá!")
    service._tick()
    receive(service, "AUTORIZAR ABC123", id="msg2")
    service._tick()
    submitted = service.coordinator.submissions[-1]
    assert submitted["message"] == "AUTORIZAR ABC123"
    assert submitted["agent_mode"] == "documentos"
    assert submitted["conversation_id"] == "abcdef123456"


@pytest.mark.parametrize(("message", "expected_mode"), [
    ("Olá celsius, tudo bem?", "assistente"),
    ("Liste meu estoque", "estoque"),
])
def test_whatsapp_uses_real_coordinator_and_task_gate(service, message, expected_mode):
    from ai.task_runtime import handle_task_command

    service.settings.features.memory = False
    prompts = []
    task_calls = []

    def loop(prompt, **kwargs):
        task_calls.append(prompt)
        return "Execução simulada para verificar o encaminhamento.", []

    def responder(prompt, **kwargs):
        prompts.append(prompt)
        result = handle_task_command(prompt, settings=service.settings, loop=loop)
        return result if result is not None else "Olá! Como posso ajudar?"

    coordinator = ChatCoordinator(settings=service.settings, event_hub=EventHub(),
                                  responder=responder, ensure_model_ready=lambda _: None)
    service.coordinator = coordinator
    try:
        receive(service, message)
        service._tick()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = coordinator.get_job(service._active["job_id"])
            if job["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(.01)
        assert job["status"] == "completed"
        assert prompts[0]["agent_mode"] == expected_mode
        assert "nao executa tarefas" not in job["response"]
        if expected_mode == "assistente":
            assert not task_calls
            assert prompts[0]["pergunta"] == message
        else:
            assert len(task_calls) == 1
            assert task_calls[0]["agent_mode"] == expected_mode
        service._tick()
        assert service.test_calls[-1][1]["text"] == "Celsius\n" + job["response"]
    finally:
        coordinator.shutdown()


def test_legacy_whatsapp_task_prefix_does_not_turn_greeting_into_work(service):
    receive(service, "TAREFA: Boa tarde")
    service._tick()
    submitted = service.coordinator.submissions[0]
    assert submitted["message"] == "Boa tarde"
    assert submitted["agent_mode"] == "assistente"
