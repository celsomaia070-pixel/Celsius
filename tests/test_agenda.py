from datetime import date, datetime, timedelta

from core.agenda import AgendaService, parse_agenda_datetime
from core.business_records import BusinessRecordService


class TestAgendaService:
    def test_parses_common_local_dates(self):
        parsed = parse_agenda_datetime("31/07/2026 14:30")

        assert parsed == datetime(2026, 7, 31, 14, 30)

    def test_parses_time_using_today(self):
        parsed = parse_agenda_datetime("09:15", today=date(2026, 7, 29))

        assert parsed == datetime(2026, 7, 29, 9, 15)

    def test_lists_upcoming_agenda_records(self, tmp_path):
        records = BusinessRecordService(data_file=tmp_path / "business_records.json")
        service = AgendaService(record_service=records)
        now = datetime(2026, 7, 29, 10, 0)

        records.save_record(
            "agenda",
            title="Consulta com cliente",
            fields={
                "titulo": "Consulta com cliente",
                "data_hora": "29/07/2026 11:00",
                "cliente": "Cliente A",
                "status": "Agendado",
            },
        )

        upcoming = service.upcoming(now=now, days=1)

        assert len(upcoming) == 1
        assert upcoming[0].title == "Consulta com cliente"
        assert upcoming[0].customer == "Cliente A"

    def test_due_reminder_is_marked_once(self, tmp_path):
        records = BusinessRecordService(data_file=tmp_path / "business_records.json")
        service = AgendaService(record_service=records)
        now = datetime(2026, 7, 29, 10, 0)
        record = records.save_record(
            "agenda",
            title="Reuniao de estoque",
            fields={
                "titulo": "Reuniao de estoque",
                "data_hora": (now + timedelta(minutes=10)).strftime("%d/%m/%Y %H:%M"),
                "lembrete_minutos": "15",
                "status": "Agendado",
            },
        )

        reminders = service.due_reminders(now=now)

        assert [event.id for event in reminders] == [record.id]
        assert service.mark_reminded(record.id, when=now) is True
        assert service.due_reminders(now=now) == []

    def test_prompt_context_exposes_agenda_to_llm(self, tmp_path):
        records = BusinessRecordService(data_file=tmp_path / "business_records.json")
        service = AgendaService(record_service=records)
        records.save_record(
            "agenda",
            title="Visita tecnica",
            fields={
                "titulo": "Visita tecnica",
                "data_hora": "30/07/2026 15:00",
                "local": "Cliente Maia",
                "status": "Confirmado",
            },
        )

        context = service.prompt_context(now=datetime(2026, 7, 29, 10, 0))

        assert "Agenda Local" in context
        assert "Visita tecnica" in context
        assert "Cliente Maia" in context
