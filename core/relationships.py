"""Shared customer and supplier access for desktop, web and local AI tools."""

from __future__ import annotations

import threading
from typing import Any

from core.business_records import BusinessRecord, BusinessRecordService, get_business_record_service
from core.modules import MODULE_CUSTOMERS
from core.settings import get_settings
from core.suppliers import Supplier, SupplierService, get_supplier_service


class RelationshipError(ValueError):
    """Raised when a customer or supplier operation is invalid."""


class RelationshipService:
    def __init__(
        self,
        *,
        settings=None,
        record_service: BusinessRecordService | None = None,
        supplier_service: SupplierService | None = None,
        event_hub=None,
    ):
        self.settings = settings or get_settings()
        self.record_service = record_service or (
            get_business_record_service()
            if self.settings is get_settings()
            else BusinessRecordService(settings=self.settings)
        )
        self.supplier_service = supplier_service or (
            get_supplier_service()
            if self.settings is get_settings()
            else SupplierService(settings=self.settings)
        )
        self.event_hub = event_hub

    def list_customers(self, search: str = "") -> list[dict[str, Any]]:
        records = self.record_service.search(MODULE_CUSTOMERS, search)
        return [self._customer_item(record) for record in records]

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        record = self._customer_record(customer_id)
        return self._customer_item(record)

    def save_customer(self, values: dict[str, Any], customer_id: str = "") -> dict[str, Any]:
        existing = self._customer_record(customer_id) if customer_id else None
        fields = dict(existing.fields) if existing else {}
        fields.update(self._clean_values(values))
        name = fields.get("nome", existing.title if existing else "").strip()
        if not name:
            raise RelationshipError("Nome do cliente e obrigatorio.")
        fields["nome"] = name
        fields["status"] = fields.get("status", "Ativo").strip() or "Ativo"
        self._ensure_unique_document(
            fields.get("documento", ""),
            self.list_customers(),
            current_id=customer_id,
            label="cliente",
        )
        record = self.record_service.save_record(
            MODULE_CUSTOMERS,
            name,
            fields,
            record_id=customer_id,
        )
        item = self._customer_item(record)
        self._publish(
            "relationships.changed",
            {"kind": "customers", "action": "updated" if customer_id else "created", "item": item},
        )
        return item

    def delete_customer(self, customer_id: str) -> bool:
        self._customer_record(customer_id)
        deleted = self.record_service.delete(customer_id)
        if deleted:
            self._publish(
                "relationships.changed",
                {"kind": "customers", "action": "deleted", "item_id": customer_id},
            )
        return deleted

    def list_suppliers(self, search: str = "") -> list[dict[str, Any]]:
        suppliers = self.supplier_service.search(search)
        return [self._supplier_item(supplier) for supplier in suppliers]

    def get_supplier(self, supplier_id: str) -> dict[str, Any]:
        supplier = self._supplier(supplier_id)
        return self._supplier_item(supplier)

    def save_supplier(self, values: dict[str, Any], supplier_id: str = "") -> dict[str, Any]:
        existing = self._supplier(supplier_id) if supplier_id else None
        fields = self._supplier_values(existing)
        fields.update(self._clean_values(values))
        name = fields.get("nome", "").strip()
        if not name:
            raise RelationshipError("Nome do fornecedor e obrigatorio.")
        fields["nome"] = name
        fields["status"] = fields.get("status", "Ativo").strip() or "Ativo"
        self._ensure_unique_document(
            fields.get("documento", ""),
            self.list_suppliers(),
            current_id=supplier_id,
            label="fornecedor",
        )
        try:
            supplier = (
                self.supplier_service.update(supplier_id, **fields)
                if supplier_id
                else self.supplier_service.add(**fields)
            )
        except ValueError as exc:
            raise RelationshipError(str(exc)) from exc
        if supplier is None:
            raise RelationshipError("Fornecedor nao encontrado.")
        item = self._supplier_item(supplier)
        self._publish(
            "relationships.changed",
            {"kind": "suppliers", "action": "updated" if supplier_id else "created", "item": item},
        )
        return item

    def delete_supplier(self, supplier_id: str) -> bool:
        self._supplier(supplier_id)
        deleted = self.supplier_service.delete(supplier_id)
        if deleted:
            self._publish(
                "relationships.changed",
                {"kind": "suppliers", "action": "deleted", "item_id": supplier_id},
            )
        return deleted

    def format_customers(self, search: str = "", limit: int = 50) -> str:
        items = self.list_customers(search)[: max(1, min(int(limit or 50), 200))]
        if not items:
            return "Nenhum cliente encontrado no cadastro local."
        lines = [f"Clientes locais ({len(items)}):"]
        for item in items:
            details = [item["status"]]
            for label, value in (
                ("tipo", item["customer_type"]),
                ("contato", item["contact"] or item["phone"]),
                ("segmento", item["segment"]),
            ):
                if value:
                    details.append(f"{label}: {value}")
            lines.append(f"- [{item['id']}] {item['name']} | {' | '.join(details)}")
        return "\n".join(lines)

    def format_suppliers(self, search: str = "", limit: int = 50) -> str:
        items = self.list_suppliers(search)[: max(1, min(int(limit or 50), 200))]
        if not items:
            return "Nenhum fornecedor encontrado no cadastro local."
        lines = [f"Fornecedores locais ({len(items)}):"]
        for item in items:
            details = [item["status"]]
            for label, value in (
                ("categoria", item["category"]),
                ("contato", item["contact"] or item["phone"]),
                ("produtos", item["products"]),
                ("entrega", f"{item['lead_time_days']} dias" if item["lead_time_days"] else ""),
            ):
                if value:
                    details.append(f"{label}: {value}")
            lines.append(f"- [{item['id']}] {item['name']} | {' | '.join(details)}")
        return "\n".join(lines)

    @staticmethod
    def _clean_values(values: dict[str, Any]) -> dict[str, str]:
        return {key: str(value or "").strip() for key, value in values.items()}

    @staticmethod
    def _ensure_unique_document(
        document: str,
        items: list[dict[str, Any]],
        *,
        current_id: str,
        label: str,
    ) -> None:
        normalized = "".join(character for character in document if character.isalnum()).casefold()
        if not normalized:
            return
        for item in items:
            existing = "".join(
                character for character in item.get("document", "") if character.isalnum()
            ).casefold()
            if existing == normalized and item["id"] != current_id:
                raise RelationshipError(f"Ja existe um {label} com este documento.")

    def _customer_record(self, customer_id: str) -> BusinessRecord:
        record = self.record_service.get(customer_id)
        if record is None or record.module_id != MODULE_CUSTOMERS:
            raise RelationshipError("Cliente nao encontrado.")
        return record

    @staticmethod
    def _customer_item(record: BusinessRecord) -> dict[str, Any]:
        fields = record.fields
        return {
            "id": record.id,
            "name": record.title,
            "customer_type": fields.get("tipo", "Outro"),
            "document": fields.get("documento", ""),
            "contact": fields.get("contato", ""),
            "phone": fields.get("telefone", ""),
            "email": fields.get("email", ""),
            "address": fields.get("endereco", ""),
            "segment": fields.get("segmento", ""),
            "responsible": fields.get("responsavel", ""),
            "status": fields.get("status", "Ativo"),
            "notes": fields.get("observacoes", ""),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    def _supplier(self, supplier_id: str) -> Supplier:
        supplier = self.supplier_service.get(supplier_id)
        if supplier is None:
            raise RelationshipError("Fornecedor nao encontrado.")
        return supplier

    @staticmethod
    def _supplier_values(supplier: Supplier | None) -> dict[str, str]:
        if supplier is None:
            return {
                "nome": "",
                "contato": "",
                "telefone": "",
                "email": "",
                "categoria": "",
                "documento": "",
                "produtos": "",
                "prazo_pagamento": "",
                "lead_time_dias": "",
                "status": "Ativo",
                "observacoes": "",
            }
        return {
            "nome": supplier.nome,
            "contato": supplier.contato,
            "telefone": supplier.telefone,
            "email": supplier.email,
            "categoria": supplier.categoria,
            "documento": supplier.documento,
            "produtos": supplier.produtos,
            "prazo_pagamento": supplier.prazo_pagamento,
            "lead_time_dias": supplier.lead_time_dias,
            "status": supplier.status,
            "observacoes": supplier.observacoes,
        }

    @staticmethod
    def _supplier_item(supplier: Supplier) -> dict[str, Any]:
        return {
            "id": supplier.id,
            "name": supplier.nome,
            "contact": supplier.contato,
            "phone": supplier.telefone,
            "email": supplier.email,
            "category": supplier.categoria,
            "document": supplier.documento,
            "products": supplier.produtos,
            "payment_terms": supplier.prazo_pagamento,
            "lead_time_days": supplier.lead_time_dias,
            "status": supplier.status,
            "notes": supplier.observacoes,
            "created_at": supplier.created_at,
            "updated_at": supplier.updated_at,
        }

    def _publish(self, event_type: str, payload: dict) -> None:
        if self.event_hub is not None:
            self.event_hub.publish(event_type, payload)


_relationship_service: RelationshipService | None = None
_relationship_lock = threading.Lock()


def get_relationship_service() -> RelationshipService:
    global _relationship_service
    if _relationship_service is None:
        with _relationship_lock:
            if _relationship_service is None:
                _relationship_service = RelationshipService()
    return _relationship_service


def reset_relationship_service() -> None:
    global _relationship_service
    _relationship_service = None
