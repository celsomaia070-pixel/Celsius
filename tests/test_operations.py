"""Tests for shared inventory and commercial catalog management."""

import pytest
from fastapi.testclient import TestClient

from core.business_records import BusinessRecordService
from core.inventory import InventoryService, ItemEstoque, StockStatus
from core.modules import (
    MODULE_CHAT,
    MODULE_INVENTORY,
    MODULE_PRODUCTS_SERVICES,
    MODULE_SETTINGS,
)
from core.operations import BusinessOperationsService, OperationsError
from core.settings import Settings
from core.web_api import EventHub, create_app


@pytest.fixture
def operations_context(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        logs_dir=tmp_path / "logs",
    )
    settings.mobile.pairing_token = "operations-token"
    settings.modules.set_enabled(
        [MODULE_CHAT, MODULE_INVENTORY, MODULE_PRODUCTS_SERVICES, MODULE_SETTINGS]
    )
    inventory = InventoryService(settings=settings, data_file=tmp_path / "inventory.json")
    records = BusinessRecordService(
        data_file=tmp_path / "business_records.json",
        settings=settings,
    )
    service = BusinessOperationsService(
        settings=settings,
        inventory_service=inventory,
        record_service=records,
    )
    return settings, service, inventory, records


def _headers():
    return {"Authorization": "Bearer operations-token"}


class TestBusinessOperationsService:
    def test_stock_health_is_derived_from_quantity_limits(self):
        item = ItemEstoque("1", "Alicate", "Ferramentas", 52, 2, 10)

        assert item.stock_status == StockStatus.EXCESSO
        assert item.excedeu_max is True

        item.quantidade = 0
        assert item.stock_status == StockStatus.SEM_ESTOQUE

    def test_inventory_instances_merge_sequential_changes(self, tmp_path):
        path = tmp_path / "inventory.json"
        first = InventoryService(data_file=path)
        second = InventoryService(data_file=path)

        created = first.adicionar_item("Filtro", "Pecas", 5, 1, 10)
        second.entrada(created.id, 2)
        first.adicionar_item("Correia", "Pecas", 3, 1, 8)

        reloaded = InventoryService(data_file=path)
        assert reloaded.get_item(created.id).quantidade == 7
        assert {item.nome for item in reloaded.get_all_items()} == {"Filtro", "Correia"}

    def test_inventory_crud_and_movements_share_desktop_service(self, operations_context):
        _settings, service, inventory, _records = operations_context
        created = service.save_inventory_item(
            {
                "name": "Filtro de oleo",
                "category": "Filtros",
                "quantity": 10,
                "minimum": 3,
                "maximum": 20,
            }
        )
        movement = service.move_inventory(created["id"], "saida", 8)
        updated = service.save_inventory_item(
            {"name": "Filtro de oleo premium", "minimum": 4, "maximum": 20},
            created["id"],
        )

        assert inventory.get_item(created["id"]).quantidade == 2
        assert movement["new_quantity"] == 2
        assert updated["health"] == "Critico"
        assert service.list_movements(created["id"])[0]["type"] == "saida"
        assert service.delete_inventory_item(created["id"]) is True

    def test_rejects_duplicate_inventory_name(self, operations_context):
        _settings, service, _inventory, _records = operations_context
        service.save_inventory_item({"name": "Correia", "quantity": 2})

        with pytest.raises(OperationsError, match="Ja existe"):
            service.save_inventory_item({"name": "correia", "quantity": 1})

    def test_product_crud_uses_modular_business_records(self, operations_context):
        _settings, service, _inventory, records = operations_context
        created = service.save_product(
            {
                "codigo": "SRV-001",
                "nome": "Troca de oleo",
                "tipo": "Servico",
                "preco": "100,00",
                "custo": "40,00",
            }
        )
        updated = service.save_product({"status": "Pausado"}, created["id"])

        assert records.get(created["id"]).fields["codigo"] == "SRV-001"
        assert created["margin_percent"] == 60.0
        assert updated["status"] == "Pausado"
        assert "Troca de oleo" in service.format_products()

    def test_rejects_duplicate_product_code(self, operations_context):
        _settings, service, _inventory, _records = operations_context
        service.save_product({"codigo": "P-10", "nome": "Produto A"})

        with pytest.raises(OperationsError, match="Ja existe"):
            service.save_product({"codigo": "p-10", "nome": "Produto B"})


class TestWebOperations:
    def test_inventory_and_catalog_endpoints(self, operations_context):
        settings, service, inventory, records = operations_context
        app = create_app(
            settings=settings,
            event_hub=EventHub(),
            operations_service=service,
        )
        with TestClient(app) as client:
            inventory_response = client.post(
                "/api/v1/inventory",
                headers=_headers(),
                json={
                    "name": "Pneu 195/55",
                    "category": "Pneus",
                    "quantity": 4,
                    "minimum": 2,
                    "maximum": 12,
                },
            )
            item_id = inventory_response.json()["item"]["id"]
            movement_response = client.post(
                f"/api/v1/inventory/{item_id}/movements",
                headers=_headers(),
                json={"type": "entrada", "quantity": 2},
            )
            product_response = client.post(
                "/api/v1/products-services",
                headers=_headers(),
                json={"code": "PN-195", "name": "Pneu 195/55", "price": "450,00"},
            )
            products_response = client.get("/api/v1/products-services", headers=_headers())

        assert inventory_response.status_code == 201
        assert movement_response.json()["item"]["quantity"] == 6
        assert inventory.get_item(item_id).quantidade == 6
        assert product_response.status_code == 201
        assert products_response.json()["items"][0]["code"] == "PN-195"
        assert records.get(product_response.json()["item"]["id"]) is not None
