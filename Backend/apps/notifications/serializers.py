from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    task_title = serializers.CharField(source='task.title', read_only=True, default=None)
    read = serializers.BooleanField(source='read_at', read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'type', 'message', 'task_id', 'task_title', 'read', 'read_at', 'created_at']
        read_only_fields = fields

class ReminderTaskSerializer(serializers.Serializer):
    """Lightweight task representation for the Reminders view."""
    id = serializers.IntegerField()
    title = serializers.CharField()
    deadline = serializers.CharField(allow_null=True)
    reminder_at = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    priority = serializers.CharField()
    category = serializers.DictField(allow_null=True)
    hours_until_deadline = serializers.FloatField(allow_null=True)

class ReminderHistorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    message = serializers.CharField()
    task_id = serializers.IntegerField(allow_null=True)
    task_title = serializers.CharField(allow_null=True)
    read = serializers.BooleanField()
    created_at = serializers.CharField()
