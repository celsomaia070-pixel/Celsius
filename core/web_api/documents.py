"""HTTP contracts for the local document library and knowledge search."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import FileResponse

from core.documents import DocumentLibraryError

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_documents(request: Request) -> dict:
    items = request.app.state.document_service.list_documents()
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    request: Request,
    filename: Annotated[str, Header(alias="X-Celsius-Filename")],
    title: Annotated[str, Header(alias="X-Celsius-Title")] = "",
    document_type: Annotated[str, Header(alias="X-Celsius-Document-Type")] = "Outro",
    category: Annotated[str, Header(alias="X-Celsius-Category")] = "",
    origin: Annotated[str, Header(alias="X-Celsius-Origin")] = "",
    responsible: Annotated[str, Header(alias="X-Celsius-Responsible")] = "",
) -> dict:
    service = request.app.state.document_service
    clean_filename = unquote(filename)
    max_bytes = service.max_bytes_for(clean_filename)
    declared_length = request.headers.get("Content-Length", "")
    if declared_length.isdigit() and int(declared_length) > max_bytes:
        raise HTTPException(status_code=413, detail="Arquivo maior que o limite configurado.")
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(status_code=413, detail="Arquivo maior que o limite configurado.")
    try:
        job, document = service.submit_upload(
            clean_filename,
            bytes(content),
            title=unquote(title),
            document_type=unquote(document_type),
            category=unquote(category),
            origin=unquote(origin),
            responsible=unquote(responsible),
        )
    except DocumentLibraryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "job": job, "document": document}


@router.get("/jobs/{job_id}")
def get_document_job(job_id: str, request: Request) -> dict:
    try:
        job = request.app.state.document_service.get_job(job_id)
    except DocumentLibraryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "job": job}


@router.get("/search")
def search_documents(query: str, request: Request, top_k: int = 5) -> dict:
    try:
        items = request.app.state.document_service.search(query, top_k=top_k)
    except DocumentLibraryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "query": query, "items": items, "count": len(items)}


@router.post("/{document_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
def reindex_document(document_id: str, request: Request) -> dict:
    try:
        job = request.app.state.document_service.submit_reindex(document_id)
    except DocumentLibraryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "job": job}


@router.get("/{document_id}/file")
def download_document(document_id: str, request: Request):
    try:
        path, filename = request.app.state.document_service.resolve_file(document_id)
    except DocumentLibraryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.delete("/{document_id}")
def delete_document(document_id: str, request: Request) -> dict:
    if not request.app.state.document_service.delete(document_id):
        raise HTTPException(status_code=404, detail="Documento nao encontrado.")
    return {"ok": True, "deleted": document_id}
