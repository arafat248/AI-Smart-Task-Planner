from __future__ import annotations
import logging
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from apps.tasks.models import Task
from .models import Notification
from .push_provider import get_push_provider

logger = logging.getLogger(__name__)

@shared_task(queue='reminders.deadline', bind=True, max_retries=3, default_retry_delay=60)
def send_deadline_reminder(self, task_id: int) -> dict:
    try:
        task = (
            Task.objects
            .select_related('user', 'category')
            .prefetch_related('tags')
            .get(id=task_id, deleted_at__isnull=True)
        )
    except Task.DoesNotExist:
        logger.warning('send_deadline_reminder: task %d not found or deleted', task_id)
        return {'task_id': task_id, 'sent': False, 'reason': 'not_found'}

    if task.status in (Task.Status.COMPLETED, Task.Status.CANCELLED):
        logger.info('send_deadline_reminder: task %d already %s — skipping', task_id, task.status)
        return {'task_id': task_id, 'sent': False, 'reason': f'status_{task.status}'}

    user = task.user

    notif, created = Notification.objects.get_or_create(
        user=user,
        task=task,
        type='reminder',
        read_at__isnull=True,
        defaults={'message': _reminder_message(task)},
    )
    if not created:
        logger.debug('send_deadline_reminder: in-app notification already exists for task %d', task_id)

    email_sent = _send_reminder_email(task, user)

    push_sent = _send_reminder_push(task, user)

    logger.info(
        'send_deadline_reminder: task=%d user=%s email=%s push=%s in_app=%s',
        task_id, user.email, email_sent, push_sent, created,
    )
    return {
        'task_id': task_id,
        'sent': True,
        'email': email_sent,
        'push': push_sent,
        'in_app': created,
    }

@shared_task(queue='reminders.deadline')
def scan_deadline_reminders() -> dict:
    now = timezone.now()
    window_end = now + timedelta(minutes=5)

    task_ids = (
        Task.objects
        .filter(
            reminder_at__gte=now,
            reminder_at__lt=window_end,
            status__in=(Task.Status.TODO, Task.Status.IN_PROGRESS),
            deleted_at__isnull=True,
        )
        .values_list('id', flat=True)
    )

    count = 0
    for tid in task_ids:
        send_deadline_reminder.delay(tid)
        count += 1

    logger.info('scan_deadline_reminders: %d tasks queued for reminder', count)
    return {'queued': count, 'window_start': now.isoformat(), 'window_end': window_end.isoformat()}

@shared_task(queue='reminders.overdue', bind=True, max_retries=3, default_retry_delay=60)
def send_overdue_alert(self, task_id: int) -> dict:
    try:
        task = Task.objects.select_related('user').get(id=task_id, deleted_at__isnull=True)
    except Task.DoesNotExist:
        return {'task_id': task_id, 'sent': False, 'reason': 'not_found'}

    if task.status in (Task.Status.COMPLETED, Task.Status.CANCELLED):
        return {'task_id': task_id, 'sent': False, 'reason': f'status_{task.status}'}

    user = task.user
    today = timezone.now().date()

    already_exists = Notification.objects.filter(
        user=user, task=task, type='overdue',
        created_at__date=today,
    ).exists()
    if already_exists:
        logger.debug('send_overdue_alert: already notified today for task %d', task_id)
        return {'task_id': task_id, 'sent': False, 'reason': 'already_notified_today'}

    notif = Notification.objects.create(
        user=user, task=task, type='overdue',
        message=_overdue_message(task),
    )
    email_sent = _send_overdue_email(task, user)
    push_sent = _send_overdue_push(task, user)
    logger.info(
        'send_overdue_alert: task=%d user=%s email=%s push=%s',
        task_id, user.email, email_sent, push_sent,
    )

    return {
        'task_id': task_id,
        'sent': True,
        'email': email_sent,
        'push': push_sent,
        'in_app': True,
    }


@shared_task(queue='reminders.overdue')
def scan_overdue_tasks() -> dict:
    now = timezone.now()

    task_ids = (
        Task.objects
        .filter(
            deadline__lt=now,
            status__in=(Task.Status.TODO, Task.Status.IN_PROGRESS),
            deleted_at__isnull=True,
        )
        .exclude(
            notifications__type='overdue',
            notifications__created_at__date=now.date(),
        )
        .values_list('id', flat=True)
    )

    count = 0
    for tid in task_ids:
        send_overdue_alert.delay(tid)
        count += 1

    logger.info('scan_overdue_tasks: %d tasks queued for overdue alert', count)
    return {'queued': count, 'scanned_at': now.isoformat()}

