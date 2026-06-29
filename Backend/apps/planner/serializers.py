from __future__ import annotations
from rest_framework import serializers
from .models import AIPlan

class GeneratePlanSerializer(serializers.Serializer):
    plan_type = serializers.ChoiceField(
        choices=AIPlan.PlanType.choices,
        default=AIPlan.PlanType.DAILY,
        help_text='daily or weekly',
    )
    plan_date = serializers.DateField(
        help_text='Start date for the plan (ISO-8601). Defaults to today if omitted.',
        required=False,
    )
    available_hours = serializers.DecimalField(
        max_digits=4, decimal_places=1,
        min_value=0.5, max_value=24.0,
        default=8.0,
        help_text='Total working hours available (0.5–24).',
    )
    work_start_time = serializers.TimeField(
        default='09:00',
        help_text='Work start time, e.g. "09:00".',
    )
    work_end_time = serializers.TimeField(
        default='17:00',
        help_text='Work end time, e.g. "17:00".',
    )

    def validate(self, data: dict) -> dict:
        from django.utils import timezone
        if not data.get('plan_date'):
            data['plan_date'] = timezone.now().date()

        start = data.get('work_start_time')
        end = data.get('work_end_time')
        if start and end and start >= end:
            raise serializers.ValidationError(
                {'work_end_time': 'Work end time must be after work start time.'}
            )
        return data

class PlanQuerySerializer(serializers.Serializer):
    plan_type = serializers.ChoiceField(
        choices=AIPlan.PlanType.choices,
        required=False,
        default=AIPlan.PlanType.DAILY,
    )
    plan_date = serializers.DateField(required=False)

class RecommendedTaskSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()
    title = serializers.CharField()
    rank = serializers.IntegerField()
    reason = serializers.CharField()
    suggested_slot = serializers.CharField()
    score = serializers.IntegerField(min_value=0, max_value=100)

class TimeBlockSerializer(serializers.Serializer):
    start = serializers.CharField(help_text='HH:MM 24h')
    end = serializers.CharField(help_text='HH:MM 24h')
    title = serializers.CharField()
    type = serializers.ChoiceField(choices=['work', 'break', 'lunch', 'buffer', 'admin'])
    task_id = serializers.IntegerField(allow_null=True)
    notes = serializers.CharField(allow_blank=True)

class BreakSuggestionSerializer(serializers.Serializer):
    after_block = serializers.IntegerField()
    time = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    type = serializers.ChoiceField(
        choices=['short', 'long', 'lunch', 'walk', 'meditation']
    )
    reason = serializers.CharField()

class AtRiskTaskSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()
    title = serializers.CharField()
    deadline = serializers.CharField()
    risk_reason = serializers.CharField()
    mitigation = serializers.CharField()

class OverdueRiskSerializer(serializers.Serializer):
    risk_level = serializers.ChoiceField(choices=['none', 'low', 'medium', 'high', 'critical'])
    risk_score = serializers.IntegerField(min_value=0, max_value=100)
    at_risk_tasks = AtRiskTaskSerializer(many=True)
    overloaded_days = serializers.ListField(child=serializers.CharField())
    analysis = serializers.CharField()

class ProductivityScoreSerializer(serializers.Serializer):
    overall = serializers.IntegerField(min_value=0, max_value=100)
    focus = serializers.IntegerField(min_value=0, max_value=100)
    feasibility = serializers.IntegerField(min_value=0, max_value=100)
    balance = serializers.IntegerField(min_value=0, max_value=100)
    urgency_load = serializers.IntegerField(min_value=0, max_value=100)
    advice = serializers.ListField(child=serializers.CharField())

class AIPlanDetailSerializer(serializers.ModelSerializer):
    recommended_order = RecommendedTaskSerializer(many=True)
    time_blocks = TimeBlockSerializer(many=True)
    break_suggestions = BreakSuggestionSerializer(many=True)
    overdue_risk = OverdueRiskSerializer()
    productivity_score = ProductivityScoreSerializer()
    overall_score = serializers.IntegerField(read_only=True)

    class Meta:
        model = AIPlan
        fields = [
            'id',
            'plan_date',
            'plan_type',
            'status',
            'available_hours',
            'work_start_time',
            'work_end_time',
            'summary',
            'recommended_order',
            'time_blocks',
            'break_suggestions',
            'overdue_risk',
            'productivity_score',
            'overall_score',
            'tips',
            'generation_ms',
            'error_message',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

class AIPlanListSerializer(serializers.ModelSerializer):
    overall_score = serializers.IntegerField(read_only=True)
    task_count = serializers.SerializerMethodField()

    class Meta:
        model = AIPlan
        fields = [
            'id', 'plan_date', 'plan_type', 'status',
            'overall_score', 'task_count', 'generation_ms', 'created_at',
        ]
        read_only_fields = fields

    def get_task_count(self, obj: AIPlan) -> int:
        return len(obj.input_tasks)
