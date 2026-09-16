"""Admin dashboard endpoints for system metrics, user management, and activity monitoring."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from core.conversation_history import ConversationHistoryService
from core.users import User, UserRole, UserService
from core.web_api.auth_users import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class SystemStatsResponse(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    total_conversations: int
    total_messages: int
    total_words: int
    total_shares: int
    storage_used_mb: float


class UserActivity(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str
    last_login: str
    conversation_count: int
    message_count: int


class RecentActivity(BaseModel):
    activity_type: str
    description: str
    timestamp: str
    user_id: str | None = None


class SystemHealth(BaseModel):
    status: str
    uptime_seconds: float
    data_dir_exists: bool
    users_dir_exists: bool
    conversations_dir_exists: bool
    reports_dir_exists: bool


_start_time = datetime.now(timezone.utc)


def _get_storage_usage(data_dir: Path) -> float:
    total = 0
    try:
        for f in data_dir.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except Exception:
        pass
    return round(total / (1024 * 1024), 2)


def _count_shares(conversations_dir: Path) -> int:
    shares_dir = conversations_dir / "shares"
    if not shares_dir.exists():
        return 0
    return sum(1 for f in shares_dir.glob("*.json"))


@router.get("/dashboard/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    request: Request, admin: User = Depends(require_admin)
) -> SystemStatsResponse:
    user_service = cast(UserService, request.app.state.user_service)
    history_service = cast(ConversationHistoryService, request.app.state.history_service)
    users = user_service.list_users()
    active = [u for u in users if u.is_active]
    admins = [u for u in users if u.role == UserRole.ADMIN]

    total_conversations = 0
    total_messages = 0
    total_words = 0
    for u in users:
        stats = history_service.get_statistics(u.id)
        total_conversations += stats["total_conversations"]
        total_messages += stats["total_messages"]
        total_words += stats["total_words"]

    settings = request.app.state.settings
    data_dir = Path(settings.data_dir)
    conv_dir = data_dir / "conversation_history"

    return SystemStatsResponse(
        total_users=len(users),
        active_users=len(active),
        admin_users=len(admins),
        total_conversations=total_conversations,
        total_messages=total_messages,
        total_words=total_words,
        total_shares=_count_shares(conv_dir),
        storage_used_mb=_get_storage_usage(data_dir),
    )


@router.get("/dashboard/users", response_model=list[UserActivity])
async def get_user_activity(
    request: Request, admin: User = Depends(require_admin)
) -> list[UserActivity]:
    user_service = cast(UserService, request.app.state.user_service)
    history_service = cast(ConversationHistoryService, request.app.state.history_service)
    users = user_service.list_users()
    result = []
    for u in users:
        stats = history_service.get_statistics(u.id)
        result.append(
            UserActivity(
                user_id=u.id,
                email=u.email,
                display_name=u.display_name,
                role=u.role.value,
                last_login=u.last_login,
                conversation_count=stats["total_conversations"],
                message_count=stats["total_messages"],
            )
        )
    result.sort(key=lambda x: x.message_count, reverse=True)
    return result


@router.get("/dashboard/activity", response_model=list[RecentActivity])
async def get_recent_activity(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(require_admin),
) -> list[RecentActivity]:
    settings = request.app.state.settings
    data_dir = Path(settings.data_dir)
    audit_log = data_dir / "audit.log"
    activities: list[RecentActivity] = []
    if audit_log.exists():
        try:
            lines = audit_log.read_text(encoding="utf-8").strip().split("\n")
            for line in reversed(lines[-limit:]):
                try:
                    import json

                    entry = json.loads(line)
                    activities.append(
                        RecentActivity(
                            activity_type="http_request",
                            description=f"{entry.get('method', '')} {entry.get('path', '')} -> {entry.get('status', '')}",
                            timestamp=entry.get("occurred_at", ""),
                            user_id=entry.get("actor", None),
                        )
                    )
                except Exception:
                    continue
        except Exception:
            pass
    return activities[:limit]


@router.get("/dashboard/health", response_model=SystemHealth)
async def get_system_health(request: Request, admin: User = Depends(require_admin)) -> SystemHealth:
    settings = request.app.state.settings
    data_dir = Path(settings.data_dir)
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()
    return SystemHealth(
        status="healthy",
        uptime_seconds=round(uptime, 1),
        data_dir_exists=data_dir.exists(),
        users_dir_exists=(data_dir / "users").exists(),
        conversations_dir_exists=(data_dir / "conversation_history").exists(),
        reports_dir_exists=(data_dir / "reports").exists(),
    )
