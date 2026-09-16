"""Proactive notification system with event watchers and rule-based alerts."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from core.json_persistence import atomic_write_json, read_json

logger = logging.getLogger(__name__)


class NotificationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationType(str, Enum):
    SYSTEM = "system"
    INVENTORY = "inventory"
    DEADLINE = "deadline"
    QUOTE = "quote"
    SECURITY = "security"
    USAGE = "usage"
    CUSTOM = "custom"


@dataclass
class ProactiveNotification:
    id: str
    type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    source_module: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    read: bool = False
    action_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationRule:
    id: str
    name: str
    notification_type: NotificationType
    priority: NotificationPriority
    source_module: str
    condition: str
    message_template: str
    enabled: bool = True
    cooldown_minutes: int = 60
    last_triggered: str = ""


class ProactiveNotificationService:
    """Manages proactive notifications with rule-based triggers and persistence."""

    def __init__(self, data_dir: Path | None = None):
        from core.settings import get_settings

        self._data_dir = Path(data_dir or get_settings().data_dir)
        self._notifications_dir = self._data_dir / "notifications"
        self._notifications_dir.mkdir(parents=True, exist_ok=True)
        self._rules_file = self._data_dir / "notification_rules.json"
        self._lock = threading.Lock()
        self._notifications: list[ProactiveNotification] = []
        self._rules: list[NotificationRule] = []
        self._watchers: list[Callable[[], list[ProactiveNotification]]] = []
        self._load_all()

    def _load_all(self) -> None:
        with self._lock:
            self._notifications.clear()
            for f in sorted(self._notifications_dir.glob("*.json")):
                try:
                    data = read_json(f, None)
                    if data:
                        data["type"] = NotificationType(data["type"])
                        data["priority"] = NotificationPriority(data["priority"])
                        self._notifications.append(ProactiveNotification(**data))
                except Exception as exc:
                    logger.warning("Falha ao carregar notificacao %s: %s", f.name, exc)
            raw_rules = read_json(self._rules_file, [])
            self._rules.clear()
            for r in raw_rules or []:
                try:
                    r["notification_type"] = NotificationType(r["notification_type"])
                    r["priority"] = NotificationPriority(r["priority"])
                    self._rules.append(NotificationRule(**r))
                except Exception:
                    continue

    def _save_notification(self, notification: ProactiveNotification) -> None:
        path = self._notifications_dir / f"{notification.id}.json"
        atomic_write_json(path, asdict(notification))

    def _save_rules(self) -> None:
        raw = []
        for rule in self._rules:
            d = asdict(rule)
            d["notification_type"] = rule.notification_type.value
            d["priority"] = rule.priority.value
            raw.append(d)
        atomic_write_json(self._rules_file, raw)

    def _generate_id(self) -> str:
        import secrets

        return secrets.token_hex(8)

    def notify(
        self,
        notification_type: NotificationType,
        priority: NotificationPriority,
        title: str,
        message: str,
        source_module: str = "",
        action_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ProactiveNotification:
        notification = ProactiveNotification(
            id=self._generate_id(),
            type=notification_type,
            priority=priority,
            title=title,
            message=message,
            source_module=source_module,
            action_url=action_url,
            metadata=metadata or {},
        )
        with self._lock:
            self._notifications.append(notification)
            self._save_notification(notification)
        logger.info("Notificacao proativa: [%s] %s", priority.value, title)
        return notification

    def list_notifications(
        self,
        *,
        unread_only: bool = False,
        notification_type: NotificationType | None = None,
        limit: int = 50,
    ) -> list[ProactiveNotification]:
        with self._lock:
            result = list(self._notifications)
            if unread_only:
                result = [n for n in result if not n.read]
            if notification_type:
                result = [n for n in result if n.type == notification_type]
            result.sort(key=lambda n: n.created_at, reverse=True)
            return result[:limit]

    def mark_read(self, notification_id: str) -> bool:
        with self._lock:
            for n in self._notifications:
                if n.id == notification_id:
                    n.read = True
                    self._save_notification(n)
                    return True
        return False

    def mark_all_read(self) -> int:
        count = 0
        with self._lock:
            for n in self._notifications:
                if not n.read:
                    n.read = True
                    self._save_notification(n)
                    count += 1
        return count

    def delete_notification(self, notification_id: str) -> bool:
        with self._lock:
            for i, n in enumerate(self._notifications):
                if n.id == notification_id:
                    self._notifications.pop(i)
                    path = self._notifications_dir / f"{notification_id}.json"
                    if path.exists():
                        path.unlink()
                    return True
        return False

    def unread_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._notifications if not n.read)

    def add_rule(self, rule: NotificationRule) -> NotificationRule:
        with self._lock:
            rule.id = rule.id or self._generate_id()
            self._rules.append(rule)
            self._save_rules()
        return rule

    def list_rules(self) -> list[NotificationRule]:
        with self._lock:
            return list(self._rules)

    def update_rule(self, rule_id: str, **kwargs: Any) -> NotificationRule | None:
        with self._lock:
            for rule in self._rules:
                if rule.id == rule_id:
                    for key, value in kwargs.items():
                        if hasattr(rule, key):
                            setattr(rule, key, value)
                    self._save_rules()
                    return rule
        return None

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            for i, rule in enumerate(self._rules):
                if rule.id == rule_id:
                    self._rules.pop(i)
                    self._save_rules()
                    return True
        return False

    def register_watcher(self, watcher: Callable[[], list[ProactiveNotification]]) -> None:
        self._watchers.append(watcher)

    def run_watchers(self) -> list[ProactiveNotification]:
        new_notifications: list[ProactiveNotification] = []
        for watcher in self._watchers:
            try:
                results = watcher()
                for n in results:
                    with self._lock:
                        self._notifications.append(n)
                        self._save_notification(n)
                    new_notifications.append(n)
            except Exception as exc:
                logger.error("Erro ao executar watcher: %s", exc)
        return new_notifications


def _inventory_watcher() -> list[ProactiveNotification]:
    notifications: list[ProactiveNotification] = []
    try:
        from core.inventory import get_inventory_service

        service = get_inventory_service()
        items = service.get_all_items()
        critical = [item for item in items if item.precisa_repor]
        if critical:
            names = ", ".join(item.nome for item in critical[:5])
            extra = f" e mais {len(critical) - 5}" if len(critical) > 5 else ""
            notifications.append(
                ProactiveNotification(
                    id="",
                    type=NotificationType.INVENTORY,
                    priority=NotificationPriority.HIGH,
                    title=f"Itens criticos no estoque ({len(critical)})",
                    message=f"Os seguintes itens precisam de reposicao: {names}{extra}",
                    source_module="inventory",
                    action_url="/inventory",
                    metadata={"critical_items": [item.nome for item in critical]},
                )
            )
    except Exception as exc:
        logger.debug("Inventory watcher falhou: %s", exc)
    return notifications


def _deadline_watcher() -> list[ProactiveNotification]:
    notifications: list[ProactiveNotification] = []
    try:
        from core.workflows import get_workflow_service

        service = get_workflow_service()
        cases = service.list_cases()
        overdue = [c for c in cases if c.get("overdue")]
        due_soon = [c for c in cases if c.get("due_soon")]
        if overdue:
            names = ", ".join(c["title"] for c in overdue[:5])
            notifications.append(
                ProactiveNotification(
                    id="",
                    type=NotificationType.DEADLINE,
                    priority=NotificationPriority.CRITICAL,
                    title=f"Prazos vencidos ({len(overdue)})",
                    message=f"Os seguintes processos estao com prazo vencido: {names}",
                    source_module="cases",
                    action_url="/cases",
                    metadata={"overdue_cases": [c["title"] for c in overdue]},
                )
            )
        if due_soon:
            names = ", ".join(c["title"] for c in due_soon[:5])
            notifications.append(
                ProactiveNotification(
                    id="",
                    type=NotificationType.DEADLINE,
                    priority=NotificationPriority.MEDIUM,
                    title=f"Prazos proximos ({len(due_soon)})",
                    message=f"Os seguintes processos vencem em breve: {names}",
                    source_module="cases",
                    action_url="/cases",
                    metadata={"due_soon_cases": [c["title"] for c in due_soon]},
                )
            )
    except Exception as exc:
        logger.debug("Deadline watcher falhou: %s", exc)
    return notifications


_proactive_service: ProactiveNotificationService | None = None
_proactive_lock = threading.Lock()


def get_proactive_notification_service() -> ProactiveNotificationService:
    global _proactive_service
    if _proactive_service is None:
        with _proactive_lock:
            if _proactive_service is None:
                _proactive_service = ProactiveNotificationService()
                _proactive_service.register_watcher(_inventory_watcher)
                _proactive_service.register_watcher(_deadline_watcher)
    return _proactive_service


def reset_proactive_notification_service() -> None:
    global _proactive_service
    with _proactive_lock:
        _proactive_service = None
