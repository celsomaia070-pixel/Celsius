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
            observacoes="Entrega em ate 3 dias.",
        )

        reloaded = SupplierService(data_file=data_file)
        suppliers = reloaded.list_all()

        assert len(suppliers) == 1
        assert suppliers[0].id == supplier.id
        assert suppliers[0].nome == "Auto Pecas Maia"
        assert suppliers[0].categoria == "Pecas"

    def test_update_delete_and_search_supplier(self, tmp_path):
        service = SupplierService(data_file=tmp_path / "suppliers.json")
        supplier = service.add("Distribuidora Central", categoria="Insumos")

        updated = service.update(
            supplier.id,
            nome="Distribuidora Central Ltda",
            contato="Ana",
            categoria="Material de escritorio",
        )

        assert updated is not None
        assert updated.contato == "Ana"
        assert service.search("escritorio")[0].id == supplier.id
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
