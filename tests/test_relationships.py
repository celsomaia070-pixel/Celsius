"""Tests for shared customer and supplier management."""

import pytest
from fastapi.testclient import TestClient

from core.business_records import BusinessRecordService
from core.modules import MODULE_CHAT, MODULE_CUSTOMERS, MODULE_SETTINGS, MODULE_SUPPLIERS
from core.relationships import RelationshipError, RelationshipService
from core.settings import Settings
from core.suppliers import SupplierService
from core.web_api import EventHub, create_app


@pytest.fixture
def relationship_context(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        logs_dir=tmp_path / "logs",
    )
    settings.mobile.pairing_token = "relationship-token"
    settings.modules.set_enabled([MODULE_CHAT, MODULE_CUSTOMERS, MODULE_SUPPLIERS, MODULE_SETTINGS])
    records = BusinessRecordService(
        data_file=tmp_path / "business_records.json",
        settings=settings,
    )
    suppliers = SupplierService(data_file=tmp_path / "suppliers.json", settings=settings)
    service = RelationshipService(
        settings=settings,
        record_service=records,
        supplier_service=suppliers,
    )
    return settings, service, suppliers


def _headers():
    return {"Authorization": "Bearer relationship-token"}


class TestRelationshipService:
    def test_customer_crud_uses_modular_business_records(self, relationship_context):
        _settings, service, _suppliers = relationship_context
        created = service.save_customer(
            {
                "nome": "Cliente Maia",
                "tipo": "Empresa",
                "documento": "12.345.678/0001-90",
                "telefone": "11999990000",
            }
        )
        updated = service.save_customer(
            {"status": "Em atendimento", "responsavel": "Celso"},
            created["id"],
        )

        assert service.list_customers("maia")[0]["phone"] == "11999990000"
        assert updated["status"] == "Em atendimento"
        assert updated["responsible"] == "Celso"
        assert service.delete_customer(created["id"]) is True
        assert service.list_customers() == []

    def test_supplier_crud_uses_existing_desktop_service(self, relationship_context):
        _settings, service, supplier_service = relationship_context
        created = service.save_supplier(
            {
                "nome": "Distribuidora Alfa",
                "categoria": "Pecas",
                "produtos": "Filtros e oleos",
                "lead_time_dias": "3",
            }
        )
        updated = service.save_supplier({"status": "Preferencial"}, created["id"])

        assert supplier_service.get(created["id"]).nome == "Distribuidora Alfa"
        assert service.list_suppliers("filtros")[0]["lead_time_days"] == "3"
        assert updated["status"] == "Preferencial"

    def test_duplicate_document_is_rejected(self, relationship_context):
        _settings, service, _suppliers = relationship_context
        service.save_customer({"nome": "Primeiro", "documento": "123.456.789-00"})

        with pytest.raises(RelationshipError, match="Ja existe"):
            service.save_customer({"nome": "Segundo", "documento": "12345678900"})

    def test_formats_local_relationships_for_llm(self, relationship_context):
        _settings, service, _suppliers = relationship_context
        service.save_customer({"nome": "Cliente A", "segmento": "Comercio"})
        service.save_supplier({"nome": "Fornecedor A", "produtos": "Embalagens"})

        assert "Cliente A" in service.format_customers()
        assert "Comercio" in service.format_customers()
        assert "Fornecedor A" in service.format_suppliers()
        assert "Embalagens" in service.format_suppliers()


class TestWebRelationships:
    def test_customer_and_supplier_endpoints_share_existing_services(self, relationship_context):
        settings, service, supplier_service = relationship_context
        app = create_app(
            settings=settings,
            event_hub=EventHub(),
            relationship_service=service,
        )
        with TestClient(app) as client:
            customer = client.post(
                "/api/v1/customers",
                headers=_headers(),
                json={"name": "Cliente Web", "customer_type": "Empresa"},
            )
            supplier = client.post(
                "/api/v1/suppliers",
                headers=_headers(),
                json={"name": "Fornecedor Web", "category": "Insumos"},
            )
            supplier_id = supplier.json()["item"]["id"]
            listed_customers = client.get("/api/v1/customers", headers=_headers())
            updated_supplier = client.patch(
                f"/api/v1/suppliers/{supplier_id}",
                headers=_headers(),
                json={"status": "Preferencial"},
            )

        assert customer.status_code == 201
        assert listed_customers.json()["items"][0]["name"] == "Cliente Web"
        assert updated_supplier.json()["item"]["status"] == "Preferencial"
        assert supplier_service.get(supplier_id).status == "Preferencial"
