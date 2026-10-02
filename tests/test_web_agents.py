"""Contract tests for the agentic HTTP surface (modes, policy, health, tasks)."""

from __future__ import annotations

import pytest
import time
from fastapi.testclient import TestClient

from core.agent_tasks import AgentTaskStore
from core.settings import Settings
from core.web_api import EventHub, create_app

API = "/api/v1"


class FakeMemoryService:
    def get_all(self):
        return []

    def add(self, text, origem=""):
        return {"texto": text, "origem": origem}


@pytest.fixture
def web_settings(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        logs_dir=tmp_path / "logs",
    )
    settings.mobile.pairing_token = "test-pairing-token"
    return settings


@pytest.fixture
def client(web_settings):
    app = create_app(
        settings=web_settings, event_hub=EventHub(), memory_service=FakeMemoryService()
    )
    with TestClient(app) as test_client:
        yield test_client


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-pairing-token"}


class TestModesEndpoint:
    def test_catalog_lists_the_six_modes(self, client):
        response = client.get(f"{API}/agents/modes", headers=_headers())
        assert response.status_code == 200
        payload = response.json()
        ids = {item["id"] for item in payload["items"]}
        assert {
            "assistente",
            "executor",
            "documentos",
            "estoque",
            "pesquisador",
            "desenvolvedor",
        } <= ids
        assert payload["default"] == "assistente"
        assert "waiting_confirmation" in payload["task_states"]

    def test_mode_detail_returns_clamped_limits(self, client):
        response = client.get(f"{API}/agents/modes/estoque", headers=_headers())
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"]["id"] == "estoque"
        assert payload["limits"]["max_steps"] >= 1
        assert payload["limits"]["max_seconds"] >= 1

    def test_unknown_mode_is_404(self, client):
        response = client.get(f"{API}/agents/modes/inventado", headers=_headers())
        assert response.status_code == 404

    def test_requires_authentication(self, client):
        assert client.get(f"{API}/agents/modes").status_code in (401, 403)


class TestToolPolicyEndpoint:
    def test_policy_is_exposed_for_every_tool(self, client):
        payload = client.get(f"{API}/agents/tools", headers=_headers()).json()
        by_tool = {item["tool"]: item for item in payload["items"]}
        assert by_tool["listar_estoque"]["requires_confirmation"] is False
        assert by_tool["saida_estoque"]["requires_confirmation"] is True
        assert by_tool["pesquisar_web"]["requires_confirmation"] is False
        assert all("risk_label" in item for item in payload["items"])


class TestHealthEndpoint:
    def test_health_never_raises_even_without_a_server(self, client):
        response = client.get(f"{API}/agents/health", headers=_headers())
        assert response.status_code == 200
        decision = response.json()["decision"]
        assert decision["state"] in {"off", "available", "unavailable"}
        assert "detail" in decision


class TestTasksEndpoint:
    def test_scope_is_required(self, client):
        assert client.get(f"{API}/agents/tasks", headers=_headers()).status_code == 400

    def test_empty_task_list_for_a_fresh_conversation(self, client):
        response = client.get(
            f"{API}/agents/tasks", params={"scope": "conversa-inexistente"}, headers=_headers()
        )
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_persisted_task_is_listed_with_the_shared_vocabulary(self, client, web_settings):
        from core.agent_tasks import AgentTaskStore

        store = AgentTaskStore(web_settings.data_dir / "agent_tasks.db")
        store.create("conversa-1", {"pergunta": "confira o estoque"}, mode="estoque")

        payload = client.get(
            f"{API}/agents/tasks", params={"scope": "conversa-1"}, headers=_headers()
        ).json()
        assert len(payload["items"]) == 1
        item = payload["items"][0]
        assert item["mode"] == "estoque"
        assert item["status"] in {
            "created",
            "planning",
            "waiting_confirmation",
            "running",
            "paused",
            "cancelled",
            "failed",
            "completed",
        }


class TestModeSelectionEndpoint:
    def test_selecting_a_mode_publishes_an_event(self, client):
        response = client.post(
            f"{API}/agents/mode?scope=conversa-1",
            json={"mode": "pesquisador"},
            headers=_headers(),
        )
        assert response.status_code == 200
        assert response.json()["mode"] == "pesquisador"

    def test_selecting_an_unknown_mode_is_rejected(self, client):
        response = client.post(
            f"{API}/agents/mode?scope=conversa-1",
            json={"mode": "nao-existe"},
            headers=_headers(),
        )
        assert response.status_code == 400

    def test_scope_is_required(self, client):
        response = client.post(f"{API}/agents/mode", json={"mode": "estoque"}, headers=_headers())
        assert response.status_code == 400


