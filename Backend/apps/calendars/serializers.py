from __future__ import annotations
from rest_framework import serializers

class DailyQuerySerializer(serializers.Serializer):
    date = serializers.DateField(
        required=False,
        help_text='Target date (ISO-8601, e.g. 2026-06-25). Defaults to today.',
    )

class WeeklyQuerySerializer(serializers.Serializer):
    week_start = serializers.DateField(
        required=False,
        help_text=(
            'Monday of the target week (ISO-8601). '
            'Defaults to the Monday of the current week.'
        ),
    )

    def validate_week_start(self, value):
        if value.weekday() != 0:
            from datetime import timedelta
            value = value - timedelta(days=value.weekday())
        return value

class MonthlyQuerySerializer(serializers.Serializer):
    year = serializers.IntegerField(
        required=False,
        min_value=2000, max_value=2100,
        help_text='4-digit year. Defaults to current year.',
    )
    month = serializers.IntegerField(
        required=False,
        min_value=1, max_value=12,
        help_text='Month number 1–12. Defaults to current month.',
    )

class RangeQuerySerializer(serializers.Serializer):
    start = serializers.DateTimeField(
        help_text='Range start (ISO-8601 datetime, inclusive).',
    )
    end = serializers.DateTimeField(
        help_text='Range end (ISO-8601 datetime, exclusive).',
    )
    status = serializers.MultipleChoiceField(
        choices=['todo', 'in_progress', 'completed', 'cancelled'],
        required=False,
        default=list,
        help_text='Filter by one or more statuses.',
    )
    priority = serializers.MultipleChoiceField(
        choices=['low', 'medium', 'high', 'urgent'],
        required=False,
        default=list,
        help_text='Filter by one or more priorities.',
    )
    category = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text='Filter by category ID.',
    )
    include_no_deadline = serializers.BooleanField(
        required=False,
        default=False,
        help_text='Include tasks with no deadline as all-day events on today.',
    )

    def validate(self, data):
        if data['start'] >= data['end']:
            raise serializers.ValidationError(
                {'end': 'Range end must be after range start.'}
            )
        return data

class OverdueQuerySerializer(serializers.Serializer):
    priority = serializers.MultipleChoiceField(
        choices=['low', 'medium', 'high', 'urgent'],
        required=False,
        default=list,
        help_text='Filter overdue tasks by priority.',
    )

class EventCategorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    color = serializers.CharField()
    icon = serializers.CharField()

class EventTagSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    color = serializers.CharField()

class ExtendedPropsSerializer(serializers.Serializer):
    taskId = serializers.IntegerField()
    description = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    priority = serializers.CharField()
    isOverdue = serializers.BooleanField()
    aiGenerated = serializers.BooleanField()
    recurrence = serializers.CharField()
    estimatedTime = serializers.CharField(allow_null=True)
    estimatedMinutes = serializers.IntegerField(allow_null=True)
    reminderAt = serializers.CharField(allow_null=True)
    completedAt = serializers.CharField(allow_null=True)
    createdAt = serializers.CharField()
    category = EventCategorySerializer(allow_null=True)
    tags = EventTagSerializer(many=True)

class CalendarEventSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    start = serializers.CharField(allow_null=True)
    end = serializers.CharField(allow_null=True)
    allDay = serializers.BooleanField()
    backgroundColor = serializers.CharField()
    borderColor = serializers.CharField()
    textColor = serializers.CharField()
    classNames = serializers.ListField(child=serializers.CharField())
    rrule = serializers.CharField(required=False)
    duration = serializers.CharField(required=False)
    extendedProps = ExtendedPropsSerializer()

class OverdueMetaSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    critical = serializers.IntegerField(help_text='Overdue by more than 7 days')
    by_priority = serializers.DictField(child=serializers.IntegerField())
    oldest_deadline = serializers.CharField(allow_null=True)

class CalendarResponseSerializer(serializers.Serializer):
    events = CalendarEventSerializer(many=True)
    total = serializers.IntegerField()
    range_start = serializers.CharField(allow_null=True)
    range_end = serializers.CharField(allow_null=True)
    view = serializers.CharField(help_text='daily | weekly | monthly | range | overdue')

class OverdueResponseSerializer(serializers.Serializer):
    events = CalendarEventSerializer(many=True)
    meta = OverdueMetaSerializer()