@shared_task(queue='reminders.push', bind=True, max_retries=5, default_retry_delay=30)
def deliver_push_notification(self, user_id: int, title: str, body: str, data: dict | None = None) -> dict:
    """
    Generic push delivery task.
    Uses the configured PushProvider (FCM by default).
    Retries on transient failures (network, FCM 5xx).
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning('deliver_push_notification: user %d not found', user_id)
        return {'user_id': user_id, 'sent': False, 'reason': 'user_not_found'}

    provider = get_push_provider()
    result = provider.send(
        user=user,
        title=title,
        body=body,
        data=data or {},
    )

    if not result['success'] and result.get('retryable'):
        raise self.retry(exc=Exception(result.get('error', 'Push failed')))

    logger.info('deliver_push_notification: user=%d sent=%s', user_id, result['success'])
    return {'user_id': user_id, **result}

@shared_task(queue='reminders.deadline')
def send_daily_digest(user_id: int) -> dict:
    """
    Send a daily summary email of upcoming and overdue tasks.
    Can be triggered by a nightly beat schedule.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return {'user_id': user_id, 'sent': False, 'reason': 'user_not_found'}

    now = timezone.now()
    tomorrow = now + timedelta(days=1)

    upcoming = (
        Task.objects
        .filter(
            user=user,
            deadline__gte=now,
            deadline__lt=tomorrow,
            status__in=(Task.Status.TODO, Task.Status.IN_PROGRESS),
            deleted_at__isnull=True,
        )
        .order_by('deadline')
    )

    overdue = (
        Task.objects
        .filter(
            user=user,
            deadline__lt=now,
            status__in=(Task.Status.TODO, Task.Status.IN_PROGRESS),
            deleted_at__isnull=True,
        )
        .order_by('deadline')
    )

    if not upcoming.exists() and not overdue.exists():
        return {'user_id': user_id, 'sent': False, 'reason': 'nothing_to_report'}

    html = render_to_string('emails/daily_digest.html', {
        'user': user,
        'upcoming': upcoming,
        'overdue': overdue,
        'now': now,
    })

    send_mail(
        subject='Your Daily Task Digest',
        message='',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html,
        fail_silently=True,
    )

    logger.info('send_daily_digest: user=%d upcoming=%d overdue=%d', user_id, upcoming.count(), overdue.count())
    return {
        'user_id': user_id,
        'sent': True,
        'upcoming_count': upcoming.count(),
        'overdue_count': overdue.count(),
    }

def _reminder_message(task: Task) -> str:
    return (
        f'Reminder: "{task.title}" is due '
        f'{task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "soon"}.'
    )

def _overdue_message(task: Task) -> str:
    return (
        f'"{task.title}" is overdue '
        f'(was due {task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "previously"}).'
    )

def _send_reminder_email(task: Task, user) -> bool:
    if not user.email:
        return False
    try:
        send_mail(
            subject=f'Reminder: {task.title}',
            message=_reminder_message(task),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.warning('Failed to send reminder email for task %d: %s', task.id, exc)
        return False

def _send_overdue_email(task: Task, user) -> bool:
    if not user.email:
        return False
    try:
        send_mail(
            subject=f'Overdue: {task.title}',
            message=_overdue_message(task),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.warning('Failed to send overdue email for task %d: %s', task.id, exc)
        return False

def _send_reminder_push(task: Task, user) -> bool:
    return _queue_push(
        user=user,
        title=f'Reminder: {task.title}',
        body=_reminder_message(task),
        data={'task_id': task.id, 'type': 'reminder'},
    )

def _send_overdue_push(task: Task, user) -> bool:
    return _queue_push(
        user=user,
        title=f'Overdue: {task.title}',
        body=_overdue_message(task),
        data={'task_id': task.id, 'type': 'overdue'},
    )

def _queue_push(user, title: str, body: str, data: dict) -> bool:
    """Queue a push notification via Celery (non-blocking)."""
    if not getattr(user, 'push_enabled', True):
        return False
    deliver_push_notification.delay(
        user_id=user.id,
        title=title,
        body=body,
        data=data,
    )
    return True
