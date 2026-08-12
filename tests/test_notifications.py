from types import SimpleNamespace

import pytest

from core.notifications import EXTERNAL_SERVICE_NOTICE, NotificationService


def _settings(**overrides):
    defaults = {
        "enabled": False,
        "external_services_allowed": False,
        "require_confirmation": True,
        "default_channel": "whatsapp",
        "whatsapp_provider": "meta_cloud_api",
        "email_provider": "",
        "sms_provider": "",
    }
    defaults.update(overrides)
    return SimpleNamespace(notifications=SimpleNamespace(**defaults))


class TestNotificationService:
    def test_creates_and_reloads_local_draft(self, tmp_path):
        data_file = tmp_path / "notifications.json"
        service = NotificationService(data_file=data_file, settings=_settings())

        draft = service.create_draft(
            "whatsapp",
            "+5511999990000",
            "Seu orcamento esta pronto.",
            source_module="quotes",
        )

        reloaded = NotificationService(data_file=data_file, settings=_settings())
        messages = reloaded.list_all()

        assert len(messages) == 1
        assert messages[0].id == draft.id
        assert messages[0].channel == "whatsapp"
        assert messages[0].source_module == "quotes"

    def test_blocks_external_send_when_not_allowed(self, tmp_path):
        service = NotificationService(
            data_file=tmp_path / "notifications.json", settings=_settings(enabled=True)
        )

        result = service.send("whatsapp", "+5511999990000", "Lembrete de consulta.")

        assert result.ok is False
        assert result.status == "blocked_external"
        assert EXTERNAL_SERVICE_NOTICE in result.message

    def test_reports_missing_provider_for_email(self, tmp_path):
        service = NotificationService(
            data_file=tmp_path / "notifications.json",
            settings=_settings(enabled=True, external_services_allowed=True),
        )

        result = service.send("email", "cliente@example.com", "Mensagem")

        assert result.ok is False
        assert result.status == "not_configured"

    def test_provider_is_prepared_but_not_sent_yet(self, tmp_path):
        service = NotificationService(
            data_file=tmp_path / "notifications.json",
            settings=_settings(enabled=True, external_services_allowed=True),
        )

        result = service.send("whatsapp", "+5511999990000", "Mensagem")

        assert result.ok is False
        assert result.status == "provider_not_implemented"

    def test_requires_recipient_and_message(self, tmp_path):
        service = NotificationService(
            data_file=tmp_path / "notifications.json", settings=_settings()
        )

        with pytest.raises(ValueError, match="Destinatario"):
            service.create_draft("sms", "", "Mensagem")

        with pytest.raises(ValueError, match="Mensagem"):
            service.create_draft("sms", "+5511999990000", "")
