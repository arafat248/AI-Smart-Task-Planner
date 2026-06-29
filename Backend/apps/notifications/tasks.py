from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task
def check_overdue_tasks():
    from django.utils import timezone
    from apps.tasks.models import Task
    from apps.notifications.services import NotificationService
    from apps.notifications.models import Notification

    today = timezone.now().date()
    overdue = Task.objects.filter(
        due_date__lt=today,
        status__in=('todo', 'in_progress'),
        deleted_at__isnull=True,
    ).exclude(
        notifications__type='overdue',
        notifications__created_at__date=today,
    ).select_related('user')

    svc = NotificationService()
    count = 0
    for task in overdue:
        svc.mark_overdue(task)
        count += 1

    logger.info('check_overdue_tasks: %d notifications created', count)
    return count

@shared_task
def send_due_reminders():
    """Run every hour — email reminders for tasks due within the next hour."""
    from django.utils import timezone
    from datetime import timedelta
    from apps.tasks.models import Task
    from django.core.mail import send_mail

    now = timezone.now()
    window = now + timedelta(hours=1)
    tasks = Task.objects.filter(
        reminder_at__gte=now,
        reminder_at__lte=window,
        status__in=('todo', 'in_progress'),
        deleted_at__isnull=True,
    ).select_related('user')

    for task in tasks:
        send_mail(
            subject=f'Reminder: {task.title}',
            message=f'Your task "{task.title}" is due soon ({task.due_date}).',
            from_email=None,
            recipient_list=[task.user.email],
            fail_silently=True,
        )
