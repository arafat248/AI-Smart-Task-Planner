from __future__ import annotations
import pytest
from datetime import timedelta
from django.utils import timezone
from apps.notifications.reminder_services import ReminderScheduler, ReminderManager
from apps.notifications.models import Notification
from apps.tasks.models import Task

@pytest.fixture
def scheduler():
    return ReminderScheduler()


@pytest.fixture
def manager():
    return ReminderManager()

@pytest.mark.django_db
class TestReminderScheduler:
    def test_schedules_reminder_for_task_with_deadline(self, user, scheduler):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Task', status='todo', priority='medium',
            deadline=now + timedelta(days=1),
        )
        result = scheduler.schedule(task)
        assert result is True
        task.refresh_from_db()
        assert task.reminder_at is not None
        assert task.reminder_at < task.deadline

    def test_does_not_schedule_without_deadline(self, user, scheduler):
        task = Task.objects.create(user=user, title='No deadline', status='todo', priority='medium')
        result = scheduler.schedule(task)
        assert result is False
        task.refresh_from_db()
        assert task.reminder_at is None

    def test_unschedules_completed_task(self, user, scheduler):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Done', status='todo', priority='medium',
            deadline=now + timedelta(days=1),
            reminder_at=now + timedelta(hours=23),
        )
        task.status = 'completed'
        task.save()
        scheduler.unschedule(task)
        task.refresh_from_db()
        assert task.reminder_at is None

    def test_does_not_schedule_past_deadline(self, user, scheduler):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Past', status='todo', priority='medium',
            deadline=now - timedelta(hours=1),
        )
        result = scheduler.schedule(task)
        assert result is True
        task.refresh_from_db()
        # reminder_at should be in the future (now + 1 min), not in the past
        assert task.reminder_at >= now

    def test_leaves_existing_reminder_at_alone(self, user, scheduler):
        now = timezone.now()
        existing = now + timedelta(hours=2)
        task = Task.objects.create(
            user=user, title='Task', status='todo', priority='medium',
            deadline=now + timedelta(days=1),
            reminder_at=existing,
        )
        result = scheduler.schedule(task)
        assert result is True
        task.refresh_from_db()
        assert task.reminder_at == existing

    def test_clears_reminder_on_soft_delete(self, user, scheduler):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Deleted', status='todo', priority='medium',
            deadline=now + timedelta(days=1),
            reminder_at=now + timedelta(hours=23),
        )
        task.soft_delete()
        result = scheduler.schedule(task)
        assert result is False
        task.refresh_from_db()
        assert task.reminder_at is None

@pytest.mark.django_db
class TestReminderManager:
    def test_upcoming_returns_tasks_in_window(self, user, manager):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Soon', status='todo', priority='medium',
            deadline=now + timedelta(hours=2),
            reminder_at=now + timedelta(minutes=30),
        )
        result = manager.upcoming(user, hours=24)
        assert len(result) >= 1
        assert any(r['id'] == task.id for r in result)

    def test_upcoming_excludes_completed(self, user, manager):
        now = timezone.now()
        Task.objects.create(
            user=user, title='Done', status='completed', priority='medium',
            deadline=now + timedelta(hours=2),
            reminder_at=now + timedelta(minutes=30),
        )
        result = manager.upcoming(user, hours=24)
        assert not any(r['title'] == 'Done' for r in result)

    def test_overdue_returns_overdue_tasks(self, user, manager):
        now = timezone.now()
        task = Task.objects.create(
            user=user, title='Late', status='todo', priority='high',
            deadline=now - timedelta(hours=1),
        )
        result = manager.overdue(user)
        assert len(result) >= 1
        assert any(r['id'] == task.id for r in result)

    def test_overdue_excludes_completed(self, user, manager):
        now = timezone.now()
        Task.objects.create(
            user=user, title='Done but late', status='completed', priority='low',
            deadline=now - timedelta(hours=1),
        )
        result = manager.overdue(user)
        assert not any(r['title'] == 'Done but late' for r in result)

    def test_history_returns_past_notifications(self, user, manager):
        now = timezone.now()
        task = Task.objects.create(user=user, title='Task', status='todo', priority='medium')
        Notification.objects.create(user=user, task=task, type='reminder', message='Test')
        result = manager.history(user, limit=10)
        assert len(result) >= 1
        assert result[0]['message'] == 'Test'

    def test_hours_until_deadline_computed(self, user, manager):
        now = timezone.now()
        Task.objects.create(
            user=user, title='Soon', status='todo', priority='medium',
            deadline=now + timedelta(hours=5),
        )
        result = manager.upcoming(user, hours=24)
        entry = next(r for r in result if r['title'] == 'Soon')
        assert entry['hours_until_deadline'] is not None
        assert 4 <= entry['hours_until_deadline'] <= 6
