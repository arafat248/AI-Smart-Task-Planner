from __future__ import annotations
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.tasks.models import Task
from .reminder_services import ReminderScheduler

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Task)
def on_task_saved(sender, instance: Task, created: bool, **kwargs):
    scheduler = ReminderScheduler()

    if instance.deleted_at is not None:
        scheduler.unschedule(instance)
        return

    if instance.status in (Task.Status.COMPLETED, Task.Status.CANCELLED):
        scheduler.unschedule(instance)
        return

    if instance.deadline is not None:
        scheduler.schedule(instance)
    else:
        scheduler.unschedule(instance)

@receiver(post_delete, sender=Task)
def on_task_deleted(sender, instance: Task, **kwargs):
    """Clean up any pending reminders when a task is hard-deleted."""
    ReminderScheduler().unschedule(instance)
