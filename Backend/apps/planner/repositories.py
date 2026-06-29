from __future__ import annotations
from typing import Any
from django.db.models import QuerySet
from .models import AIPlan, PlanStatus

class PlannerRepository:
    def get_by_id(self, plan_id: Any, user) -> AIPlan:
        return AIPlan.objects.get(id=plan_id, user=user)

    def latest_for_user(self, user, plan_type: str) -> AIPlan | None:
        return (
            AIPlan.objects
            .filter(user=user, plan_type=plan_type, status=PlanStatus.COMPLETED)
            .first()
        )

    def get_for_date(self, user, plan_date: str, plan_type: str) -> AIPlan | None:
        return AIPlan.objects.filter(
            user=user,
            plan_date=plan_date,
            plan_type=plan_type,
            status=PlanStatus.COMPLETED,
        ).first()

    def all_for_user(self, user) -> QuerySet:
        return AIPlan.objects.filter(user=user)

    def history_for_user(self, user, plan_type: str | None = None) -> QuerySet:
        qs = AIPlan.objects.filter(user=user, status=PlanStatus.COMPLETED)
        if plan_type:
            qs = qs.filter(plan_type=plan_type)
        return qs
    
    def create_pending(self, user, plan_date: str, plan_type: str,
                       input_tasks: list, available_hours: float,
                       work_start_time: str, work_end_time: str) -> AIPlan:
        return AIPlan.objects.create(
            user=user,
            plan_date=plan_date,
            plan_type=plan_type,
            status=PlanStatus.PENDING,
            input_tasks=input_tasks,
            available_hours=available_hours,
            work_start_time=work_start_time,
            work_end_time=work_end_time,
        )

    def mark_generating(self, plan: AIPlan, prompt: str) -> AIPlan:
        plan.status = PlanStatus.GENERATING
        plan.prompt_used = prompt
        plan.save(update_fields=['status', 'prompt_used'])
        return plan

    def save_result(self, plan: AIPlan, parsed: dict, raw: dict, ms: int) -> AIPlan:
        plan.status = PlanStatus.COMPLETED
        plan.raw_response = raw
        plan.summary = parsed.get('summary', '')
        plan.recommended_order = parsed.get('recommended_order', [])
        plan.time_blocks = parsed.get('time_blocks', [])
        plan.break_suggestions = parsed.get('break_suggestions', [])
        plan.overdue_risk = parsed.get('overdue_risk', {})
        plan.productivity_score = parsed.get('productivity_score', {})
        plan.tips = parsed.get('tips', [])
        plan.generation_ms = ms
        plan.save(update_fields=[
            'status', 'raw_response', 'summary', 'recommended_order',
            'time_blocks', 'break_suggestions', 'overdue_risk',
            'productivity_score', 'tips', 'generation_ms',
        ])
        return plan

    def mark_failed(self, plan: AIPlan, error: str) -> AIPlan:
        plan.status = PlanStatus.FAILED
        plan.error_message = error
        plan.retry_count = plan.retry_count + 1
        plan.save(update_fields=['status', 'error_message', 'retry_count'])
        return plan
