"""HTTP contracts for local chat, conversations and attachments."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.chat_attachments import AttachmentError
from core.chat_service import ChatBusyError, ChatNotFoundError

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    conversation_id: str = ""
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    model_id: str = ""


@router.get("/conversations")
async def list_conversations(request: Request) -> dict:
    return {"ok": True, "items": request.app.state.chat_coordinator.list_conversations()}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict:
    try:
        conversation = request.app.state.chat_coordinator.get_conversation(conversation_id)
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "conversation": conversation}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request) -> dict:
    try:
        deleted = request.app.state.chat_coordinator.delete_conversation(conversation_id)
    except ChatBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "deleted": conversation_id if deleted else ""}


@router.post("/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    request: Request,
    filename: Annotated[str, Header(alias="X-Celsius-Filename")],
) -> dict:
    store = request.app.state.chat_coordinator.attachments
    declared_length = request.headers.get("Content-Length", "")
    if declared_length.isdigit() and int(declared_length) > store.max_bytes:
        raise HTTPException(status_code=413, detail="Arquivo maior que o limite configurado.")

    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > store.max_bytes:
            raise HTTPException(status_code=413, detail="Arquivo maior que o limite configurado.")
    try:
        attachment = store.save(unquote(filename), bytes(content))
    except AttachmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "attachment": attachment.public_dict()}


@router.post("/messages", status_code=status.HTTP_202_ACCEPTED)
async def send_message(payload: ChatMessageRequest, request: Request) -> dict:
    try:
        job = request.app.state.chat_coordinator.submit(
            message=payload.message,
            conversation_id=payload.conversation_id,
            attachment_ids=payload.attachment_ids,
            model_id=payload.model_id,
        )
    except ChatBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (AttachmentError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "job": job}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    try:
        job = request.app.state.chat_coordinator.get_job(job_id)
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "job": job}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> dict:
    try:
        job = request.app.state.chat_coordinator.cancel(job_id)
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "job": job}
