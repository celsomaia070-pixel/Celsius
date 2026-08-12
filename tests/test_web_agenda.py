"""Contract tests for the web agenda migration."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from core.agenda import AgendaService
from core.business_records import BusinessRecordService
from core.modules import MODULE_AGENDA, MODULE_CHAT, MODULE_SETTINGS
from core.settings import Settings
from core.web_api import EventHub, create_app


@pytest.fixture
def agenda_client(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        logs_dir=tmp_path / "logs",
    )
    settings.mobile.pairing_token = "agenda-token"
    settings.modules.set_enabled([MODULE_CHAT, MODULE_AGENDA, MODULE_SETTINGS])
    records = BusinessRecordService(
        data_file=tmp_path / "business_records.json",
        settings=settings,
    )
    agenda = AgendaService(record_service=records)
    app = create_app(settings=settings, event_hub=EventHub(), agenda_service=agenda)
    with TestClient(app) as client:
        yield client


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer agenda-token"}


class TestWebAgenda:
    def test_creates_lists_and_updates_shared_agenda_record(self, agenda_client):
        created = agenda_client.post(
            "/api/v1/agenda",
            headers=_headers(),
            json={
                "title": "Reuniao comercial",
                "event_type": "Reuniao",
                "starts_at": "2026-08-06T14:30",
                "customer": "Cliente A",
                "reminder_minutes": 30,
            },
        )
        event_id = created.json()["event"]["id"]
        listed = agenda_client.get("/api/v1/agenda", headers=_headers())
        updated = agenda_client.patch(
            f"/api/v1/agenda/{event_id}",
            headers=_headers(),
            json={"status": "Confirmado", "responsible": "Celso"},
        )

        assert created.status_code == 201
        assert listed.json()["items"][0]["customer"] == "Cliente A"
        assert updated.json()["event"]["status"] == "Confirmado"
        assert updated.json()["event"]["responsible"] == "Celso"

    def test_rejects_invalid_date_and_unknown_record(self, agenda_client):
        invalid = agenda_client.post(
            "/api/v1/agenda",
            headers=_headers(),
            json={"title": "Data ruim", "starts_at": "amanha talvez"},
        )
        missing = agenda_client.patch(
            "/api/v1/agenda/inexistente",
            headers=_headers(),
            json={"status": "Concluido"},
        )

        assert invalid.status_code == 422
        assert missing.status_code == 404

    def test_due_reminder_requires_acknowledgement(self, agenda_client):
        starts_at = datetime.now() + timedelta(minutes=5)
        created = agenda_client.post(
            "/api/v1/agenda",
            headers=_headers(),
            json={
                "title": "Ligar para fornecedor",
                "starts_at": starts_at.isoformat(timespec="minutes"),
                "reminder_minutes": 15,
            },
        )
        event_id = created.json()["event"]["id"]

        first_due = agenda_client.get("/api/v1/agenda/reminders/due", headers=_headers())
        acknowledged = agenda_client.post(
            f"/api/v1/agenda/{event_id}/acknowledge",
            headers=_headers(),
        )
        second_due = agenda_client.get("/api/v1/agenda/reminders/due", headers=_headers())

        assert [item["id"] for item in first_due.json()["items"]] == [event_id]
        assert acknowledged.status_code == 200
        assert second_due.json()["items"] == []

    def test_deletes_agenda_record(self, agenda_client):
        created = agenda_client.post(
            "/api/v1/agenda",
            headers=_headers(),
            json={"title": "Cancelar depois", "starts_at": "2026-08-10T09:00"},
        )
        event_id = created.json()["event"]["id"]

        deleted = agenda_client.delete(f"/api/v1/agenda/{event_id}", headers=_headers())
        listed = agenda_client.get("/api/v1/agenda", headers=_headers())

        assert deleted.json()["deleted"] == event_id
        assert listed.json()["items"] == []
