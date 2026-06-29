from __future__ import annotations
from django.utils import timezone
from .models import Notification

class NotificationService:
    def create(self, user, message: str, notif_type: str = 'system', task=None) -> Notification:
        return Notification.objects.create(
            user=user, message=message, type=notif_type, task=task
        )

    def schedule_reminder(self, task) -> None:
        self.create(
            user=task.user,
            message=f'Reminder: "{task.title}" is due on {task.due_date}.',
            notif_type='reminder',
            task=task,
        )

    def cancel_reminder(self, task) -> None:
        Notification.objects.filter(task=task, type='reminder', read_at__isnull=True).update(
            read_at=timezone.now()
        )

    def mark_overdue(self, task) -> None:
        self.create(
            user=task.user,
            message=f'"{task.title}" is overdue (was due {task.due_date}).',
            notif_type='overdue',
            task=task,
        )
    def mark_read(self, notification: Notification) -> None:
        notification.read_at = timezone.now()
        notification.save(update_fields=['read_at'])

    def mark_all_read(self, user) -> int:
        return Notification.objects.filter(user=user, read_at__isnull=True).update(
            read_at=timezone.now()
        )
