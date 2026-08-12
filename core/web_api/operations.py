"""HTTP contracts for local inventory, products and services."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.operations import OperationsError

router = APIRouter(tags=["inventory and catalog"])


class InventoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    category: str = Field(default="Geral", max_length=120)
    quantity: int = Field(default=0, ge=0, le=1_000_000_000)
    minimum: int = Field(default=0, ge=0, le=1_000_000_000)
    maximum: int = Field(default=0, ge=0, le=1_000_000_000)
    location: str = Field(default="", max_length=40)


class InventoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    category: str | None = Field(default=None, max_length=120)
    minimum: int | None = Field(default=None, ge=0, le=1_000_000_000)
    maximum: int | None = Field(default=None, ge=0, le=1_000_000_000)
    location: str | None = Field(default=None, max_length=40)


class InventoryMovementRequest(BaseModel):
    type: str = Field(pattern="^(entrada|saida)$")
    quantity: int = Field(gt=0, le=1_000_000_000)


class ProductCreateRequest(BaseModel):
    code: str = Field(default="", max_length=80)
    name: str = Field(min_length=1, max_length=180)
    type: str = Field(default="Produto", max_length=40)
    category: str = Field(default="", max_length=120)
    unit: str = Field(default="", max_length=40)
    price: str = Field(default="", max_length=60)
    cost: str = Field(default="", max_length=60)
    default_supplier: str = Field(default="", max_length=180)
    status: str = Field(default="Ativo", max_length=40)
    notes: str = Field(default="", max_length=5_000)


class ProductUpdateRequest(BaseModel):
    code: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=180)
    type: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=120)
    unit: str | None = Field(default=None, max_length=40)
    price: str | None = Field(default=None, max_length=60)
    cost: str | None = Field(default=None, max_length=60)
    default_supplier: str | None = Field(default=None, max_length=180)
    status: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=5_000)


PRODUCT_FIELD_MAP = {
    "code": "codigo",
    "name": "nome",
    "type": "tipo",
    "category": "categoria",
    "unit": "unidade",
    "price": "preco",
    "cost": "custo",
    "default_supplier": "fornecedor_padrao",
    "status": "status",
    "notes": "observacoes",
}


def _values(payload: BaseModel) -> dict:
    return payload.model_dump(exclude_none=True)


def _product_values(payload: BaseModel) -> dict[str, str]:
    values = payload.model_dump(exclude_none=True)
    return {
        target: values[source] for source, target in PRODUCT_FIELD_MAP.items() if source in values
    }


def _operation_error(exc: OperationsError, *, not_found: bool = False) -> HTTPException:
    return HTTPException(status_code=404 if not_found else 400, detail=str(exc))


@router.get("/inventory")
def list_inventory(request: Request, search: str = "") -> dict:
    items = request.app.state.operations_service.list_inventory(search)
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/inventory", status_code=status.HTTP_201_CREATED)
def create_inventory_item(payload: InventoryCreateRequest, request: Request) -> dict:
    try:
        item = request.app.state.operations_service.save_inventory_item(_values(payload))
    except OperationsError as exc:
        raise _operation_error(exc) from exc
    return {"ok": True, "item": item}


@router.patch("/inventory/{item_id}")
def update_inventory_item(
    item_id: str,
    payload: InventoryUpdateRequest,
    request: Request,
) -> dict:
    try:
        item = request.app.state.operations_service.save_inventory_item(_values(payload), item_id)
    except OperationsError as exc:
        raise _operation_error(exc, not_found="nao encontrado" in str(exc).lower()) from exc
    return {"ok": True, "item": item}


@router.delete("/inventory/{item_id}")
def delete_inventory_item(item_id: str, request: Request) -> dict:
    try:
        request.app.state.operations_service.delete_inventory_item(item_id)
    except OperationsError as exc:
        raise _operation_error(exc, not_found=True) from exc
    return {"ok": True, "deleted": item_id}


@router.post("/inventory/{item_id}/movements", status_code=status.HTTP_201_CREATED)
def move_inventory(item_id: str, payload: InventoryMovementRequest, request: Request) -> dict:
    try:
        movement = request.app.state.operations_service.move_inventory(
            item_id,
            payload.type,
            payload.quantity,
        )
        item = request.app.state.operations_service.get_inventory_item(item_id)
    except OperationsError as exc:
        raise _operation_error(exc, not_found="nao encontrado" in str(exc).lower()) from exc
    return {"ok": True, "movement": movement, "item": item}


@router.get("/inventory-movements")
def list_inventory_movements(
    request: Request,
    item_id: str = "",
    limit: int = 100,
) -> dict:
    items = request.app.state.operations_service.list_movements(item_id, limit)
    return {"ok": True, "items": items, "count": len(items)}


@router.get("/products-services")
def list_products(request: Request, search: str = "") -> dict:
    items = request.app.state.operations_service.list_products(search)
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/products-services", status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreateRequest, request: Request) -> dict:
    try:
        item = request.app.state.operations_service.save_product(_product_values(payload))
    except OperationsError as exc:
        raise _operation_error(exc) from exc
    return {"ok": True, "item": item}


@router.patch("/products-services/{product_id}")
def update_product(product_id: str, payload: ProductUpdateRequest, request: Request) -> dict:
    try:
        item = request.app.state.operations_service.save_product(
            _product_values(payload),
            product_id,
        )
    except OperationsError as exc:
        raise _operation_error(exc, not_found="nao encontrado" in str(exc).lower()) from exc
    return {"ok": True, "item": item}


@router.delete("/products-services/{product_id}")
def delete_product(product_id: str, request: Request) -> dict:
    try:
        request.app.state.operations_service.delete_product(product_id)
    except OperationsError as exc:
        raise _operation_error(exc, not_found=True) from exc
    return {"ok": True, "deleted": product_id}
