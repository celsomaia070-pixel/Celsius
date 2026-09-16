"""Tests for proactive notification system."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.proactive_notifications import (
    NotificationPriority,
    NotificationRule,
    NotificationType,
    ProactiveNotificationService,
    ProactiveNotification,
    reset_proactive_notification_service,
)


@pytest.fixture
def tmp_data(tmp_path: Path):
    reset_proactive_notification_service()
    svc = ProactiveNotificationService(data_dir=tmp_path)
    yield svc
    reset_proactive_notification_service()


class TestNotifications:
    def test_create_notification(self, tmp_data: ProactiveNotificationService):
        n = tmp_data.notify(
            NotificationType.SYSTEM,
            NotificationPriority.MEDIUM,
            "Teste",
            "Mensagem de teste",
        )
        assert n.id
        assert n.title == "Teste"
        assert n.priority == NotificationPriority.MEDIUM

    def test_list_notifications(self, tmp_data: ProactiveNotificationService):
        tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "A", "Msg A")
        tmp_data.notify(NotificationType.INVENTORY, NotificationPriority.HIGH, "B", "Msg B")
        all_n = tmp_data.list_notifications()
        assert len(all_n) == 2

    def test_filter_unread(self, tmp_data: ProactiveNotificationService):
        n1 = tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "A", "Msg A")
        tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "B", "Msg B")
        tmp_data.mark_read(n1.id)
        unread = tmp_data.list_notifications(unread_only=True)
        assert len(unread) == 1

    def test_filter_by_type(self, tmp_data: ProactiveNotificationService):
        tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "A", "Msg A")
        tmp_data.notify(NotificationType.INVENTORY, NotificationPriority.HIGH, "B", "Msg B")
        system = tmp_data.list_notifications(notification_type=NotificationType.SYSTEM)
        assert len(system) == 1

    def test_mark_read(self, tmp_data: ProactiveNotificationService):
        n = tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "A", "Msg A")
        assert tmp_data.mark_read(n.id) is True
        updated = [x for x in tmp_data.list_notifications() if x.id == n.id][0]
        assert updated.read is True

    def test_mark_all_read(self, tmp_data: ProactiveNotificationService):
        tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "A", "Msg A")
        tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "B", "Msg B")
        count = tmp_data.mark_all_read()
        assert count == 2
        assert tmp_data.unread_count() == 0

    def test_unread_count(self, tmp_data: ProactiveNotificationService):
        tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "A", "Msg A")
        tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "B", "Msg B")
        assert tmp_data.unread_count() == 2

    def test_delete_notification(self, tmp_data: ProactiveNotificationService):
        n = tmp_data.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "A", "Msg A")
        assert tmp_data.delete_notification(n.id) is True
        assert len(tmp_data.list_notifications()) == 0

    def test_persistence(self, tmp_path: Path):
        svc1 = ProactiveNotificationService(data_dir=tmp_path)
        svc1.notify(NotificationType.SYSTEM, NotificationPriority.LOW, "A", "Msg A")
        svc2 = ProactiveNotificationService(data_dir=tmp_path)
        assert len(svc2.list_notifications()) == 1


class TestRules:
    def test_add_rule(self, tmp_data: ProactiveNotificationService):
        rule = NotificationRule(
            id="",
            name="Teste",
            notification_type=NotificationType.INVENTORY,
            priority=NotificationPriority.HIGH,
            source_module="inventory",
            condition="critical_items > 0",
            message_template="Existem {count} itens criticos",
        )
        created = tmp_data.add_rule(rule)
        assert created.id
        assert created.name == "Teste"

    def test_list_rules(self, tmp_data: ProactiveNotificationService):
        rule = NotificationRule(
            id="",
            name="Teste",
            notification_type=NotificationType.INVENTORY,
            priority=NotificationPriority.HIGH,
            source_module="inventory",
            condition="critical_items > 0",
            message_template="Msg",
        )
        tmp_data.add_rule(rule)
        rules = tmp_data.list_rules()
        assert len(rules) == 1

    def test_update_rule(self, tmp_data: ProactiveNotificationService):
        rule = NotificationRule(
            id="",
            name="Teste",
            notification_type=NotificationType.INVENTORY,
            priority=NotificationPriority.HIGH,
            source_module="inventory",
            condition="critical_items > 0",
            message_template="Msg",
        )
        created = tmp_data.add_rule(rule)
        updated = tmp_data.update_rule(created.id, enabled=False)
        assert updated is not None
        assert updated.enabled is False

    def test_delete_rule(self, tmp_data: ProactiveNotificationService):
        rule = NotificationRule(
            id="",
            name="Teste",
            notification_type=NotificationType.INVENTORY,
            priority=NotificationPriority.HIGH,
            source_module="inventory",
            condition="critical_items > 0",
            message_template="Msg",
        )
        created = tmp_data.add_rule(rule)
        assert tmp_data.delete_rule(created.id) is True
        assert len(tmp_data.list_rules()) == 0


class TestWatchers:
    def test_register_watcher(self, tmp_data: ProactiveNotificationService):
        def my_watcher():
            return [
                ProactiveNotification(
                    id="",
                    type=NotificationType.CUSTOM,
                    priority=NotificationPriority.LOW,
                    title="Watcher Alert",
                    message="Teste",
                    source_module="test",
                )
            ]

        tmp_data.register_watcher(my_watcher)
        new = tmp_data.run_watchers()
        assert len(new) == 1
        assert new[0].title == "Watcher Alert"
