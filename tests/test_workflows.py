"""Tests for quotes, reports, cases and deadlines shared by web and desktop."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from core.business_records import BusinessRecordService
from core.modules import (
    MODULE_CASES_DEADLINES,
    MODULE_CHAT,
    MODULE_QUOTES,
    MODULE_REPORTS,
    MODULE_SETTINGS,
)
from core.settings import Settings
from core.web_api import EventHub, create_app
from core.workflows import BusinessWorkflowService, WorkflowError


class FakeOperations:
    def list_inventory(self):
        return [
            {
                "name": "Filtro",
                "quantity": 2,
                "health": "Critico",
                "needs_restock": True,
            }
        ]


class FakeRelationships:
    def list_customers(self):
        return [{"name": "Cliente A", "status": "Ativo"}]

    def list_suppliers(self):
        return [{"name": "Fornecedor A", "status": "Preferencial"}]


@pytest.fixture
def workflow_context(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        logs_dir=tmp_path / "logs",
    )
    settings.mobile.pairing_token = "workflow-token"
    settings.modules.set_enabled(
        [
            MODULE_CHAT,
            MODULE_QUOTES,
            MODULE_REPORTS,
            MODULE_CASES_DEADLINES,
            MODULE_SETTINGS,
        ]
    )
    records = BusinessRecordService(data_file=tmp_path / "business_records.json", settings=settings)
    service = BusinessWorkflowService(
        settings=settings,
        record_service=records,
        operations_service=FakeOperations(),
        relationship_service=FakeRelationships(),
        event_hub=EventHub(),
        reports_dir=tmp_path / "reports",
    )
    return settings, records, service


def _headers():
    return {"Authorization": "Bearer workflow-token"}


class TestBusinessWorkflowService:
    def test_quote_numbering_values_and_duplicate_protection(self, workflow_context):
        _settings, _records, service = workflow_context
        first = service.save_quote(
            {"titulo": "Revisao geral", "cliente": "Cliente A", "valor": "1.250,50"}
        )
        second = service.save_quote({"titulo": "Troca de pneus", "valor": "500"})

        assert first["number"].endswith("0001")
        assert first["value_number"] == 1250.5
        assert second["number"].endswith("0002")
        with pytest.raises(WorkflowError, match="Ja existe"):
            service.save_quote({"titulo": "Duplicado", "numero": first["number"]})

    def test_case_flags_overdue_and_due_soon(self, workflow_context):
        _settings, _records, service = workflow_context
        overdue = service.save_case(
            {
                "processo": "Processo 100",
                "prazo": (date.today() - timedelta(days=2)).isoformat(),
                "prioridade": "Critica",
            }
        )
        due_soon = service.save_case(
            {
                "processo": "Renovacao",
                "prazo": (date.today() + timedelta(days=3)).isoformat(),
            }
        )

        assert overdue["overdue"] is True
        assert due_soon["due_soon"] is True
        assert "ATRASADO" in service.format_cases()

    def test_generates_local_report_and_removes_file(self, workflow_context):
        _settings, records, service = workflow_context
        service.save_quote({"titulo": "Aprovado", "valor": "1000", "status": "Aprovado"})
        report = service.generate_report(
            {
                "titulo": "Resumo executivo",
                "tipo": "Executivo",
                "fonte_dados": "Executivo",
                "formato": "md",
            }
        )
        path = service.report_file(report["id"])

        assert path.exists()
        assert "Gerado localmente" in path.read_text(encoding="utf-8")
        assert report["downloadable"] is True
        assert records.get(report["id"]).module_id == MODULE_REPORTS
        assert service.delete_report(report["id"]) is True
        assert not path.exists()


class TestWorkflowWebAPI:
    def test_workflow_endpoints_share_local_service(self, workflow_context):
        settings, _records, service = workflow_context
        app = create_app(settings=settings, event_hub=EventHub(), workflow_service=service)
        with TestClient(app) as client:
            quote = client.post(
                "/api/v1/quotes",
                headers=_headers(),
                json={"title": "Proposta web", "customer": "Cliente A", "value": "750"},
            )
            case = client.post(
                "/api/v1/cases-deadlines",
                headers=_headers(),
                json={"title": "Prazo contratual", "priority": "Alta"},
            )
            report = client.post(
                "/api/v1/reports/generate",
                headers=_headers(),
                json={
                    "title": "Relatorio web",
                    "report_type": "Executivo",
                    "source": "Executivo",
                    "output_format": "md",
                },
            )
            report_id = report.json()["item"]["id"]
            download = client.get(
                f"/api/v1/reports/{report_id}/download",
                headers=_headers(),
            )

        assert quote.status_code == 201
        assert case.status_code == 201
        assert case.json()["local_only"] is True
        assert report.status_code == 201
        assert download.status_code == 200
        assert b"Relatorio web" in download.content
        assert b"Estoque" in download.content

    def test_generates_multiline_pdf_through_web_api(self, workflow_context):
        settings, _records, service = workflow_context
        app = create_app(settings=settings, event_hub=EventHub(), workflow_service=service)
        with TestClient(app) as client:
            report = client.post(
                "/api/v1/reports/generate",
                headers=_headers(),
                json={
                    "title": "Relatorio executivo PDF",
                    "report_type": "Executivo",
                    "source": "Executivo",
                    "output_format": "pdf",
                },
            )
            assert report.status_code == 201, report.text
            item = report.json()["item"]
            download = client.get(item["download_url"], headers=_headers())

        assert download.status_code == 200
        assert download.content.startswith(b"%PDF")
