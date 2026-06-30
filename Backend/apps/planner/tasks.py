from __future__ import annotations
import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30, 
    acks_late=True, 
    reject_on_worker_lost=True,
)
def generate_plan_async(self, plan_id: int):
    from apps.planner.models import AIPlan, PlanStatus
    from apps.planner.services import PlannerService

    try:
        plan = AIPlan.objects.get(id=plan_id)
    except AIPlan.DoesNotExist:
        logger.error('generate_plan_async: plan_id=%s not found, discarding task', plan_id)
        return

    if plan.status == PlanStatus.COMPLETED:
        logger.info('generate_plan_async: plan_id=%s already completed, skipping', plan_id)
        return

    try:
        svc = PlannerService()
        svc.generate(plan)
        logger.info('generate_plan_async: plan_id=%s completed successfully', plan_id)

    except Exception as exc:
        retry_in = 30 * (2 ** self.request.retries)   # 30s, 60s, 120s
        logger.warning(
            'generate_plan_async: plan_id=%s failed (attempt %d/%d): %s. Retry in %ds.',
            plan_id, self.request.retries + 1, self.max_retries + 1, exc, retry_in,
        )
        try:
            raise self.retry(exc=exc, countdown=retry_in)
        except MaxRetriesExceededError:
            logger.error(
                'generate_plan_async: plan_id=%s exhausted all retries. Marking as FAILED.',
                plan_id,
            )
            plan.refresh_from_db()
            plan.status = PlanStatus.FAILED
            plan.error_message = f'Generation failed after {self.max_retries + 1} attempts: {exc}'
            plan.save(update_fields=['status', 'error_message'])
