from dataclasses import dataclass
from datetime import date, datetime, timedelta
from unicodedata import category, normalize

from core.business_records import BusinessRecord, BusinessRecordService, get_business_record_service
from core.modules import MODULE_AGENDA

ACTIVE_AGENDA_STATUSES = {"", "Agendado", "Confirmado", "Remarcar"}
DONE_AGENDA_STATUSES = {"Concluido", "Cancelado"}
DEFAULT_REMINDER_MINUTES = 15


@dataclass(frozen=True)
class AgendaEvent:
    id: str
    title: str
    starts_at: datetime
    status: str
    reminder_minutes: int
    event_type: str = "Outro"
    customer: str = ""
    responsible: str = ""
    location: str = ""
    notes: str = ""
    reminder_sent_at: str = ""

    @property
    def reminder_at(self) -> datetime:
        return self.starts_at - timedelta(minutes=self.reminder_minutes)


class AgendaService:
    """Agenda view over modular business records."""

    def __init__(self, record_service: BusinessRecordService | None = None):
        self.record_service = record_service or get_business_record_service()

    def list_events(self, *, include_done: bool = False) -> list[AgendaEvent]:
        events = []
        for record in self.record_service.list_by_module(MODULE_AGENDA):
            event = self._event_from_record(record)
            if event is None:
                continue
            if not include_done and event.status in DONE_AGENDA_STATUSES:
                continue
            events.append(event)
        return sorted(events, key=lambda event: event.starts_at)

    def upcoming(self, *, now: datetime | None = None, days: int = 14) -> list[AgendaEvent]:
        now = now or datetime.now()
        until = now + timedelta(days=days)
        return [
            event
            for event in self.list_events()
            if now <= event.starts_at <= until and event.status in ACTIVE_AGENDA_STATUSES
        ]

    def due_reminders(self, *, now: datetime | None = None) -> list[AgendaEvent]:
        now = now or datetime.now()
        return [
            event
            for event in self.list_events()
            if event.status in ACTIVE_AGENDA_STATUSES
            and not event.reminder_sent_at
            and event.reminder_at <= now <= event.starts_at + timedelta(hours=12)
        ]

    def mark_reminded(self, event_id: str, *, when: datetime | None = None) -> bool:
        record = self.record_service.get(event_id)
        if record is None or record.module_id != MODULE_AGENDA:
            return False
        fields = dict(record.fields)
        fields["lembrete_enviado_em"] = (when or datetime.now()).strftime("%d/%m/%Y %H:%M")
        self.record_service.save_record(MODULE_AGENDA, record.title, fields, record_id=record.id)
        return True

    def prompt_context(self, *, now: datetime | None = None, limit: int = 8) -> str:
        events = self.upcoming(now=now, days=30)[:limit]
        if not events:
            return (
                "## Agenda Local\n"
                "O Celsius tem acesso local a agenda, mas nao ha compromissos futuros cadastrados."
            )

        lines = [
            "## Agenda Local",
            "O Celsius tem acesso local aos compromissos cadastrados abaixo.",
            "Use estes dados quando o usuario perguntar sobre agenda, prazos, consultas, visitas ou lembretes.",
        ]
        for event in events:
            details = [
                event.starts_at.strftime("%d/%m/%Y %H:%M"),
                event.status or "Agendado",
            ]
            if event.customer:
                details.append(f"cliente: {event.customer}")
            if event.responsible:
                details.append(f"responsavel: {event.responsible}")
            if event.location:
                details.append(f"local: {event.location}")
            lines.append(f"- {event.title}: {' | '.join(details)}")
        return "\n".join(lines)

    def _event_from_record(self, record: BusinessRecord) -> AgendaEvent | None:
        fields = record.fields
        starts_at = parse_agenda_datetime(fields.get("data_hora", ""))
        if starts_at is None:
            return None
        return AgendaEvent(
            id=record.id,
            title=record.title,
            starts_at=starts_at,
            status=fields.get("status", "Agendado").strip() or "Agendado",
            reminder_minutes=_parse_int(
                fields.get("lembrete_minutos", ""), DEFAULT_REMINDER_MINUTES
            ),
            event_type=fields.get("tipo", "Outro").strip() or "Outro",
            customer=fields.get("cliente", "").strip(),
            responsible=fields.get("responsavel", "").strip(),
            location=fields.get("local", "").strip(),
            notes=fields.get("observacoes", "").strip(),
            reminder_sent_at=fields.get("lembrete_enviado_em", "").strip(),
        )


def parse_agenda_datetime(value: str, *, today: date | None = None) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None

    normalized = _strip_accents(raw).replace("T", " ").replace(" as ", " ")
    formats = (
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%H:%M",
    )
    base_day = today or date.today()
    for fmt in formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        if fmt == "%H:%M":
            return datetime.combine(base_day, parsed.time())
        return parsed
    return None


def _parse_int(value: str, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _strip_accents(value: str) -> str:
    decomposed = normalize("NFD", value)
    return "".join(char for char in decomposed if category(char) != "Mn")


_agenda_service: AgendaService | None = None


def get_agenda_service() -> AgendaService:
    global _agenda_service
    if _agenda_service is None:
        _agenda_service = AgendaService()
    return _agenda_service


def reset_agenda_service():
    global _agenda_service
    _agenda_service = None
