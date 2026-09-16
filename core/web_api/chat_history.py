"""API endpoints for conversation history, search, sharing, and statistics."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from core.conversation_history import ConversationHistoryService
from core.users import User
from core.web_api.auth_users import get_current_user

router = APIRouter(prefix="/chat", tags=["chat-history"])


class CreateConversationRequest(BaseModel):
    title: str = "Nova conversa"
    tags: list[str] = []


class UpdateConversationRequest(BaseModel):
    title: str | None = None
    tags: list[str] | None = None


class AddMessageRequest(BaseModel):
    role: str
    content: str
    metadata: dict | None = None


class ShareRequest(BaseModel):
    expires_hours: int = 24
    max_views: int = 0


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    tags: list[str]
    shared: bool


class SearchResult(BaseModel):
    conversation_id: str
    title: str
    score: int
    excerpts: list[str]
    message_count: int
    updated_at: str


class StatsResponse(BaseModel):
    total_conversations: int
    total_messages: int
    total_words: int
    user_messages: int
    assistant_messages: int
    earliest_conversation: str | None
    latest_conversation: str | None


class ShareResponse(BaseModel):
    share_id: str
    conversation_id: str
    title: str
    created_at: str
    expires_at: str
    max_views: int
    view_count: int
    is_active: bool


@router.post("/conversations/new", response_model=ConversationSummary)
async def create_conversation(
    request: Request, body: CreateConversationRequest, user: User = Depends(get_current_user)
) -> ConversationSummary:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    conv = service.create_conversation(user.id, title=body.title, metadata={"tags": body.tags})
    return ConversationSummary(
        id=conv["id"],
        title=conv["title"],
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
        message_count=len(conv.get("messages", [])),
        tags=conv.get("tags", []),
        shared=conv.get("shared", False),
    )


@router.get("/conversations/history", response_model=list[ConversationSummary])
async def list_conversations(
    request: Request,
    tag: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
) -> list[ConversationSummary]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    convs = service.list_user_conversations(user.id, tag=tag, limit=limit, offset=offset)
    return [
        ConversationSummary(
            id=c["id"],
            title=c["title"],
            created_at=c["created_at"],
            updated_at=c["updated_at"],
            message_count=c["message_count"],
            tags=c.get("tags", []),
            shared=c.get("shared", False),
        )
        for c in convs
    ]


@router.get("/conversations/history/{conversation_id}")
async def get_conversation(
    request: Request, conversation_id: str, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    conv = service.get_conversation(conversation_id, user.id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    return conv


@router.put("/conversations/history/{conversation_id}")
async def update_conversation(
    request: Request,
    conversation_id: str,
    body: UpdateConversationRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    conv = service.update_conversation(conversation_id, user.id, title=body.title, tags=body.tags)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    return conv


@router.delete("/conversations/history/{conversation_id}")
async def delete_conversation(
    request: Request, conversation_id: str, user: User = Depends(get_current_user)
) -> dict[str, bool]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    ok = service.delete_conversation(conversation_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    return {"ok": True}


@router.post("/conversations/history/{conversation_id}/messages")
async def add_message(
    request: Request,
    conversation_id: str,
    body: AddMessageRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    msg = service.add_message(conversation_id, user.id, body.role, body.content, body.metadata)
    if msg is None:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    return msg


@router.get("/conversations/search", response_model=list[SearchResult])
async def search_conversations(
    request: Request,
    q: str = Query(..., min_length=1),
    start_date: str | None = None,
    end_date: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    return service.search_conversations(
        user.id, q, start_date=start_date, end_date=end_date, tag=tag, limit=limit
    )


@router.get("/conversations/stats", response_model=StatsResponse)
async def get_statistics(
    request: Request, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    return service.get_statistics(user.id)


@router.post("/conversations/history/{conversation_id}/share", response_model=ShareResponse)
async def share_conversation(
    request: Request,
    conversation_id: str,
    body: ShareRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    share = service.share_conversation(
        conversation_id, user.id, expires_hours=body.expires_hours, max_views=body.max_views
    )
    if share is None:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    return share


@router.get("/conversations/shared/{share_id}")
async def get_shared_conversation(request: Request, share_id: str) -> dict[str, Any]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    data = service.get_shared_conversation(share_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Link compartilhado invalido ou expirado.")
    return data


@router.delete("/conversations/shared/{share_id}")
async def revoke_share(
    request: Request, share_id: str, user: User = Depends(get_current_user)
) -> dict[str, bool]:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    ok = service.revoke_share(share_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Compartilhamento nao encontrado.")
    return {"ok": True}


@router.get("/conversations/history/{conversation_id}/export")
async def export_conversation(
    request: Request,
    conversation_id: str,
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    user: User = Depends(get_current_user),
) -> Response:
    service = cast(ConversationHistoryService, request.app.state.history_service)
    content = service.export_conversation(conversation_id, user.id, format=format)
    if content is None:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    media_type = "application/json" if format == "json" else "text/markdown"
    filename = f"conversation-{conversation_id}.{'json' if format == 'json' else 'md'}"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
