"""HTTP contracts for quotes, reports, cases and deadlines."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.workflows import WorkflowError

router = APIRouter(tags=["business workflows"])
logger = logging.getLogger(__name__)


class QuoteRequest(BaseModel):
    number: str = Field(default="", max_length=80)
    title: str = Field(min_length=1, max_length=180)
    customer: str = Field(default="", max_length=180)
    valid_until: str = Field(default="", max_length=20)
    value: str = Field(default="", max_length=60)
    margin: str = Field(default="", max_length=60)
    responsible: str = Field(default="", max_length=180)
    status: str = Field(default="Rascunho", max_length=40)
    items: str = Field(default="", max_length=10_000)
    notes: str = Field(default="", max_length=5_000)


class CaseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    customer: str = Field(default="", max_length=180)
    case_type: str = Field(default="", max_length=120)
    deadline: str = Field(default="", max_length=20)
    priority: str = Field(default="Normal", max_length=40)
    responsible: str = Field(default="", max_length=180)
    status: str = Field(default="Novo", max_length=60)
    next_step: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=5_000)


class ReportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    report_type: str = Field(default="Executivo", max_length=60)
    period: str = Field(default="Atual", max_length=120)
    source: str = Field(default="Executivo", max_length=80)
    indicator: str = Field(default="", max_length=180)
    periodicity: str = Field(default="Sob demanda", max_length=40)
    responsible: str = Field(default="", max_length=180)
    output_format: str = Field(default="pdf", pattern="^(pdf|docx|md)$")
    notes: str = Field(default="", max_length=5_000)


QUOTE_MAP = {
    "number": "numero",
    "title": "titulo",
    "customer": "cliente",
    "valid_until": "validade",
    "value": "valor",
    "margin": "margem",
    "responsible": "responsavel",
    "status": "status",
    "items": "itens",
    "notes": "observacoes",
}
CASE_MAP = {
    "title": "processo",
    "customer": "cliente",
    "case_type": "tipo",
    "deadline": "prazo",
    "priority": "prioridade",
    "responsible": "responsavel",
    "status": "status",
    "next_step": "proximo_passo",
    "notes": "observacoes",
}
REPORT_MAP = {
    "title": "titulo",
    "report_type": "tipo",
    "period": "periodo",
    "source": "fonte_dados",
    "indicator": "indicador",
    "periodicity": "periodicidade",
    "responsible": "responsavel",
    "output_format": "formato",
    "notes": "observacoes",
}


def _mapped(payload: BaseModel, mapping: dict[str, str]) -> dict[str, str]:
    values = payload.model_dump()
    return {target: values[source] for source, target in mapping.items()}


def _error(exc: WorkflowError, *, not_found: bool = False) -> HTTPException:
    return HTTPException(status_code=404 if not_found else 400, detail=str(exc))


@router.get("/quotes")
def list_quotes(request: Request, search: str = "") -> dict:
    items = request.app.state.workflow_service.list_quotes(search)
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/quotes", status_code=status.HTTP_201_CREATED)
def create_quote(payload: QuoteRequest, request: Request) -> dict:
    try:
        item = request.app.state.workflow_service.save_quote(_mapped(payload, QUOTE_MAP))
    except WorkflowError as exc:
        raise _error(exc) from exc
    return {"ok": True, "item": item}


@router.patch("/quotes/{quote_id}")
def update_quote(quote_id: str, payload: QuoteRequest, request: Request) -> dict:
    try:
        item = request.app.state.workflow_service.save_quote(_mapped(payload, QUOTE_MAP), quote_id)
    except WorkflowError as exc:
        raise _error(exc, not_found="nao encontrado" in str(exc).lower()) from exc
    return {"ok": True, "item": item}


@router.delete("/quotes/{quote_id}")
def delete_quote(quote_id: str, request: Request) -> dict:
    try:
        request.app.state.workflow_service.delete_quote(quote_id)
    except WorkflowError as exc:
        raise _error(exc, not_found=True) from exc
    return {"ok": True, "deleted": quote_id}


@router.get("/cases-deadlines")
def list_cases(request: Request, search: str = "") -> dict:
    items = request.app.state.workflow_service.list_cases(search)
    return {"ok": True, "items": items, "count": len(items), "local_only": True}


@router.post("/cases-deadlines", status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseRequest, request: Request) -> dict:
    try:
        item = request.app.state.workflow_service.save_case(_mapped(payload, CASE_MAP))
    except WorkflowError as exc:
        raise _error(exc) from exc
    return {"ok": True, "item": item, "local_only": True}


@router.patch("/cases-deadlines/{case_id}")
def update_case(case_id: str, payload: CaseRequest, request: Request) -> dict:
    try:
        item = request.app.state.workflow_service.save_case(_mapped(payload, CASE_MAP), case_id)
    except WorkflowError as exc:
        raise _error(exc, not_found="nao encontrado" in str(exc).lower()) from exc
    return {"ok": True, "item": item, "local_only": True}


@router.delete("/cases-deadlines/{case_id}")
def delete_case(case_id: str, request: Request) -> dict:
    try:
        request.app.state.workflow_service.delete_case(case_id)
    except WorkflowError as exc:
        raise _error(exc, not_found=True) from exc
    return {"ok": True, "deleted": case_id}


@router.get("/reports")
def list_reports(request: Request, search: str = "") -> dict:
    items = request.app.state.workflow_service.list_reports(search)
    return {"ok": True, "items": items, "count": len(items), "local_only": True}


@router.post("/reports/generate", status_code=status.HTTP_201_CREATED)
def generate_report(payload: ReportRequest, request: Request) -> dict:
    try:
        item = request.app.state.workflow_service.generate_report(_mapped(payload, REPORT_MAP))
    except WorkflowError as exc:
        raise _error(exc) from exc
    except Exception as exc:
        logger.exception("Failed to generate %s report", payload.output_format)
        raise HTTPException(
            status_code=500,
            detail=(
                "Nao foi possivel gerar o arquivo do relatorio. "
                "Consulte os logs do Celsius para obter o diagnostico tecnico."
            ),
        ) from exc
    return {"ok": True, "item": item, "local_only": True}


@router.get("/reports/{report_id}/download")
def download_report(report_id: str, request: Request):
    try:
        path = request.app.state.workflow_service.report_file(report_id)
    except WorkflowError as exc:
        raise _error(exc, not_found=True) from exc
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, request: Request) -> dict:
    try:
        request.app.state.workflow_service.delete_report(report_id)
    except WorkflowError as exc:
        raise _error(exc, not_found=True) from exc
    return {"ok": True, "deleted": report_id}
