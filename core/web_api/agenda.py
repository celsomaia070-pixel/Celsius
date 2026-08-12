"""HTTP contracts for the local company agenda and persistent reminders."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.agenda import AgendaEvent, parse_agenda_datetime
from core.modules import MODULE_AGENDA

router = APIRouter(prefix="/agenda", tags=["agenda"])


class AgendaCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    event_type: str = Field(default="Outro", max_length=60)
    starts_at: str = Field(min_length=1, max_length=40)
    customer: str = Field(default="", max_length=180)
    responsible: str = Field(default="", max_length=180)
    location: str = Field(default="", max_length=240)
    reminder_minutes: int = Field(default=15, ge=0, le=43_200)
    status: str = Field(default="Agendado", max_length=40)
    notes: str = Field(default="", max_length=5_000)


class AgendaUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    event_type: str | None = Field(default=None, max_length=60)
    starts_at: str | None = Field(default=None, min_length=1, max_length=40)
    customer: str | None = Field(default=None, max_length=180)
    responsible: str | None = Field(default=None, max_length=180)
    location: str | None = Field(default=None, max_length=240)
    reminder_minutes: int | None = Field(default=None, ge=0, le=43_200)
    status: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=5_000)


def agenda_event_payload(event: AgendaEvent, *, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    return {
        "id": event.id,
        "title": event.title,
        "starts_at": event.starts_at.isoformat(timespec="minutes"),
        "status": event.status,
        "event_type": event.event_type,
        "reminder_minutes": event.reminder_minutes,
        "reminder_at": event.reminder_at.isoformat(timespec="minutes"),
        "reminder_due": (
            not event.reminder_sent_at
            and event.reminder_at <= now <= event.starts_at + timedelta(hours=12)
        ),
        "reminder_acknowledged": bool(event.reminder_sent_at),
        "customer": event.customer,
        "responsible": event.responsible,
        "location": event.location,
        "notes": event.notes,
    }


def _record_fields(payload: AgendaCreateRequest | AgendaUpdateRequest) -> dict[str, str]:
    values = payload.model_dump(exclude_none=True)
    mapping = {
        "event_type": "tipo",
        "starts_at": "data_hora",
        "customer": "cliente",
        "responsible": "responsavel",
        "location": "local",
        "reminder_minutes": "lembrete_minutos",
        "status": "status",
        "notes": "observacoes",
    }
    fields = {}
    for source, target in mapping.items():
        if source in values:
            fields[target] = str(values[source]).strip()
    return fields


def _validated_starts_at(value: str) -> datetime:
    parsed = parse_agenda_datetime(value)
    if parsed is None:
        raise HTTPException(
            status_code=422,
            detail="Informe uma data e hora valida para o compromisso.",
        )
    return parsed


def _find_event(request: Request, event_id: str) -> AgendaEvent:
    event = next(
        (
            item
            for item in request.app.state.agenda_service.list_events(include_done=True)
            if item.id == event_id
        ),
        None,
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Compromisso nao encontrado.")
    return event


@router.get("")
def list_agenda(request: Request, include_done: bool = True) -> dict:
    events = request.app.state.agenda_service.list_events(include_done=include_done)
    return {
        "ok": True,
        "items": [agenda_event_payload(event) for event in events],
        "count": len(events),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_agenda_event(payload: AgendaCreateRequest, request: Request) -> dict:
    starts_at = _validated_starts_at(payload.starts_at)
    fields = _record_fields(payload)
    fields["data_hora"] = starts_at.strftime("%d/%m/%Y %H:%M")
    fields["titulo"] = payload.title.strip()
    record = request.app.state.agenda_service.record_service.save_record(
        MODULE_AGENDA,
        payload.title,
        fields,
    )
    event = _find_event(request, record.id)
    item = agenda_event_payload(event)
    request.app.state.event_hub.publish("agenda.changed", {"action": "created", "event": item})
    return {"ok": True, "event": item}


@router.patch("/{event_id}")
def update_agenda_event(event_id: str, payload: AgendaUpdateRequest, request: Request) -> dict:
    record = request.app.state.agenda_service.record_service.get(event_id)
    if record is None or record.module_id != MODULE_AGENDA:
        raise HTTPException(status_code=404, detail="Compromisso nao encontrado.")

    fields = dict(record.fields)
    updates = _record_fields(payload)
    if payload.starts_at is not None:
        starts_at = _validated_starts_at(payload.starts_at)
        updates["data_hora"] = starts_at.strftime("%d/%m/%Y %H:%M")
    schedule_changed = any(
        key in updates and updates[key] != fields.get(key, "")
        for key in ("data_hora", "lembrete_minutos")
    )
    fields.update(updates)
    if schedule_changed:
        fields.pop("lembrete_enviado_em", None)
    title = payload.title.strip() if payload.title is not None else record.title
    fields["titulo"] = title
    request.app.state.agenda_service.record_service.save_record(
        MODULE_AGENDA,
        title,
        fields,
        record_id=record.id,
    )
    event = _find_event(request, event_id)
    item = agenda_event_payload(event)
    request.app.state.event_hub.publish("agenda.changed", {"action": "updated", "event": item})
    return {"ok": True, "event": item}


@router.delete("/{event_id}")
def delete_agenda_event(event_id: str, request: Request) -> dict:
    record = request.app.state.agenda_service.record_service.get(event_id)
    if record is None or record.module_id != MODULE_AGENDA:
        raise HTTPException(status_code=404, detail="Compromisso nao encontrado.")
    request.app.state.agenda_service.record_service.delete(event_id)
    request.app.state.pending_agenda_reminders.discard(event_id)
    request.app.state.event_hub.publish(
        "agenda.changed",
        {"action": "deleted", "event_id": event_id},
    )
    return {"ok": True, "deleted": event_id}


@router.get("/reminders/due")
def due_agenda_reminders(request: Request) -> dict:
    events = request.app.state.agenda_service.due_reminders()
    request.app.state.pending_agenda_reminders.update(event.id for event in events)
    return {
        "ok": True,
        "items": [agenda_event_payload(event) for event in events],
        "count": len(events),
    }


@router.post("/{event_id}/acknowledge")
def acknowledge_agenda_reminder(event_id: str, request: Request) -> dict:
    if not request.app.state.agenda_service.mark_reminded(event_id):
        raise HTTPException(status_code=404, detail="Compromisso nao encontrado.")
    request.app.state.pending_agenda_reminders.discard(event_id)
    request.app.state.event_hub.publish(
        "agenda.reminder.acknowledged",
        {"event_id": event_id},
    )
    return {"ok": True, "acknowledged": event_id}
