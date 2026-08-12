"""Shared inventory and commercial catalog access for desktop, web and local AI."""

from __future__ import annotations

import threading
from decimal import Decimal, InvalidOperation
from typing import Any

from core.business_records import BusinessRecord, BusinessRecordService, get_business_record_service
from core.inventory import (
    ColunaKanban,
    InventoryService,
    ItemEstoque,
    Movimentacao,
    get_inventory_service,
)
from core.modules import MODULE_PRODUCTS_SERVICES
from core.settings import get_settings


class OperationsError(ValueError):
    """Raised when an inventory or catalog operation is invalid."""


class BusinessOperationsService:
    def __init__(
        self,
        *,
        settings=None,
        inventory_service: InventoryService | None = None,
        record_service: BusinessRecordService | None = None,
        event_hub=None,
    ):
        use_global_services = settings is None
        self.settings = settings or get_settings()
        if inventory_service is not None:
            self.inventory_service = inventory_service
        elif use_global_services:
            self.inventory_service = get_inventory_service()
        else:
            explicit_fields = getattr(self.settings, "model_fields_set", set())
            inventory_file = (
                self.settings.inventory_file
                if "inventory_file" in explicit_fields
                else self.settings.base_dir / "inventory.json"
            )
            self.inventory_service = InventoryService(
                settings=self.settings,
                data_file=inventory_file,
            )
        self.record_service = record_service or (
            get_business_record_service()
            if use_global_services
            else BusinessRecordService(settings=self.settings)
        )
        self.event_hub = event_hub
        self.inventory_service.add_listener(self._inventory_changed)

    def list_inventory(self, search: str = "") -> list[dict[str, Any]]:
        items = (
            self.inventory_service.buscar(search)
            if search.strip()
            else self.inventory_service.get_all_items()
        )
        return [self._inventory_item(item) for item in sorted(items, key=lambda item: item.nome)]

    def get_inventory_item(self, item_id: str) -> dict[str, Any]:
        return self._inventory_item(self._inventory_record(item_id))

    def save_inventory_item(
        self,
        values: dict[str, Any],
        item_id: str = "",
    ) -> dict[str, Any]:
        existing = self._inventory_record(item_id) if item_id else None
        name = str(values.get("name", existing.nome if existing else "")).strip()
        category = str(values.get("category", existing.categoria if existing else "Geral")).strip()
        if not name:
            raise OperationsError("Nome do item e obrigatorio.")
        self._ensure_unique_inventory_name(name, current_id=item_id)

        minimum = self._integer(values.get("minimum", existing.estoque_min if existing else 0))
        maximum = self._integer(values.get("maximum", existing.estoque_max if existing else 0))
        if minimum < 0 or maximum < 0:
            raise OperationsError("Estoques minimo e maximo nao podem ser negativos.")
        if maximum and minimum > maximum:
            raise OperationsError("Estoque minimo nao pode ser maior que o maximo.")

        if existing is None:
            quantity = self._integer(values.get("quantity", 0))
            if quantity < 0:
                raise OperationsError("Quantidade inicial nao pode ser negativa.")
            item = self.inventory_service.adicionar_item(
                nome=name,
                categoria=category or "Geral",
                quantidade=quantity,
                estoque_min=minimum,
                estoque_max=maximum,
            )
        else:
            item = self.inventory_service.editar_item(
                item_id,
                nome=name,
                categoria=category or "Geral",
                estoque_min=minimum,
                estoque_max=maximum,
            )
            if item is None:
                raise OperationsError("Item de estoque nao encontrado.")

        location = str(values.get("location", "")).strip()
        if location:
            try:
                column = ColunaKanban(location)
            except ValueError as exc:
                raise OperationsError("Localizacao de estoque invalida.") from exc
            self.inventory_service.mover_item(item.id, column)
            item = self._inventory_record(item.id)
        return self._inventory_item(item)

    def delete_inventory_item(self, item_id: str) -> bool:
        self._inventory_record(item_id)
        return self.inventory_service.remover_item(item_id)

    def move_inventory(self, item_id: str, movement_type: str, quantity: int) -> dict[str, Any]:
        self._inventory_record(item_id)
        amount = self._integer(quantity)
        if amount <= 0:
            raise OperationsError("A quantidade da movimentacao deve ser maior que zero.")
        if movement_type == "entrada":
            movement = self.inventory_service.entrada(item_id, amount)
        elif movement_type == "saida":
            movement = self.inventory_service.saida(item_id, amount)
        else:
            raise OperationsError("Tipo de movimentacao invalido.")
        if movement is None:
            raise OperationsError("Movimentacao invalida ou saldo insuficiente.")
        return self._movement_item(movement)

    def list_movements(self, item_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        movements = self.inventory_service.get_movimentacoes(item_id or None)
        safe_limit = max(1, min(self._integer(limit or 100), 200))
        return [self._movement_item(item) for item in reversed(movements[-safe_limit:])]

    def list_products(self, search: str = "") -> list[dict[str, Any]]:
        records = self.record_service.search(MODULE_PRODUCTS_SERVICES, search)
        return [self._product_item(record) for record in records]

    def get_product(self, product_id: str) -> dict[str, Any]:
        return self._product_item(self._product_record(product_id))

    def save_product(self, values: dict[str, Any], product_id: str = "") -> dict[str, Any]:
        existing = self._product_record(product_id) if product_id else None
        fields = dict(existing.fields) if existing else {}
        fields.update({key: str(value or "").strip() for key, value in values.items()})
        name = fields.get("nome", existing.title if existing else "").strip()
        if not name:
            raise OperationsError("Nome do produto ou servico e obrigatorio.")
        fields["nome"] = name
        fields["tipo"] = fields.get("tipo", "Produto") or "Produto"
        fields["status"] = fields.get("status", "Ativo") or "Ativo"
        self._ensure_unique_product_code(fields.get("codigo", ""), current_id=product_id)
        try:
            record = self.record_service.save_record(
                MODULE_PRODUCTS_SERVICES,
                name,
                fields,
                record_id=product_id,
            )
        except ValueError as exc:
            raise OperationsError(str(exc)) from exc
        item = self._product_item(record)
        self._publish(
            "catalog.changed",
            {
                "action": "updated" if product_id else "created",
                "item": item,
            },
        )
        return item

    def delete_product(self, product_id: str) -> bool:
        self._product_record(product_id)
        deleted = self.record_service.delete(product_id)
        if deleted:
            self._publish("catalog.changed", {"action": "deleted", "item_id": product_id})
        return deleted

    def format_products(self, search: str = "", limit: int = 50) -> str:
        items = self.list_products(search)[: max(1, min(self._integer(limit or 50), 200))]
        if not items:
            return "Nenhum produto ou servico encontrado no catalogo local."
        lines = [f"Produtos e servicos locais ({len(items)}):"]
        for item in items:
            details = [item["type"], item["status"]]
            if item["code"]:
                details.append(f"codigo: {item['code']}")
            if item["price"]:
                details.append(f"preco: {item['price']}")
            if item["category"]:
                details.append(f"categoria: {item['category']}")
            lines.append(f"- [{item['id']}] {item['name']} | {' | '.join(details)}")
        return "\n".join(lines)

    def _inventory_record(self, item_id: str) -> ItemEstoque:
        item = self.inventory_service.get_item(item_id)
        if item is None:
            raise OperationsError("Item de estoque nao encontrado.")
        return item

    def _product_record(self, product_id: str) -> BusinessRecord:
        record = self.record_service.get(product_id)
        if record is None or record.module_id != MODULE_PRODUCTS_SERVICES:
            raise OperationsError("Produto ou servico nao encontrado.")
        return record

    def _ensure_unique_inventory_name(self, name: str, *, current_id: str) -> None:
        normalized = name.casefold()
        for item in self.inventory_service.get_all_items():
            if item.nome.casefold() == normalized and item.id != current_id:
                raise OperationsError("Ja existe um item de estoque com este nome.")

    def _ensure_unique_product_code(self, code: str, *, current_id: str) -> None:
        normalized = code.strip().casefold()
        if not normalized:
            return
        for item in self.list_products():
            if item["code"].casefold() == normalized and item["id"] != current_id:
                raise OperationsError("Ja existe um produto ou servico com este codigo.")

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise OperationsError("Valor numerico invalido.") from exc

    @staticmethod
    def _decimal(value: str) -> Decimal:
        normalized = str(value or "").replace("R$", "").replace(" ", "")
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        try:
            return Decimal(normalized or "0")
        except InvalidOperation:
            return Decimal("0")

    @classmethod
    def _inventory_item(cls, item: ItemEstoque) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.nome,
            "category": item.categoria,
            "quantity": item.quantidade,
            "minimum": item.estoque_min,
            "maximum": item.estoque_max,
            "location": item.localizacao,
            "location_label": item.coluna.label,
            "health": item.stock_status.label,
            "health_code": item.stock_status.value,
            "needs_restock": item.precisa_repor,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _movement_item(movement: Movimentacao) -> dict[str, Any]:
        return {
            "id": movement.id,
            "item_id": movement.item_id,
            "item_name": movement.item_nome,
            "type": movement.tipo,
            "quantity": movement.quantidade,
            "previous_quantity": movement.quantidade_anterior,
            "new_quantity": movement.quantidade_nova,
            "timestamp": movement.timestamp,
        }

    @classmethod
    def _product_item(cls, record: BusinessRecord) -> dict[str, Any]:
        fields = record.fields
        price = fields.get("preco", "")
        cost = fields.get("custo", "")
        price_number = cls._decimal(price)
        cost_number = cls._decimal(cost)
        margin = (
            round(float((price_number - cost_number) / price_number * 100), 1)
            if price_number > 0
            else None
        )
        return {
            "id": record.id,
            "code": fields.get("codigo", ""),
            "name": record.title,
            "type": fields.get("tipo", "Produto"),
            "category": fields.get("categoria", ""),
            "unit": fields.get("unidade", ""),
            "price": price,
            "cost": cost,
            "margin_percent": margin,
            "default_supplier": fields.get("fornecedor_padrao", ""),
            "status": fields.get("status", "Ativo"),
            "notes": fields.get("observacoes", ""),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    def _inventory_changed(self, action: str, data=None) -> None:
        payload: dict[str, Any] = {"action": action}
        if isinstance(data, ItemEstoque):
            payload["item"] = self._inventory_item(data)
        elif isinstance(data, Movimentacao):
            payload["movement"] = self._movement_item(data)
        elif data:
            payload["item_id"] = str(data)
        self._publish("inventory.changed", payload)

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_hub is not None:
            self.event_hub.publish(event_type, payload)


_operations_service: BusinessOperationsService | None = None
_operations_lock = threading.Lock()


def get_operations_service() -> BusinessOperationsService:
    global _operations_service
    if _operations_service is None:
        with _operations_lock:
            if _operations_service is None:
                _operations_service = BusinessOperationsService()
    return _operations_service


def reset_operations_service() -> None:
    global _operations_service
    _operations_service = None