class TestTaskDetailEndpoint:
    def test_task_detail_returns_full_info(self, client, web_settings):
        store = AgentTaskStore(web_settings.data_dir / "agent_tasks.db")
        task = store.create("conversa-1", {"pergunta": "analise o codigo"}, mode="executor")
        task_id = task["id"]

        response = client.get(
            f"{API}/agents/tasks/{task_id}", params={"scope": "conversa-1"}, headers=_headers()
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["task"]["id"] == task_id
        assert payload["task"]["mode"] == "executor"
        assert payload["task"]["objective"] == "analise o codigo"
        assert "plan" in payload["task"]
        assert "steps" in payload["task"]

    def test_task_detail_404_for_unknown(self, client):
        response = client.get(
            f"{API}/agents/tasks/unknown123", params={"scope": "conversa-1"}, headers=_headers()
        )
        assert response.status_code == 404

    def test_task_plan_endpoint(self, client, web_settings):
        store = AgentTaskStore(web_settings.data_dir / "agent_tasks.db")
        task = store.create("conversa-1", {"pergunta": "faça o relatorio"}, mode="executor")
        task_id = task["id"]

        response = client.get(
            f"{API}/agents/tasks/{task_id}/plan", params={"scope": "conversa-1"}, headers=_headers()
        )
        assert response.status_code == 200
        assert "plan" in response.json()

    def test_task_steps_endpoint(self, client, web_settings):
        store = AgentTaskStore(web_settings.data_dir / "agent_tasks.db")
        task = store.create("conversa-1", {"pergunta": "teste"}, mode="executor")
        task_id = task["id"]

        response = client.get(
            f"{API}/agents/tasks/{task_id}/steps",
            params={"scope": "conversa-1"},
            headers=_headers(),
        )
        assert response.status_code == 200
        payload = response.json()
        assert "steps" in payload
        assert "current_step_index" in payload


class TestTaskConfirmEndpoint:
    def test_confirm_requires_approval_code(self, client):
        response = client.post(
            f"{API}/agents/tasks/abc123/confirm",
            json={},
            params={"scope": "conversa-1"},
            headers=_headers(),
        )
        assert response.status_code == 422  # validation error

    def test_confirm_404_for_nonexistent(self, client):
        response = client.post(
            f"{API}/agents/tasks/abc123/confirm",
            json={"approval_code": "ABC123"},
            params={"scope": "conversa-1"},
            headers=_headers(),
        )
        assert response.status_code == 404


class TestTaskCancelEndpoint:
    def test_cancel_requires_scope(self, client):
        response = client.post(f"{API}/agents/tasks/abc123/cancel", headers=_headers())
        assert response.status_code == 400

    def test_cancel_404_for_nonexistent(self, client):
        response = client.post(
            f"{API}/agents/tasks/abc123/cancel",
            params={"scope": "conversa-1"},
            headers=_headers(),
        )
        assert response.status_code == 404

    def test_cancel_marks_task_cancelled(self, client, web_settings):
        store = AgentTaskStore(web_settings.data_dir / "agent_tasks.db")
        task = store.create("conversa-1", {"pergunta": "cancelar isso"}, mode="executor")
        task_id = task["id"]

        response = client.post(
            f"{API}/agents/tasks/{task_id}/cancel",
            params={"scope": "conversa-1"},
            headers=_headers(),
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Verify task is cancelled
        task_check = store.get(task_id, "conversa-1")
        assert task_check["status"] == "cancelled"


class TestTaskHistoryEndpoint:
    def test_history_returns_execution_log(self, client, web_settings):
        store = AgentTaskStore(web_settings.data_dir / "agent_tasks.db")
        task = store.create("conversa-1", {"pergunta": "historico"}, mode="executor")
        task_id = task["id"]

        response = client.get(
            f"{API}/agents/tasks/{task_id}/history",
            params={"scope": "conversa-1"},
            headers=_headers(),
        )
        assert response.status_code == 200
        payload = response.json()
        assert "history" in payload
        assert isinstance(payload["history"], list)


class TestCurrentModeEndpoint:
    def test_current_mode_defaults_to_assistente(self, client):
        response = client.get(
            f"{API}/agents/mode/current", params={"scope": "nova-conversa"}, headers=_headers()
        )
        assert response.status_code == 200
        assert response.json()["mode"] == "assistente"

    def test_current_mode_from_latest_task(self, client, web_settings):
        store = AgentTaskStore(web_settings.data_dir / "agent_tasks.db")
        store.create("conversa-1", {"pergunta": "modo estoque"}, mode="estoque")

        response = client.get(
            f"{API}/agents/mode/current", params={"scope": "conversa-1"}, headers=_headers()
        )
        assert response.status_code == 200
        assert response.json()["mode"] == "estoque"
