"""API endpoints for proactive notifications."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from core.proactive_notifications import (
    NotificationPriority,
    NotificationRule,
    NotificationType,
    ProactiveNotification,
    ProactiveNotificationService,
)
from core.users import User
from core.web_api.auth_users import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: str
    type: str
    priority: str
    title: str
    message: str
    source_module: str
    created_at: str
    read: bool
    action_url: str
    metadata: dict


class UnreadCountResponse(BaseModel):
    count: int


class RuleRequest(BaseModel):
    name: str
    notification_type: str
    priority: str
    source_module: str
    condition: str
    message_template: str
    enabled: bool = True
    cooldown_minutes: int = 60


class RuleResponse(BaseModel):
    id: str
    name: str
    notification_type: str
    priority: str
    source_module: str
    condition: str
    message_template: str
    enabled: bool
    cooldown_minutes: int
    last_triggered: str


def _notification_to_response(n: ProactiveNotification) -> NotificationResponse:
    return NotificationResponse(
        id=n.id,
        type=n.type.value,
        priority=n.priority.value,
        title=n.title,
        message=n.message,
        source_module=n.source_module,
        created_at=n.created_at,
        read=n.read,
        action_url=n.action_url,
        metadata=n.metadata,
    )


def _rule_to_response(r: NotificationRule) -> RuleResponse:
    return RuleResponse(
        id=r.id,
        name=r.name,
        notification_type=r.notification_type.value,
        priority=r.priority.value,
        source_module=r.source_module,
        condition=r.condition,
        message_template=r.message_template,
        enabled=r.enabled,
        cooldown_minutes=r.cooldown_minutes,
        last_triggered=r.last_triggered,
    )


@router.get("/", response_model=list[NotificationResponse])
async def list_notifications(
    request: Request,
    unread_only: bool = False,
    type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
) -> list[NotificationResponse]:
    service = cast(ProactiveNotificationService, request.app.state.notification_service)
    ntype = NotificationType(type) if type else None
    return [
        _notification_to_response(n)
        for n in service.list_notifications(
            unread_only=unread_only, notification_type=ntype, limit=limit
        )
    ]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    request: Request, user: User = Depends(get_current_user)
) -> UnreadCountResponse:
    service = cast(ProactiveNotificationService, request.app.state.notification_service)
    return UnreadCountResponse(count=service.unread_count())


@router.post("/{notification_id}/read")
async def mark_read(
    request: Request, notification_id: str, user: User = Depends(get_current_user)
) -> dict[str, bool]:
    service = cast(ProactiveNotificationService, request.app.state.notification_service)
    ok = service.mark_read(notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notificacao nao encontrada.")
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(
    request: Request, user: User = Depends(get_current_user)
) -> dict[str, int | bool]:
    service = cast(ProactiveNotificationService, request.app.state.notification_service)
    count = service.mark_all_read()
    return {"ok": True, "marked": count}


@router.delete("/{notification_id}")
async def delete_notification(
    request: Request, notification_id: str, user: User = Depends(get_current_user)
) -> dict[str, bool]:
    service = cast(ProactiveNotificationService, request.app.state.notification_service)
    ok = service.delete_notification(notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notificacao nao encontrada.")
    return {"ok": True}


@router.post("/refresh")
async def refresh_notifications(
    request: Request, user: User = Depends(get_current_user)
) -> dict[str, int | bool]:
    service = cast(ProactiveNotificationService, request.app.state.notification_service)
    new = service.run_watchers()
    return {"ok": True, "new_notifications": len(new)}


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    request: Request, user: User = Depends(get_current_user)
) -> list[RuleResponse]:
    service = cast(ProactiveNotificationService, request.app.state.notification_service)
    return [_rule_to_response(r) for r in service.list_rules()]


@router.post("/rules", response_model=RuleResponse, status_code=201)
async def create_rule(
    request: Request, body: RuleRequest, user: User = Depends(get_current_user)
) -> RuleResponse:
    service = cast(ProactiveNotificationService, request.app.state.notification_service)
    try:
        ntype = NotificationType(body.notification_type)
        priority = NotificationPriority(body.priority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rule = NotificationRule(
        id="",
        name=body.name,
        notification_type=ntype,
        priority=priority,
        source_module=body.source_module,
        condition=body.condition,
        message_template=body.message_template,
        enabled=body.enabled,
        cooldown_minutes=body.cooldown_minutes,
    )
    created = service.add_rule(rule)
    return _rule_to_response(created)


@router.delete("/rules/{rule_id}")
async def delete_rule(
    request: Request, rule_id: str, user: User = Depends(get_current_user)
) -> dict[str, bool]:
    service = cast(ProactiveNotificationService, request.app.state.notification_service)
    ok = service.delete_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Regra nao encontrada.")
    return {"ok": True}
