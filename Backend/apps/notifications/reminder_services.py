from __future__ import annotations
import logging
from datetime import timedelta
from django.utils import timezone
from apps.tasks.models import Task
from .models import Notification
from .reminder_tasks import send_deadline_reminder, send_overdue_alert

logger = logging.getLogger(__name__)

DEFAULT_REMINDER_MINUTES = 60  # 1 hour before deadline

class ReminderScheduler:
    def schedule(self, task: Task) -> bool:
        """
        Compute reminder_at and store it on the task.
        Returns True if a reminder was scheduled, False otherwise.
        """
        if task.deleted_at is not None:
            return False
        if task.deadline is None:
            self._clear_reminder(task)
            return False
        if task.status in (Task.Status.COMPLETED, Task.Status.CANCELLED):
            self._clear_reminder(task)
            return False

        # If reminder_at is already set and looks reasonable, leave it alone
        if task.reminder_at is not None and task.reminder_at < task.deadline:
            logger.debug('ReminderScheduler: task %d already has reminder_at', task.id)
            return True

        # Default: remind 1 hour before deadline
        reminder_at = task.deadline - timedelta(minutes=DEFAULT_REMINDER_MINUTES)
        # Don't schedule in the past
        if reminder_at < timezone.now():
            reminder_at = timezone.now() + timedelta(minutes=1)

        task.reminder_at = reminder_at
        task.save(update_fields=['reminder_at'])

        logger.info('ReminderScheduler: task %d reminder_at=%s', task.id, reminder_at.isoformat())
        return True

    def unschedule(self, task: Task) -> None:
        """Cancel any pending reminder for this task."""
        self._clear_reminder(task)
        Notification.objects.filter(
            task=task, type='reminder', read_at__isnull=True,
        ).update(read_at=timezone.now())
        logger.info('ReminderScheduler: unscheduled task %d', task.id)

    def _clear_reminder(self, task: Task) -> None:
        if task.reminder_at is not None:
            task.reminder_at = None
            task.save(update_fields=['reminder_at'])

class ReminderManager:
    """
    Query and manage reminders for a user.
    Used by the frontend "Reminders" view.
    """

    def upcoming(self, user, hours: int = 24) -> list[dict]:
        """All tasks with a reminder in the next N hours."""
        now = timezone.now()
        end = now + timedelta(hours=hours)
        tasks = (
            Task.objects
            .filter(
                user=user,
                reminder_at__gte=now,
                reminder_at__lte=end,
                status__in=(Task.Status.TODO, Task.Status.IN_PROGRESS),
                deleted_at__isnull=True,
            )
            .select_related('category')
            .order_by('reminder_at')
        )
        return [self._to_dict(t) for t in tasks]

    def overdue(self, user) -> list[dict]:
        """All overdue tasks for this user."""
        now = timezone.now()
        tasks = (
            Task.objects
            .filter(
                user=user,
                deadline__lt=now,
                status__in=(Task.Status.TODO, Task.Status.IN_PROGRESS),
                deleted_at__isnull=True,
            )
            .select_related('category')
            .order_by('deadline')
        )
        return [self._to_dict(t) for t in tasks]

    def history(self, user, limit: int = 30) -> list[dict]:
        """Past reminder notifications (sent + read)."""
        notifs = (
            Notification.objects
            .filter(user=user, type='reminder')
            .select_related('task')
            .order_by('-created_at')[:limit]
        )
        return [
            {
                'id': n.id,
                'message': n.message,
                'task_id': n.task_id,
                'task_title': n.task.title if n.task else None,
                'read': n.read_at is not None,
                'created_at': n.created_at.isoformat(),
            }
            for n in notifs
        ]

    def _to_dict(self, task: Task) -> dict:
        return {
            'id': task.id,
            'title': task.title,
            'deadline': task.deadline.isoformat() if task.deadline else None,
            'reminder_at': task.reminder_at.isoformat() if task.reminder_at else None,
            'status': task.status,
            'priority': task.priority,
            'category': (
                {'id': task.category.id, 'name': task.category.name, 'color': task.category.color}
                if task.category else None
            ),
            'hours_until_deadline': (
                round((task.deadline - timezone.now()).total_seconds() / 3600, 1)
                if task.deadline else None
            ),
        }
