"""Admin dashboard endpoints for system metrics, user management, and activity monitoring."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from core.conversation_history import ConversationHistoryService
from core.decision_calibration import load_outcomes
from core.metrics import MetricNames, get_metrics
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


class DecisionKindStats(BaseModel):
    n: int
    predicted_true: int
    rate: float
    mean_value: float


class DecisionStatsResponse(BaseModel):
    enabled: bool
    outcomes_file: str
    total_outcomes: int
    total_provider_fallbacks: int
    fallback_rate: float
    by_kind: dict[str, DecisionKindStats]
    requests_total: dict[str, float]
    latency_ms: dict[str, float]


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


def _decision_requests_totals() -> dict[str, float]:
    metrics = get_metrics()
    totals: dict[str, float] = {}
    for status in ("ok", "error", "fallback", "disabled"):
        totals[status] = metrics.get_counter(MetricNames.DECISION_REQUESTS_TOTAL, status=status)
    return totals


def _decision_latency_ms() -> dict[str, float]:
    stats = get_metrics().get_histogram_stats(MetricNames.DECISION_LATENCY_SECONDS)
    if stats["count"] == 0:
        return {"count": 0.0, "avg_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
    return {
        "count": float(stats["count"]),
        "avg_ms": round(stats["avg"] * 1000.0, 2),
        "p50_ms": round(stats["p50"] * 1000.0, 2),
        "p95_ms": round(stats["p95"] * 1000.0, 2),
        "p99_ms": round(stats["p99"] * 1000.0, 2),
    }


def _decision_outcomes(settings: Any) -> tuple[list[dict[str, Any]], Path]:
    logs_dir = getattr(settings, "logs_dir", None) or Path(settings.base_dir) / "logs"
    path = Path(logs_dir) / "decision_outcomes.jsonl"
    if not path.exists():
        return [], path
    return load_outcomes(path), path


@router.get("/dashboard/decisions", response_model=DecisionStatsResponse)
async def get_decision_stats(
    request: Request, admin: User = Depends(require_admin)
) -> DecisionStatsResponse:
    settings = request.app.state.settings
    decision_settings = getattr(settings, "decision", None)
    outcomes, path = _decision_outcomes(settings)

    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in outcomes:
        by_kind[str(entry.get("kind", "unknown"))].append(entry)

    fallbacks = sum(1 for e in outcomes if str(e.get("provider", "")).lower() == "fallback")

    kind_stats: dict[str, DecisionKindStats] = {}
    for kind, items in by_kind.items():
        predicted_true = sum(1 for e in items if bool(e.get("predicted")))
        mean_value = 0.0
        if items:
            values = []
            for e in items:
                try:
                    values.append(float(e.get("value", 0.0)))
                except (TypeError, ValueError):
                    values.append(0.0)
            mean_value = round(sum(values) / len(values), 4)
        kind_stats[kind] = DecisionKindStats(
            n=len(items),
            predicted_true=predicted_true,
            rate=round(predicted_true / len(items), 4) if items else 0.0,
            mean_value=mean_value,
        )

    return DecisionStatsResponse(
        enabled=bool(getattr(decision_settings, "enabled", False)),
        outcomes_file=str(path),
        total_outcomes=len(outcomes),
        total_provider_fallbacks=fallbacks,
        fallback_rate=round(fallbacks / len(outcomes), 4) if outcomes else 0.0,
        by_kind=kind_stats,
        requests_total=_decision_requests_totals(),
        latency_ms=_decision_latency_ms(),
    )
