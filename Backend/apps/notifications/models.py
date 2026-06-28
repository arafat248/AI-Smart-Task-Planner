from django.db import models
from core.mixins import TimestampMixin

class Notification(TimestampMixin):
    TYPE_CHOICES = [
        ('reminder', 'Reminder'),
        ('overdue', 'Overdue'),
        ('ai_plan', 'AI Plan'),
        ('system', 'System'),
    ]

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='notifications')
    task = models.ForeignKey('tasks.Task', null=True, blank=True, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='reminder')
    message = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'notifications_notification'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'read_at'], condition=models.Q(read_at__isnull=True), name='notif_unread_idx'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'Notification<{self.user.email} {self.type}>'
