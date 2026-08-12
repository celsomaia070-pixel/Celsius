"""Tests for supplier registry service."""

from core.suppliers import SupplierService


class TestSupplierService:
    def test_add_and_reload_supplier(self, tmp_path):
        data_file = tmp_path / "suppliers.json"
        service = SupplierService(data_file=data_file)

        supplier = service.add(
            nome="Auto Pecas Maia",
            contato="Celso",
            telefone="11999990000",
            email="compras@example.com",
            categoria="Pecas",
            documento="12.345.678/0001-90",
            produtos="Pastilhas de freio, filtros e oleos",
            prazo_pagamento="28 dias",
            lead_time_dias="3",
            status="Preferencial",
            observacoes="Entrega em ate 3 dias.",
        )

        reloaded = SupplierService(data_file=data_file)
        suppliers = reloaded.list_all()

        assert len(suppliers) == 1
        assert suppliers[0].id == supplier.id
        assert suppliers[0].nome == "Auto Pecas Maia"
        assert suppliers[0].categoria == "Pecas"
        assert suppliers[0].documento == "12.345.678/0001-90"
        assert suppliers[0].status == "Preferencial"

    def test_update_delete_and_search_supplier(self, tmp_path):
        service = SupplierService(data_file=tmp_path / "suppliers.json")
        supplier = service.add("Distribuidora Central", categoria="Insumos")

        updated = service.update(
            supplier.id,
            nome="Distribuidora Central Ltda",
            contato="Ana",
            categoria="Material de escritorio",
            produtos="Papel, toner e embalagens",
            status="Ativo",
        )

        assert updated is not None
        assert updated.contato == "Ana"
        assert service.search("escritorio")[0].id == supplier.id
        assert service.search("toner")[0].id == supplier.id
        assert service.delete(supplier.id) is True
        assert service.list_all() == []

    def test_supplier_name_is_required(self, tmp_path):
        service = SupplierService(data_file=tmp_path / "suppliers.json")

        try:
            service.add("   ")
        except ValueError as exc:
            assert "obrigatorio" in str(exc)
        else:
            raise AssertionError("Expected ValueError for empty supplier name.")
