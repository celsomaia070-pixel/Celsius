"""Contract tests for the first phase of the local web migration."""

import asyncio
import base64
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.modules import MODULE_CHAT, MODULE_INVENTORY, MODULE_SETTINGS
from core.config import get_model_by_id
from core.settings import Settings
from core.web_api import EventHub, create_app


@pytest.fixture
def web_settings(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        logs_dir=tmp_path / "logs",
    )
    settings.mobile.pairing_token = "test-pairing-token"
    settings.customer.company_name = "Empresa Teste"
    settings.customer.company_sector = "Comercio"
    settings.modules.set_enabled([MODULE_CHAT, MODULE_INVENTORY, MODULE_SETTINGS])
    return settings


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-pairing-token"}


class FakeMemoryService:
    def __init__(self):
        self.items = []

    def get_all(self):
        return list(self.items)

    def add(self, text):
        item = {"texto": text, "data": "05/08/2026"}
        self.items.append(item)
        return item

    def search(self, _query):
        return [item["texto"] for item in self.items]


class FakeTTSProvider:
    async def synthesize(self, text):
        return f"audio:{text}".encode()


def _wait_for_job(client: TestClient, job_id: str) -> dict:
    for _attempt in range(100):
        response = client.get(f"/api/v1/chat/jobs/{job_id}", headers=_headers())
        job = response.json()["job"]
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("A tarefa HTTP de chat nao terminou.")


