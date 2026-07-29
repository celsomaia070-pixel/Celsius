"""Tests for generic modular business records."""

from core.business_records import BusinessRecordService


class TestBusinessRecordService:
    def test_saves_and_reloads_record(self, tmp_path):
        data_file = tmp_path / "business_records.json"
        service = BusinessRecordService(data_file=data_file)

        record = service.save_record(
            "customers",
            title="Cliente Maia",
            fields={"nome": "Cliente Maia", "telefone": "11999990000"},
        )

        reloaded = BusinessRecordService(data_file=data_file)
        records = reloaded.list_by_module("customers")

        assert len(records) == 1
        assert records[0].id == record.id
        assert records[0].fields["telefone"] == "11999990000"

    def test_search_and_delete_record(self, tmp_path):
        service = BusinessRecordService(data_file=tmp_path / "business_records.json")
        record = service.save_record(
            "agenda",
            title="Consulta inicial",
            fields={"titulo": "Consulta inicial", "responsavel": "Celso"},
        )

        assert service.search("agenda", "celso")[0].id == record.id
        assert service.delete(record.id) is True
        assert service.list_by_module("agenda") == []
