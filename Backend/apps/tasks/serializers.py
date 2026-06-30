from __future__ import annotations
from datetime import timedelta
import bleach
from django.utils import timezone
from rest_framework import serializers
from .models import Category, Tag, Task

ALLOWED_TAGS = ['br', 'p', 'strong', 'em', 'u', 'ul', 'ol', 'li', 'a']
ALLOWED_ATTRS = {'a': ['href', 'title']}

class TagSerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True)
    class Meta:
        model = Tag
        fields = ['id', 'name', 'color', 'task_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'task_count', 'created_at', 'updated_at']

    def validate_name(self, value: str) -> str:
        return value.strip()

    def validate_color(self, value: str) -> str:
        if not value.startswith('#') or len(value) not in (4, 7):
            raise serializers.ValidationError('Color must be a valid hex code, e.g. #3B82F6.')
        return value.upper()

class CategorySerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'color', 'icon', 'description',
            'task_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'task_count', 'created_at', 'updated_at']

    def validate_name(self, value: str) -> str:
        return value.strip()

    def validate_color(self, value: str) -> str:
        if not value.startswith('#') or len(value) not in (4, 7):
            raise serializers.ValidationError('Color must be a valid hex code, e.g. #3B82F6.')
        return value.upper()

class TaskReadSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    estimated_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'description',
            'deadline',
            'reminder_at',
            'estimated_time',
            'estimated_minutes',
            'priority',
            'status',
            'category',
            'tags',
            'recurrence',
            'ai_generated',
            'is_overdue',
            'completed_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

class TaskWriteSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=500,
        help_text='Task title (required on create).',
    )
    description = serializers.CharField(
        required=False, default='', allow_blank=True,
        help_text='Optional detailed description.',
    )

    deadline = serializers.DateTimeField(
        required=False, allow_null=True,
        help_text='Deadline as ISO-8601 datetime, e.g. 2026-07-01T09:00:00Z.',
    )
    reminder_at = serializers.DateTimeField(
        required=False, allow_null=True,
        help_text='When to send a reminder (must be before deadline).',
    )
    recurrence = serializers.ChoiceField(
        choices=Task.Recurrence.choices,
        required=False,
        default=Task.Recurrence.NONE,
    )

    estimated_time = serializers.DurationField(
        required=False, allow_null=True,
        help_text='Duration string e.g. "02:30:00" (2 h 30 min) or "P0DT1H30M".',
    )

    priority = serializers.ChoiceField(
        choices=Task.Priority.choices,
        required=False,
        default=Task.Priority.MEDIUM,
    )
    status = serializers.ChoiceField(
        choices=Task.Status.choices,
        required=False,
        default=Task.Status.TODO,
    )

    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.none(),
        source='category',
        required=False,
        allow_null=True,
        help_text='ID of an existing category owned by the current user.',
    )
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.none(),
        many=True,
        source='tag_ids',
        required=False,
        default=list,
        help_text='List of tag IDs owned by the current user.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            self.fields['category_id'].queryset = Category.objects.filter(user=request.user)
            self.fields['tag_ids'].child_relation.queryset = Tag.objects.filter(user=request.user)

    def validate_title(self, value: str) -> str:
        return bleach.clean(value.strip(), tags=[], strip=True)

    def validate_description(self, value: str) -> str:
        return bleach.clean(value.strip(), tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)

    def validate_estimated_time(self, value) -> timedelta | None:
        if value is not None and value.total_seconds() <= 0:
            raise serializers.ValidationError('Estimated time must be positive.')
        return value

    def validate(self, data: dict) -> dict:
        deadline    = data.get('deadline')
        reminder_at = data.get('reminder_at')

        if deadline and reminder_at and reminder_at >= deadline:
            raise serializers.ValidationError(
                {'reminder_at': 'Reminder must be set before the deadline.'}
            )
        return data

class BulkCompleteSerializer(serializers.Serializer):
    task_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=100,
        help_text='List of task IDs to mark as completed (max 100).',
    )

class TaskStatsSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    todo = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    overdue = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    by_priority = serializers.DictField(child=serializers.IntegerField())
    by_category = serializers.ListField()
    total_estimated_h = serializers.FloatField()
