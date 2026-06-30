from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def spawn_recurring_tasks(self):
    """Midnight job: clone recurring tasks that were due today."""
    from .repositories import TaskRepository
    from django.utils import timezone

    repo = TaskRepository()
    today = timezone.now().date()
    tasks = repo.get_recurring_due_today()
    spawned = 0

    for task in tasks:
        from datetime import timedelta
        delta_map = {'daily': timedelta(days=1), 'weekly': timedelta(weeks=1), 'monthly': timedelta(days=30)}
        delta = delta_map.get(task.recurrence)
        if not delta:
            continue
        repo.create(
            user=task.user,
            category=task.category,
            title=task.title,
            description=task.description,
            priority=task.priority,
            estimated_minutes=task.estimated_minutes,
            due_date=today + delta,
            recurrence=task.recurrence,
        )
        spawned += 1

    logger.info('spawn_recurring_tasks: %d tasks created for %s', spawned, today)
    return spawned
