"""HTTP contracts for local customers and suppliers."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.relationships import RelationshipError

router = APIRouter(tags=["customers and suppliers"])


class CustomerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    customer_type: str = Field(default="Outro", max_length=60)
    document: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=180)
    phone: str = Field(default="", max_length=60)
    email: str = Field(default="", max_length=180)
    address: str = Field(default="", max_length=300)
    segment: str = Field(default="", max_length=120)
    responsible: str = Field(default="", max_length=180)
    status: str = Field(default="Ativo", max_length=40)
    notes: str = Field(default="", max_length=5_000)


class CustomerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    customer_type: str | None = Field(default=None, max_length=60)
    document: str | None = Field(default=None, max_length=80)
    contact: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=300)
    segment: str | None = Field(default=None, max_length=120)
    responsible: str | None = Field(default=None, max_length=180)
    status: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=5_000)


class SupplierCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    contact: str = Field(default="", max_length=180)
    phone: str = Field(default="", max_length=60)
    email: str = Field(default="", max_length=180)
    category: str = Field(default="", max_length=120)
    document: str = Field(default="", max_length=80)
    products: str = Field(default="", max_length=1_000)
    payment_terms: str = Field(default="", max_length=180)
    lead_time_days: str = Field(default="", max_length=20)
    status: str = Field(default="Ativo", max_length=40)
    notes: str = Field(default="", max_length=5_000)


class SupplierUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    contact: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=180)
    category: str | None = Field(default=None, max_length=120)
    document: str | None = Field(default=None, max_length=80)
    products: str | None = Field(default=None, max_length=1_000)
    payment_terms: str | None = Field(default=None, max_length=180)
    lead_time_days: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=5_000)


CUSTOMER_FIELD_MAP = {
    "name": "nome",
    "customer_type": "tipo",
    "document": "documento",
    "contact": "contato",
    "phone": "telefone",
    "email": "email",
    "address": "endereco",
    "segment": "segmento",
    "responsible": "responsavel",
    "status": "status",
    "notes": "observacoes",
}
SUPPLIER_FIELD_MAP = {
    "name": "nome",
    "contact": "contato",
    "phone": "telefone",
    "email": "email",
    "category": "categoria",
    "document": "documento",
    "products": "produtos",
    "payment_terms": "prazo_pagamento",
    "lead_time_days": "lead_time_dias",
    "status": "status",
    "notes": "observacoes",
}


def _mapped_values(payload: BaseModel, mapping: dict[str, str]) -> dict[str, str]:
    values = payload.model_dump(exclude_none=True)
    return {target: values[source] for source, target in mapping.items() if source in values}


def _relationship_error(exc: RelationshipError, *, not_found: bool = False) -> HTTPException:
    return HTTPException(status_code=404 if not_found else 400, detail=str(exc))


@router.get("/customers")
def list_customers(request: Request, search: str = "") -> dict:
    items = request.app.state.relationship_service.list_customers(search)
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/customers", status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreateRequest, request: Request) -> dict:
    try:
        item = request.app.state.relationship_service.save_customer(
            _mapped_values(payload, CUSTOMER_FIELD_MAP)
        )
    except RelationshipError as exc:
        raise _relationship_error(exc) from exc
    return {"ok": True, "item": item}


@router.patch("/customers/{customer_id}")
def update_customer(customer_id: str, payload: CustomerUpdateRequest, request: Request) -> dict:
    try:
        item = request.app.state.relationship_service.save_customer(
            _mapped_values(payload, CUSTOMER_FIELD_MAP),
            customer_id,
        )
    except RelationshipError as exc:
        raise _relationship_error(exc, not_found="nao encontrado" in str(exc).lower()) from exc
    return {"ok": True, "item": item}


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str, request: Request) -> dict:
    try:
        request.app.state.relationship_service.delete_customer(customer_id)
    except RelationshipError as exc:
        raise _relationship_error(exc, not_found=True) from exc
    return {"ok": True, "deleted": customer_id}


@router.get("/suppliers")
def list_suppliers(request: Request, search: str = "") -> dict:
    items = request.app.state.relationship_service.list_suppliers(search)
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierCreateRequest, request: Request) -> dict:
    try:
        item = request.app.state.relationship_service.save_supplier(
            _mapped_values(payload, SUPPLIER_FIELD_MAP)
        )
    except RelationshipError as exc:
        raise _relationship_error(exc) from exc
    return {"ok": True, "item": item}


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: str, payload: SupplierUpdateRequest, request: Request) -> dict:
    try:
        item = request.app.state.relationship_service.save_supplier(
            _mapped_values(payload, SUPPLIER_FIELD_MAP),
            supplier_id,
        )
    except RelationshipError as exc:
        raise _relationship_error(exc, not_found="nao encontrado" in str(exc).lower()) from exc
    return {"ok": True, "item": item}


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: str, request: Request) -> dict:
    try:
        request.app.state.relationship_service.delete_supplier(supplier_id)
    except RelationshipError as exc:
        raise _relationship_error(exc, not_found=True) from exc
    return {"ok": True, "deleted": supplier_id}
