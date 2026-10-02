"""Personal menu selection must persist without changing another account's workspace."""

import pytest
from fastapi.testclient import TestClient

from core.modules import MODULE_INVENTORY, MODULE_KNOWLEDGE, MODULE_SETTINGS
from core.settings import Settings
from core.users import UserRole, UserService
from core.web_api import EventHub, create_app


def create_workspace_app(settings, user_service, event_hub=None):
    app = create_app(settings=settings, event_hub=event_hub)
    app.state.user_service = user_service
    return app


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(base_dir=tmp_path, data_dir=tmp_path / "data")
    settings.modules.set_enabled([MODULE_INVENTORY, MODULE_KNOWLEDGE])
    service = UserService(settings.data_dir)
    owner = service.register("owner@example.test", "test-password-123")
    teacher = service.register("teacher@example.test", "test-password-123")
    return settings, service, owner, teacher


def login(client, email):
    result = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "test-password-123",
        },
    )
    assert result.status_code == 200


def navigation_ids(client):
    result = client.get("/api/v1/navigation")
    assert result.status_code == 200
    return {item["id"] for item in result.json()["items"]}


def test_disable_is_personal_and_survives_restart(workspace):
    settings, service, owner, teacher = workspace
    app = create_workspace_app(settings=settings, user_service=service, event_hub=EventHub())
    with TestClient(app) as client:
        login(client, teacher.email)
        assert (
            client.patch(
                "/api/v1/settings/sidebar",
                json={
                    "enabled": [MODULE_KNOWLEDGE],
                    "show_conversations": False,
                },
            ).status_code
            == 200
        )
        assert MODULE_INVENTORY not in navigation_ids(client)
        assert MODULE_INVENTORY in settings.modules.enabled
        login(client, owner.email)
        assert MODULE_INVENTORY in navigation_ids(client)
        assert not client.get("/api/v1/navigation").json()["preferences"]
    reloaded = UserService(settings.data_dir)
    assert reloaded.get_user(teacher.id).sidebar_preferences["show_conversations"] is False
    app = create_workspace_app(settings=settings, user_service=reloaded, event_hub=EventHub())
    with TestClient(app) as client:
        login(client, teacher.email)
        assert MODULE_INVENTORY not in navigation_ids(client)
        assert MODULE_KNOWLEDGE in navigation_ids(client)


def test_hide_retains_activation_and_partial_changes_merge(workspace):
    settings, service, _, teacher = workspace
    app = create_workspace_app(settings=settings, user_service=service, event_hub=EventHub())
    with TestClient(app) as client:
        login(client, teacher.email)
        assert (
            client.patch(
                "/api/v1/settings/sidebar",
                json={
                    "sidebar_visible": {MODULE_INVENTORY: False},
                },
            ).status_code
            == 200
        )
        modules = {item["id"]: item for item in client.get("/api/v1/modules").json()["items"]}
        assert modules[MODULE_INVENTORY]["enabled"] is True
        assert modules[MODULE_INVENTORY]["in_navigation"] is False
        assert (
            client.patch(
                "/api/v1/settings/sidebar",
                json={
                    "sidebar_visible": {MODULE_KNOWLEDGE: False},
                    "show_memories": False,
                },
            ).status_code
            == 200
        )
        assert MODULE_INVENTORY not in navigation_ids(client)
        assert MODULE_KNOWLEDGE not in navigation_ids(client)
        assert (
            client.patch(
                "/api/v1/settings/sidebar",
                json={
                    "sidebar_visible": {MODULE_INVENTORY: True},
                },
            ).status_code
            == 200
        )
        assert MODULE_INVENTORY in navigation_ids(client)
        assert MODULE_KNOWLEDGE not in navigation_ids(client)


def test_essential_navigation_cannot_be_lost(workspace):
    settings, service, _, teacher = workspace
    app = create_workspace_app(settings=settings, user_service=service, event_hub=EventHub())
    with TestClient(app) as client:
        login(client, teacher.email)
        assert (
            client.patch(
                "/api/v1/settings/sidebar",
                json={
                    "enabled": [],
                    "sidebar_visible": {"chat": False, MODULE_SETTINGS: False},
                },
            ).status_code
            == 200
        )
        assert navigation_ids(client) == {"chat", MODULE_SETTINGS}


@pytest.mark.parametrize(
    "body",
    [
        {"enabled": ["unknown"]},
        {"sidebar_visible": {"unknown": False}},
        {"show_memories": "false"},
        {"sidebar_visible": {MODULE_INVENTORY: "false"}},
    ],
)
def test_invalid_preferences_do_not_change_account(workspace, body):
    settings, service, _, teacher = workspace
    with TestClient(create_workspace_app(settings=settings, user_service=service)) as client:
        login(client, teacher.email)
        assert client.patch("/api/v1/settings/sidebar", json=body).status_code == 422
        assert service.get_user(teacher.id).sidebar_preferences == {}


def test_requires_login_and_viewer_only_changes_own_menu(workspace):
    settings, service, _, teacher = workspace
    service.update_user(teacher.id, role=UserRole.VIEWER)
    with TestClient(create_workspace_app(settings=settings, user_service=service)) as client:
        assert client.patch("/api/v1/settings/sidebar", json={}).status_code == 401
        login(client, teacher.email)
        assert (
            client.patch("/api/v1/settings/sidebar", json={"show_memories": False}).status_code
            == 200
        )
        assert client.post("/api/v1/inventory", json={}).status_code == 403


def test_global_settings_preserve_modules_when_not_submitted(workspace):
    settings, service, owner, _ = workspace
    settings.modules.sidebar_visible[MODULE_INVENTORY] = False
    with TestClient(create_workspace_app(settings=settings, user_service=service)) as client:
        login(client, owner.email)
        payload = client.get("/api/v1/settings").json()
        assert payload["modules"][MODULE_INVENTORY]["sidebar_visible"] is False
        payload.pop("modules")
        assert client.put("/api/v1/settings", json=payload).status_code == 200
        assert settings.modules.is_enabled(MODULE_INVENTORY)
        assert settings.modules.sidebar_visible[MODULE_INVENTORY] is False
