from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ServiceUnavailable, ValidationError
from .models import AIPlan, PlanStatus
from .prompts import build_daily_prompt, build_weekly_prompt
from .repositories import PlannerRepository

logger = logging.getLogger(__name__)

_repo = PlannerRepository()

REQUIRED_KEYS = {
    'summary', 'recommended_order', 'time_blocks',
    'break_suggestions', 'overdue_risk', 'productivity_score', 'tips',
}

class PlannerService:
    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def create_pending_plan(
        self,
        user,
        plan_type: str,
        plan_date: str,
        available_hours: float,
        work_start_time: str,
        work_end_time: str,
    ) -> AIPlan:
        from apps.tasks.models import Task
        tasks_qs = Task.objects.filter(
            user=user,
            deleted_at__isnull=True,
            status__in=('todo', 'in_progress'),
        ).select_related('category').prefetch_related('tags')
        input_snapshot = [_serialise_task(t) for t in tasks_qs]

        return _repo.create_pending(
            user=user,
            plan_date=plan_date,
            plan_type=plan_type,
            input_tasks=input_snapshot,
            available_hours=available_hours,
            work_start_time=work_start_time,
            work_end_time=work_end_time,
        )

    def generate(self, plan: AIPlan) -> AIPlan:
        tasks = plan.input_tasks
        plan_type = plan.plan_type
        plan_date = str(plan.plan_date)
        avail_hours = float(plan.available_hours)
        work_start = str(plan.work_start_time)
        work_end = str(plan.work_end_time)

        if plan_type == AIPlan.PlanType.DAILY:
            prompt = build_daily_prompt(tasks, plan_date, avail_hours, work_start, work_end)
        else:
            prompt = build_weekly_prompt(tasks, plan_date, avail_hours, work_start, work_end)

        _repo.mark_generating(plan, prompt)
        logger.info(
            'Generating %s AI plan id=%s user=%s tasks=%d',
            plan_type, plan.id, plan.user_id, len(tasks),
        )
        t_start = time.monotonic()
        try:
            raw = self._call_openai(prompt)
        except Exception as exc:
            _repo.mark_failed(plan, str(exc))
            logger.error('OpenAI call failed for plan=%s: %s', plan.id, exc)
            raise ServiceUnavailable(
                detail='AI service is temporarily unavailable. Your plan will retry automatically.'
            )
        ms = int((time.monotonic() - t_start) * 1000)

        try:
            parsed = self._validate_and_enrich(raw, tasks, avail_hours)
        except (ValueError, KeyError) as exc:
            _repo.mark_failed(plan, f'Schema validation failed: {exc}')
            logger.error('AI response schema invalid for plan=%s: %s', plan.id, exc)
            raise ValidationError(
                {'detail': f'AI returned an unexpected response format. Please try again. ({exc})'}
            )
        result = _repo.save_result(plan, parsed, raw, ms)
        logger.info('Plan id=%s completed in %dms score=%s', plan.id, ms, result.overall_score)
        return result

    def get_plan(self, plan_id: Any, user) -> AIPlan:
        try:
            return _repo.get_by_id(plan_id, user)
        except AIPlan.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Plan not found.')

    def get_latest(self, user, plan_type: str) -> AIPlan | None:
        return _repo.latest_for_user(user, plan_type)
    def get_history(self, user, plan_type: str | None = None):
        return _repo.history_for_user(user, plan_type)

    def _call_openai(self, prompt: str, model: str = 'gpt-4o-mini') -> dict:
        models = [model, 'gpt-3.5-turbo-1106']
        last_exc = None

        for attempt, m in enumerate(models):
            try:
                response = self._client.chat.completions.create(
                    model=m,
                    messages=[
                        {
                            'role': 'system',
                            'content': (
                                'You are an expert AI productivity coach. '
                                'Return ONLY valid JSON matching the schema exactly. '
                                'No markdown fences, no explanations, no extra keys.'
                            ),
                        },
                        {'role': 'user', 'content': prompt},
                    ],
                    temperature=0.4,
                    max_tokens=4096,
                    response_format={'type': 'json_object'},
                )
                content = response.choices[0].message.content
                return json.loads(content)
            except Exception as exc:
                last_exc = exc
                logger.warning('OpenAI attempt %d failed (model=%s): %s', attempt + 1, m, exc)
                if attempt < len(models) - 1:
                    time.sleep(1)  # Brief pause before fallback
        raise last_exc

    def _validate_and_enrich(
        self, raw: dict, tasks: list[dict], available_hours: float
    ) -> dict:
        missing = REQUIRED_KEYS - set(raw.keys())
        if missing:
            raise ValueError(f'Missing required keys: {missing}')

        for item in raw.get('recommended_order', []):
            item.setdefault('score', 50)
            item.setdefault('reason', '')
            item.setdefault('suggested_slot', '')

        # Normalise time_blocks
        for block in raw.get('time_blocks', []):
            block.setdefault('task_id', None)
            block.setdefault('notes', '')
            block.setdefault('type', 'work')

        for brk in raw.get('break_suggestions', []):
            brk.setdefault('type', 'short')
            brk.setdefault('reason', '')
            brk.setdefault('duration_minutes', 10)

        risk = raw.get('overdue_risk', {})
        risk.setdefault('risk_level', 'none')
        risk.setdefault('risk_score', 0)
        risk.setdefault('at_risk_tasks', [])
        risk.setdefault('overloaded_days', [])
        risk.setdefault('analysis', '')
        raw['overdue_risk'] = risk

        score = raw.get('productivity_score', {})
        score.setdefault('overall', 50)
        score.setdefault('focus', 50)
        score.setdefault('feasibility', 50)
        score.setdefault('balance', 50)
        score.setdefault('urgency_load', 50)
        score.setdefault('advice', [])
        raw['productivity_score'] = score

        total_est_min = sum(t.get('estimated_minutes', 0) or 0 for t in tasks)
        available_min = available_hours * 60
        if available_min > 0:
            load_ratio = total_est_min / available_min
            computed_feasibility = max(0, min(100, int((1 - max(0, load_ratio - 1)) * 100)))
            if computed_feasibility < score['feasibility']:
                score['feasibility'] = computed_feasibility
                score['overall'] = int((
                    score.get('focus', 50) +
                    score['feasibility'] +
                    score.get('balance', 50) +
                    max(0, 100 - score.get('urgency_load', 50))
                ) / 4)

        return raw

def _serialise_task(task) -> dict:
    return {
        'id': task.id,
        'title': task.title,
        'description': (task.description or '')[:200],
        'priority': task.priority,
        'status': task.status,
        'deadline': task.deadline.isoformat() if task.deadline else None,
        'estimated_minutes': task.estimated_minutes,
        'category': task.category.name if task.category else None,
        'tags': [t.name for t in task.tags.all()],
        'is_overdue': task.is_overdue,
        'recurrence': task.recurrence,
    }
