import json
import logging
import os
import tempfile
import threading
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from core.settings import get_settings

logger = logging.getLogger(__name__)

NotificationChannel = Literal["whatsapp", "email", "sms"]
NotificationStatus = Literal[
    "draft",
    "blocked_external",
    "disabled",
    "not_configured",
    "provider_not_implemented",
    "sent",
]

EXTERNAL_SERVICE_NOTICE = "Este recurso usa internet e servico externo."


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


@dataclass
class NotificationMessage:
    id: str
    channel: NotificationChannel
    recipient: str
    body: str
    subject: str = ""
    source_module: str = ""
    provider: str = ""
    status: NotificationStatus = "draft"
    error: str = ""
    requires_external_service: bool = True
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = _now()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationMessage":
        return cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})


@dataclass(frozen=True)
class NotificationResult:
    ok: bool
    status: NotificationStatus
    message: str
    notification_id: str


class NotificationService:
    """Local notification history and provider gate for external channels."""

    def __init__(self, data_file: Path | None = None, settings=None):
        self.settings = settings or get_settings()
        self.data_file = (
            Path(data_file) if data_file else self.settings.data_dir / "notifications.json"
        )
        self._messages: dict[str, NotificationMessage] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        with self._lock:
            self._messages = {}
            if not self.data_file.exists():
                return
            try:
                raw = json.loads(self.data_file.read_text(encoding="utf-8"))
                messages_raw = raw.get("messages", []) if isinstance(raw, dict) else []
                for message_data in messages_raw:
                    message = NotificationMessage.from_dict(message_data)
                    self._messages[message.id] = message
            except Exception as exc:
                logger.error("Erro ao ler notificacoes: %s", exc)

    def _save(self):
        with self._lock:
            data = {"messages": [message.to_dict() for message in self._messages.values()]}
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{self.data_file.name}.",
                suffix=".tmp",
                dir=self.data_file.parent,
                text=True,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as file:
                    json.dump(data, file, ensure_ascii=False, indent=2)
                os.replace(tmp_name, self.data_file)
            except Exception as exc:
                logger.error("Erro ao salvar notificacoes: %s", exc)
                with suppress(OSError):
                    os.unlink(tmp_name)

    def list_all(self) -> list[NotificationMessage]:
        with self._lock:
            return sorted(self._messages.values(), key=lambda item: item.updated_at, reverse=True)

    def get(self, notification_id: str) -> NotificationMessage | None:
        with self._lock:
            return self._messages.get(notification_id)

    def create_draft(
        self,
        channel: NotificationChannel,
        recipient: str,
        body: str,
        *,
        subject: str = "",
        source_module: str = "",
        metadata: dict[str, str] | None = None,
    ) -> NotificationMessage:
        self._validate_payload(channel, recipient, body)
        with self._lock:
            message = NotificationMessage(
                id=str(uuid.uuid4())[:8],
                channel=channel,
                recipient=recipient.strip(),
                body=body.strip(),
                subject=subject.strip(),
                source_module=source_module.strip(),
                provider=self._provider_for(channel),
                metadata=metadata or {},
            )
            self._messages[message.id] = message
            self._save()
            return message

    def send(
        self,
        channel: NotificationChannel,
        recipient: str,
        body: str,
        *,
        subject: str = "",
        source_module: str = "",
        metadata: dict[str, str] | None = None,
    ) -> NotificationResult:
        message = self.create_draft(
            channel,
            recipient,
            body,
            subject=subject,
            source_module=source_module,
            metadata=metadata,
        )
        status, text = self._send_status(channel)
        with self._lock:
            message.status = status
            message.error = "" if status == "sent" else text
            message.updated_at = _now()
            self._save()
        return NotificationResult(
            ok=status == "sent",
            status=status,
            message=text,
            notification_id=message.id,
        )

    def _send_status(self, channel: NotificationChannel) -> tuple[NotificationStatus, str]:
        notifications = self.settings.notifications
        if not notifications.enabled:
            return "disabled", "Notificacoes estao desativadas nas configuracoes."
        if not notifications.external_services_allowed:
            return (
                "blocked_external",
                f"{EXTERNAL_SERVICE_NOTICE} Ative servicos externos nas configuracoes para enviar.",
            )
        provider = self._provider_for(channel)
        if not provider:
            return "not_configured", f"Canal {channel} ainda nao possui provedor configurado."
        return (
            "provider_not_implemented",
            f"Provedor {provider} esta preparado na configuracao, mas o envio real ainda nao foi implementado.",
        )

    def _provider_for(self, channel: NotificationChannel) -> str:
        notifications = self.settings.notifications
        if channel == "whatsapp":
            return notifications.whatsapp_provider.strip()
        if channel == "email":
            return notifications.email_provider.strip()
        if channel == "sms":
            return notifications.sms_provider.strip()
        return ""

    def _validate_payload(self, channel: str, recipient: str, body: str) -> None:
        if channel not in {"whatsapp", "email", "sms"}:
            raise ValueError("Canal de notificacao desconhecido.")
        if not recipient.strip():
            raise ValueError("Destinatario e obrigatorio.")
        if not body.strip():
            raise ValueError("Mensagem e obrigatoria.")


_notification_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


def reset_notification_service():
    global _notification_service
    _notification_service = None
