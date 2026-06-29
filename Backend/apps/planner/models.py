from __future__ import annotations
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.mixins import TimestampMixin

class PlanStatus(models.TextChoices):
    PENDING = 'pending', _('Pending')
    GENERATING = 'generating', _('Generating')
    COMPLETED = 'completed', _('Completed')
    FAILED = 'failed', _('Failed')

class AIPlan(TimestampMixin):
    class PlanType(models.TextChoices):
        DAILY  = 'daily',  _('Daily')
        WEEKLY = 'weekly', _('Weekly')

    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='ai_plans', db_index=True,
    )

    plan_date = models.DateField(db_index=True, help_text=_('Start date of this plan.'))
    plan_type = models.CharField(max_length=10, choices=PlanType.choices, default=PlanType.DAILY)
    status = models.CharField(max_length=20, choices=PlanStatus.choices, default=PlanStatus.PENDING)
    input_tasks = models.JSONField(default=list, help_text=_('Serialised task snapshot sent to AI.'))
    available_hours = models.DecimalField(max_digits=4, decimal_places=1, default=8.0)
    work_start_time = models.TimeField(default='09:00')
    work_end_time = models.TimeField(default='17:00')
    prompt_used = models.TextField(blank=True)
    recommended_order = models.JSONField(default=list)
    time_blocks = models.JSONField(default=list)
    break_suggestions = models.JSONField(default=list)
    overdue_risk = models.JSONField(default=dict)
    productivity_score = models.JSONField(default=dict)
    summary = models.TextField(blank=True)
    tips = models.JSONField(default=list)
    raw_response = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    generation_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'planner_aiplan'
        ordering = ['-plan_date', '-created_at']
        indexes = [
            models.Index(fields=['user', '-plan_date'], name='plan_user_date_idx'),
            models.Index(fields=['user', 'plan_type'],  name='plan_user_type_idx'),
            models.Index(fields=['user', 'status'],     name='plan_user_status_idx'),
        ]

    def __str__(self) -> str:
        return f'AIPlan<{self.user.email} {self.plan_date} {self.plan_type} [{self.status}]>'

    @property
    def is_ready(self) -> bool:
        return self.status == PlanStatus.COMPLETED

    @property
    def overall_score(self) -> int | None:
        return self.productivity_score.get('overall') if self.productivity_score else None
