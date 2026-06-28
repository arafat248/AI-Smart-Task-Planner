from __future__ import annotations
from rest_framework import serializers

class SummarySerializer(serializers.Serializer):
    total                    = serializers.IntegerField()
    completed                = serializers.IntegerField()
    in_progress              = serializers.IntegerField()
    todo                     = serializers.IntegerField()
    cancelled                = serializers.IntegerField()
    pending                  = serializers.IntegerField(
        help_text='todo + in_progress'
    )
    overdue                  = serializers.IntegerField()
    due_soon                 = serializers.IntegerField(
        help_text='Tasks due within the next 24 hours'
    )
    ai_generated             = serializers.IntegerField()
    productivity_pct         = serializers.FloatField(
        help_text='completed / (total - cancelled) × 100'
    )
    total_estimated_hours    = serializers.FloatField()
    completed_estimated_hours = serializers.FloatField()

class PriorityBreakdownSerializer(serializers.Serializer):
    priority  = serializers.CharField()
    total     = serializers.IntegerField()
    completed = serializers.IntegerField()
    pending   = serializers.IntegerField()

class CategoryBreakdownSerializer(serializers.Serializer):
    id        = serializers.IntegerField()
    name      = serializers.CharField()
    color     = serializers.CharField()
    icon      = serializers.CharField()
    total     = serializers.IntegerField()
    completed = serializers.IntegerField()
    pending   = serializers.IntegerField()
    overdue   = serializers.IntegerField()

class TagBreakdownSerializer(serializers.Serializer):
    id        = serializers.IntegerField()
    name      = serializers.CharField()
    color     = serializers.CharField()
    total     = serializers.IntegerField()
    completed = serializers.IntegerField()

class StreakSerializer(serializers.Serializer):
    current_streak   = serializers.IntegerField()
    longest_streak   = serializers.IntegerField()
    last_active_date = serializers.CharField(allow_null=True)

class RecentCategorySerializer(serializers.Serializer):
    name  = serializers.CharField()
    color = serializers.CharField()

class RecentCompletionSerializer(serializers.Serializer):
    id           = serializers.IntegerField()
    title        = serializers.CharField()
    priority     = serializers.CharField()
    completed_at = serializers.CharField()
    category     = RecentCategorySerializer(allow_null=True)

class UpcomingDeadlineSerializer(serializers.Serializer):
    id              = serializers.IntegerField()
    title           = serializers.CharField()
    priority        = serializers.CharField()
    status          = serializers.CharField()
    deadline        = serializers.CharField()
    hours_remaining = serializers.FloatField()
    category        = RecentCategorySerializer(allow_null=True)

class DailyDataPointSerializer(serializers.Serializer):
    date      = serializers.CharField()
    completed = serializers.IntegerField()
    created   = serializers.IntegerField()

class WeeklyDataPointSerializer(serializers.Serializer):
    week_start = serializers.CharField()
    completed  = serializers.IntegerField()
    created    = serializers.IntegerField()

class MonthlyDataPointSerializer(serializers.Serializer):
    month     = serializers.CharField(help_text='YYYY-MM')
    label     = serializers.CharField(help_text='e.g. Jun 2026')
    completed = serializers.IntegerField()
    created   = serializers.IntegerField()

class OverviewResponseSerializer(serializers.Serializer):
    summary             = SummarySerializer()
    priorities          = PriorityBreakdownSerializer(many=True)
    categories          = CategoryBreakdownSerializer(many=True)
    tags                = TagBreakdownSerializer(many=True)
    streak              = StreakSerializer()
    upcoming_deadlines  = UpcomingDeadlineSerializer(many=True)
    recent_completions  = RecentCompletionSerializer(many=True)

class WeeklyProgressResponseSerializer(serializers.Serializer):
    daily  = DailyDataPointSerializer(many=True)
    weekly = WeeklyDataPointSerializer(many=True)

class MonthlyProgressResponseSerializer(serializers.Serializer):
    monthly              = MonthlyDataPointSerializer(many=True)
    month_on_month_delta = serializers.FloatField(
        allow_null=True,
        help_text='% change vs previous month (null if insufficient data)',
    )

class FullAnalyticsResponseSerializer(serializers.Serializer):
    summary              = SummarySerializer()
    priorities           = PriorityBreakdownSerializer(many=True)
    categories           = CategoryBreakdownSerializer(many=True)
    tags                 = TagBreakdownSerializer(many=True)
    streak               = StreakSerializer()
    upcoming_deadlines   = UpcomingDeadlineSerializer(many=True)
    recent_completions   = RecentCompletionSerializer(many=True)
    daily_progress       = DailyDataPointSerializer(many=True)
    weekly_progress      = WeeklyDataPointSerializer(many=True)
    monthly_progress     = MonthlyDataPointSerializer(many=True)
    month_on_month_delta = serializers.FloatField(allow_null=True)

class WeeklyQuerySerializer(serializers.Serializer):
    weeks = serializers.IntegerField(
        min_value=1, max_value=52, default=8,
        help_text='Number of weeks to include (1–52)',
    )

class MonthlyQuerySerializer(serializers.Serializer):
    months = serializers.IntegerField(
        min_value=1, max_value=24, default=6,
        help_text='Number of months to include (1–24)',
    )

class FullAnalyticsQuerySerializer(serializers.Serializer):
    weeks  = serializers.IntegerField(min_value=1, max_value=52, default=8)
    months = serializers.IntegerField(min_value=1, max_value=24, default=6)