class TestWebApi:
    def test_lan_mode_does_not_publish_api_documentation(self, web_settings):
        with TestClient(
            create_app(
                settings=web_settings,
                event_hub=EventHub(),
                lan_access_enabled=True,
            )
        ) as client:
            docs = client.get("/api/docs")
            schema = client.get("/api/v1/openapi.json")

        assert docs.status_code == 404
        assert schema.status_code == 404

    def test_health_is_local_and_versioned(self, web_settings):
        with TestClient(create_app(settings=web_settings, event_hub=EventHub())) as client:
            response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["processing_mode"] == "local"
        assert response.json()["api_version"] == "v1"

    def test_openapi_schema_is_available_with_bearer_auth(self, web_settings):
        with TestClient(create_app(settings=web_settings, event_hub=EventHub())) as client:
            response = client.get("/api/v1/openapi.json")

        assert response.status_code == 200
        security_schemes = response.json()["components"]["securitySchemes"]
        assert any(scheme["type"] == "http" for scheme in security_schemes.values())
        assert "/api/v1/chat/messages" in response.json()["paths"]

    def test_web_shell_pairs_local_browser_without_exposing_token(self, web_settings):
        app = create_app(settings=web_settings, event_hub=EventHub())
        with TestClient(app) as client:
            page = client.get("/app?token=test-pairing-token")
            session = client.get("/api/v1/session")
            stylesheet = client.get("/app/assets/app.css")
            script = client.get("/app/assets/app.js")

        assert page.status_code == 200
        assert "Celsius Project AI" in page.text
        assert "test-pairing-token" not in page.text
        assert session.status_code == 200
        assert stylesheet.status_code == 200
        assert script.status_code == 200
        assert 'id="memory-button"' in page.text
        assert 'id="model-select"' in page.text
        assert 'id="voice-toggle"' in page.text
        assert 'id="jarvis-toggle"' in page.text
        assert 'id="mobile-pair-button"' in page.text
        assert 'id="voice-input-button"' in page.text
        assert 'data-theme-option="dark"' in page.text
        assert 'data-theme-option="green"' in page.text
        assert ">GREEN<" in page.text
        assert ">DARK<" in page.text
        assert 'body[data-theme="green"]' in stylesheet.text
        assert 'body[data-theme="dark"]' in stylesheet.text
        assert "--page: #050505" in stylesheet.text
        assert "celsius-theme-v2" in script.text
        assert "celsius-jarvis-position" in script.text
        assert "conversation-delete" in script.text
        assert 'api("/voice/transcribe"' in script.text
        assert "startVoiceInput" in script.text
        assert "speechSynthesisChain" in script.text
        assert "speechPlaybackChain" in script.text
        assert "smoothSpeechBoundary" in script.text
        assert ".then(() => playSpeechBlob" in script.text
        assert "state.speechChain = state.speechChain.then" not in script.text

    def test_private_routes_require_pairing(self, web_settings):
        with TestClient(create_app(settings=web_settings, event_hub=EventHub())) as client:
            response = client.get("/api/v1/modules")

        assert response.status_code == 401
        assert response.json()["ok"] is False

    def test_mobile_pairing_exposes_lan_qr_to_authenticated_browser(
        self, web_settings, monkeypatch
    ):
        monkeypatch.setattr("core.web_api.mobile.get_lan_ip", lambda: "192.168.1.50")
        app = create_app(
            settings=web_settings,
            event_hub=EventHub(),
            lan_access_enabled=True,
            public_scheme="https",
            public_port=8790,
        )
        with TestClient(app) as client:
            response = client.get("/api/v1/mobile/pairing", headers=_headers())

        payload = response.json()
        assert response.status_code == 200
        assert payload["url"] == ("https://192.168.1.50:8790/app?token=test-pairing-token")
        assert payload["qr_code"].startswith("data:image/png;base64,")
        assert payload["lan_access_enabled"] is True
        assert payload["external_service"] is False
        assert payload["https"] is True
        assert payload["interface"] == "desktop-responsive"
        assert payload["voice_input"] is True

    def test_modules_expose_configuration_without_hiding_catalog(self, web_settings):
        with TestClient(create_app(settings=web_settings, event_hub=EventHub())) as client:
            response = client.get("/api/v1/modules", headers=_headers())

        items = {item["id"]: item for item in response.json()["items"]}
        assert response.status_code == 200
        assert items[MODULE_CHAT]["mandatory"] is True
        assert items[MODULE_INVENTORY]["enabled"] is True
        assert items["suppliers"]["enabled"] is False

    def test_navigation_contains_only_enabled_visible_ready_modules(self, web_settings):
        web_settings.modules.sidebar_visible[MODULE_INVENTORY] = False
        with TestClient(create_app(settings=web_settings, event_hub=EventHub())) as client:
            response = client.get("/api/v1/navigation", headers=_headers())

        ids = {item["id"] for item in response.json()["items"]}
        assert ids == {MODULE_CHAT, MODULE_SETTINGS}

    def test_session_uses_existing_company_profile(self, web_settings):
        with TestClient(create_app(settings=web_settings, event_hub=EventHub())) as client:
            response = client.get("/api/v1/session?token=test-pairing-token")

        assert response.status_code == 200
        assert response.json()["company"]["name"] == "Empresa Teste"
        assert response.json()["assistant"]["name"] == "Celsius"

    def test_memories_are_shared_through_authenticated_contract(self, web_settings):
        memory_service = FakeMemoryService()
        app = create_app(
            settings=web_settings,
            event_hub=EventHub(),
            memory_service=memory_service,
        )
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/memories",
                headers=_headers(),
                json={"text": "O usuario prefere relatorios detalhados"},
            )
            listed = client.get("/api/v1/memories", headers=_headers())
            duplicate = client.post(
                "/api/v1/memories",
                headers=_headers(),
                json={"text": "O usuario prefere relatorios detalhados"},
            )

        assert created.status_code == 201
        assert listed.json()["items"][0]["text"].startswith("O usuario")
        assert duplicate.status_code == 409

    def test_models_report_only_ready_files_as_selectable(self, web_settings):
        model = get_model_by_id("qwen3-4b-q4km")
        web_settings.resources_dir.mkdir(parents=True)
        (web_settings.resources_dir / model.filename).write_bytes(b"gguf")
        with TestClient(create_app(settings=web_settings, event_hub=EventHub())) as client:
            response = client.get("/api/v1/models", headers=_headers())

        items = {item["id"]: item for item in response.json()["items"]}
        assert response.status_code == 200
        assert response.json()["automatic_routing"] is True
        assert items[model.id]["ready"] is True
        assert all(item["ready"] <= item["installed"] for item in items.values())

    def test_voice_exposes_external_dependency_and_returns_audio(self, web_settings):
        app = create_app(
            settings=web_settings,
            event_hub=EventHub(),
            tts_provider=FakeTTSProvider(),
        )
        with TestClient(app) as client:
            capabilities = client.get("/api/v1/voice", headers=_headers())
            audio = client.post(
                "/api/v1/voice/synthesize",
                headers=_headers(),
                json={"text": "Ola"},
            )

        assert capabilities.json()["requires_internet"] is True
        assert capabilities.json()["jarvis"]["available"] is True
        assert audio.status_code == 200
        assert audio.headers["content-type"] == "audio/mpeg"
        assert audio.content == b"audio:Ola"

    def test_voice_question_is_transcribed_locally(self, web_settings, monkeypatch):
        captured = {}

        def fake_transcribe(audio, *, model_name):
            captured.update(audio=audio, model_name=model_name)
            return "gere um relatorio do estoque"

        monkeypatch.setattr(
            "core.mobile_voice.transcribe_mobile_wav",
            fake_transcribe,
        )
        app = create_app(settings=web_settings, event_hub=EventHub())
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/voice/transcribe",
                headers=_headers(),
                json={
                    "audio_base64": base64.b64encode(b"wav-local").decode("ascii"),
                    "mime_type": "audio/wav",
                },
            )

        assert response.status_code == 200
        assert response.json()["transcript"] == "gere um relatorio do estoque"
        assert response.json()["processing_mode"] == "local"
        assert captured == {"audio": b"wav-local", "model_name": "small"}

    def test_websocket_requires_pairing_and_answers_ping(self, web_settings):
        app = create_app(settings=web_settings, event_hub=EventHub())
        with (
            TestClient(app) as client,
            client.websocket_connect("/api/v1/events?token=test-pairing-token") as websocket,
        ):
            assert websocket.receive_json()["type"] == "system.connected"
            websocket.send_json({"type": "ping", "payload": {"sequence": 7}})
            response = websocket.receive_json()

        assert response == {"type": "pong", "payload": {"sequence": 7}}

    def test_websocket_rejects_client_without_pairing(self, web_settings):
        app = create_app(settings=web_settings, event_hub=EventHub())
        with (
            TestClient(app) as client,
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect("/api/v1/events"),
        ):
            pass

    def test_chat_message_runs_as_job_and_persists_conversation(self, web_settings, tmp_path):
        web_settings.features.memory = False

        def responder(_prompt, *, fn_chunk, **_kwargs):
            fn_chunk("Resposta via API")
            return "Resposta via API"

        hub = EventHub()
        coordinator = ChatCoordinator(
            settings=web_settings,
            event_hub=hub,
            conversation_manager=ConversationManager(tmp_path / "conversations"),
            responder=responder,
            ensure_model_ready=lambda _status: None,
        )
        app = create_app(
            settings=web_settings,
            event_hub=hub,
            chat_coordinator=coordinator,
        )
        with TestClient(app) as client:
            accepted = client.post(
                "/api/v1/chat/messages",
                headers=_headers(),
                json={"message": "Ola pela web"},
            )
            job = _wait_for_job(client, accepted.json()["job"]["id"])
            conversation = client.get(
                f"/api/v1/chat/conversations/{job['conversation_id']}",
                headers=_headers(),
            ).json()["conversation"]

        assert accepted.status_code == 202
        assert job["status"] == "completed"
        assert conversation["messages"][-1]["content"] == "Resposta via API"

    def test_chat_conversation_can_be_deleted(self, web_settings, tmp_path):
        manager = ConversationManager(tmp_path / "conversations")
        conversation = manager.create("Conversa descartavel")
        coordinator = ChatCoordinator(
            settings=web_settings,
            event_hub=EventHub(),
            conversation_manager=manager,
            responder=lambda _prompt, **_kwargs: "ok",
            ensure_model_ready=lambda _status: None,
        )
        app = create_app(
            settings=web_settings,
            event_hub=EventHub(),
            chat_coordinator=coordinator,
        )
        with TestClient(app) as client:
            deleted = client.delete(
                f"/api/v1/chat/conversations/{conversation['id']}",
                headers=_headers(),
            )
            missing = client.get(
                f"/api/v1/chat/conversations/{conversation['id']}",
                headers=_headers(),
            )

        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == conversation["id"]
        assert missing.status_code == 404

    def test_chat_upload_reaches_document_prompt(self, web_settings, tmp_path):
        web_settings.features.memory = False
        captured = {}

        def responder(prompt, **_kwargs):
            captured.update(prompt)
            return "Arquivo recebido"

        hub = EventHub()
        coordinator = ChatCoordinator(
            settings=web_settings,
            event_hub=hub,
            conversation_manager=ConversationManager(tmp_path / "conversations"),
            responder=responder,
            ensure_model_ready=lambda _status: None,
        )
        app = create_app(
            settings=web_settings,
            event_hub=hub,
            chat_coordinator=coordinator,
        )
        with TestClient(app) as client:
            upload = client.post(
                "/api/v1/chat/attachments",
                headers={**_headers(), "X-Celsius-Filename": "dados.txt"},
                content=b"receita mensal 5000",
            )
            attachment_id = upload.json()["attachment"]["id"]
            accepted = client.post(
                "/api/v1/chat/messages",
                headers=_headers(),
                json={"message": "Analise", "attachment_ids": [attachment_id]},
            )
            job = _wait_for_job(client, accepted.json()["job"]["id"])

        assert upload.status_code == 201
        assert job["status"] == "completed"
        assert "receita mensal 5000" in captured["documento"]


@pytest.mark.asyncio
async def test_event_hub_distributes_events():
    hub = EventHub()
    async with hub.subscribe() as queue:
        published = hub.publish("agenda.reminder", {"title": "Reuniao"})
        received = await asyncio.wait_for(queue.get(), timeout=1)

    assert received == published
    assert received["payload"]["title"] == "Reuniao"


from core.chat_service import ChatCoordinator
from core.conversations import ConversationManager
