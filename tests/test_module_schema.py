from core.module_schema import get_record_schema, module_primary_field, module_summary
from core.modules import (
    MODULE_AGENDA,
    MODULE_CASES_DEADLINES,
    MODULE_CUSTOMERS,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_NOTIFICATIONS,
    MODULE_PRODUCTS_SERVICES,
    MODULE_QUOTES,
    MODULE_REPORTS,
    MODULE_SUPPLIERS,
)


class TestModuleRecordSchema:
    def test_core_business_modules_have_structured_schemas(self):
        module_ids = (
            MODULE_KNOWLEDGE,
            MODULE_CUSTOMERS,
            MODULE_SUPPLIERS,
            MODULE_PRODUCTS_SERVICES,
            MODULE_QUOTES,
            MODULE_FINANCE,
            MODULE_REPORTS,
            MODULE_AGENDA,
            MODULE_CASES_DEADLINES,
            MODULE_NOTIFICATIONS,
        )

        for module_id in module_ids:
            schema = get_record_schema(module_id)

            assert schema is not None
            assert schema.primary_field in {field.key for field in schema.fields}
            assert any(
                field.key == schema.primary_field and field.required for field in schema.fields
            )
            assert schema.workflow.default_status in schema.workflow.statuses

    def test_finance_schema_uses_erp_fields(self):
        schema = get_record_schema(MODULE_FINANCE)
        field_keys = {field.key for field in schema.fields}

        assert {"tipo", "valor", "vencimento", "status", "centro_custo"} <= field_keys

    def test_quotes_schema_uses_commercial_pipeline_fields(self):
        schema = get_record_schema(MODULE_QUOTES)
        field_keys = {field.key for field in schema.fields}

        assert {"cliente", "validade", "valor", "status", "itens"} <= field_keys

    def test_agenda_schema_declares_reminder_fields(self):
        schema = get_record_schema(MODULE_AGENDA)
        field_keys = {field.key for field in schema.fields}

        assert {"data_hora", "lembrete_minutos", "status"} <= field_keys

    def test_notifications_schema_declares_external_channel_fields(self):
        schema = get_record_schema(MODULE_NOTIFICATIONS)
        field_keys = {field.key for field in schema.fields}

        assert {"canal", "destinatario", "mensagem", "consentimento"} <= field_keys
        assert "Pendente configuracao" in schema.workflow.statuses

    def test_primary_field_and_summary_helpers(self):
        assert module_primary_field(MODULE_CUSTOMERS) == "nome"

        summary = module_summary(
            {"nome": "Cliente A", "status": "Ativo", "telefone": "11999990000"},
            MODULE_CUSTOMERS,
        )

        assert "Cliente A" in summary
        assert "Ativo" in summary
