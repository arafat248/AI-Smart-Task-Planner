from __future__ import annotations
import pytest
from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from apps.notifications.reminder_tasks import (
    send_deadline_reminder,
    scan_deadline_reminders,
    send_overdue_alert,
    scan_overdue_tasks,
    deliver_push_notification,
    send_daily_digest,
)
from apps.notifications.models import Notification
from apps.tasks.models import Task


@pytest.mark.django_db
class TestSendDeadlineReminder:
    def test_sends_in_app_notification(self, user, task_with_deadline):
        result = send_deadline_reminder(task_with_deadline.id)
        assert result['sent'] is True
        assert result['in_app'] is True
        assert Notification.objects.filter(task=task_with_deadline, type='reminder').exists()

    def test_skips_completed_task(self, user, task_with_deadline):
        task_with_deadline.status = 'completed'
        task_with_deadline.save()
        result = send_deadline_reminder(task_with_deadline.id)
        assert result['sent'] is False
        assert result['reason'] == 'status_completed'

    def test_skips_deleted_task(self, user, task_with_deadline):
        task_with_deadline.soft_delete()
        result = send_deadline_reminder(task_with_deadline.id)
        assert result['sent'] is False
        assert result['reason'] == 'not_found'

    def test_idempotent_same_task(self, user, task_with_deadline):
        send_deadline_reminder(task_with_deadline.id)
        send_deadline_reminder(task_with_deadline.id)
        # Should only create one in-app notification
        count = Notification.objects.filter(task=task_with_deadline, type='reminder').count()
        assert count == 1

    def test_sends_email(self, user, task_with_deadline):
        with patch('apps.notifications.reminder_tasks.send_mail') as mock_mail:
            mock_mail.return_value = 1
            result = send_deadline_reminder(task_with_deadline.id)
            assert result['email'] is True
            mock_mail.assert_called_once()

    def test_queues_push(self, user, task_with_deadline):
        with patch('apps.notifications.reminder_tasks.deliver_push_notification.delay') as mock_push:
            result = send_deadline_reminder(task_with_deadline.id)
            assert result['push'] is True
            mock_push.assert_called_once()

@pytest.mark.django_db
class TestScanDeadlineReminders:
    def test_finds_task_in_window(self, user):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Soon', status='todo', priority='medium',
            deadline=now + timedelta(hours=2),
            reminder_at=now + timedelta(minutes=2),
        )
        with patch('apps.notifications.reminder_tasks.send_deadline_reminder.delay') as mock_delay:
            scan_deadline_reminders()
            mock_delay.assert_called_once_with(task.id)

    def test_ignores_task_outside_window(self, user):
        now = timezone.now()
        Task.objects.create(
            user=user, title='Later', status='todo', priority='medium',
            deadline=now + timedelta(hours=10),
            reminder_at=now + timedelta(hours=9),
        )
        with patch('apps.notifications.reminder_tasks.send_deadline_reminder.delay') as mock_delay:
            result = scan_deadline_reminders()
            mock_delay.assert_not_called()
            assert result['queued'] == 0

@pytest.mark.django_db
class TestSendOverdueAlert:
    def test_sends_overdue_notification(self, user):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Late', status='todo', priority='high',
            deadline=now - timedelta(days=1),
        )
        result = send_overdue_alert(task.id)
        assert result['sent'] is True
        assert Notification.objects.filter(task=task, type='overdue').exists()

    def test_idempotent_same_day(self, user):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Late', status='todo', priority='high',
            deadline=now - timedelta(days=1),
        )
        send_overdue_alert(task.id)
        result = send_overdue_alert(task.id)
        assert result['sent'] is False
        assert result['reason'] == 'already_notified_today'

    def test_skips_completed(self, user):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Done', status='completed', priority='low',
            deadline=now - timedelta(days=1),
        )
        result = send_overdue_alert(task.id)
        assert result['sent'] is False

@pytest.mark.django_db
class TestScanOverdueTasks:
    def test_finds_overdue_task(self, user):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Late', status='todo', priority='high',
            deadline=now - timedelta(hours=1),
        )
        with patch('apps.notifications.reminder_tasks.send_overdue_alert.delay') as mock_delay:
            scan_overdue_tasks()
            mock_delay.assert_called_once_with(task.id)

    def test_ignores_on_time_task(self, user):
        now = timezone.now()
        Task.objects.create(
            user=user, title='On time', status='todo', priority='medium',
            deadline=now + timedelta(days=1),
        )
        with patch('apps.notifications.reminder_tasks.send_overdue_alert.delay') as mock_delay:
            scan_overdue_tasks()
            mock_delay.assert_not_called()

@pytest.mark.django_db
class TestDeliverPushNotification:
    def test_no_op_provider_logs(self, user):
        result = deliver_push_notification(user.id, 'Test', 'Body', {'key': 'val'})
        assert result['success'] is True
        assert result['provider'] == 'noop'

    def test_missing_user(self):
        result = deliver_push_notification(99999, 'Test', 'Body', {})
        assert result['sent'] is False
        assert result['reason'] == 'user_not_found'

@pytest.mark.django_db
class TestSendDailyDigest:

    def test_nothing_to_report(self, user):
        result = send_daily_digest(user.id)
        assert result['sent'] is False
        assert result['reason'] == 'nothing_to_report'

    def test_sends_with_upcoming(self, user):
        now = timezone.now()
        Task.objects.create(
            user=user, title='Today', status='todo', priority='medium',
            deadline=now + timedelta(hours=2),
        )
        with patch('apps.notifications.reminder_tasks.send_mail') as mock_mail:
            mock_mail.return_value = 1
            result = send_daily_digest(user.id)
            assert result['sent'] is True
            mock_mail.assert_called_once()
