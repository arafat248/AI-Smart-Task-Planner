from __future__ import annotations
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.mixins import TimestampMixin, SoftDeleteMixin

class Category(TimestampMixin):
    ICON_CHOICES = [
        ('folder', 'Folder'), ('briefcase', 'Briefcase'), ('book', 'Book'),
        ('code', 'Code'), ('heart', 'Heart'), ('home', 'Home'),
        ('star', 'Star'), ('target', 'Target'), ('zap', 'Zap'),
        ('shopping-cart', 'Shopping Cart'), ('music', 'Music'), ('camera', 'Camera'),
    ]

    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='categories', db_index=True,
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=20, default='#3B82F6')
    icon = models.CharField(max_length=50, default='folder', choices=ICON_CHOICES)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = 'tasks_category'
        unique_together = [['user', 'name']]
        ordering = ['name']
        verbose_name = _('category')
        verbose_name_plural = _('categories')

    def __str__(self) -> str:
        return self.name

class Tag(TimestampMixin):
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='tags', db_index=True,
    )
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20, default='#8B5CF6')

    class Meta:
        db_table = 'tasks_tag'
        unique_together = [['user', 'name']]
        ordering = ['name']
        verbose_name = _('tag')

    def __str__(self) -> str:
        return self.name

class Task(TimestampMixin, SoftDeleteMixin):

    class Priority(models.TextChoices):
        LOW = 'low', _('Low')
        MEDIUM = 'medium', _('Medium')
        HIGH = 'high', _('High')
        URGENT = 'urgent', _('Urgent')

    class Status(models.TextChoices):
        TODO = 'todo', _('To Do')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    class Recurrence(models.TextChoices):
        NONE = 'none', _('None')
        DAILY = 'daily', _('Daily')
        WEEKLY = 'weekly', _('Weekly')
        MONTHLY = 'monthly', _('Monthly')

    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='tasks', db_index=True,
    )

    category = models.ForeignKey(
        Category, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='tasks',
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='tasks')

    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    deadline = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text=_('Absolute date+time when the task must be done.'),
    )
    reminder_at = models.DateTimeField(null=True, blank=True)
    recurrence = models.CharField(
        max_length=10,
        choices=Recurrence.choices,
        default=Recurrence.NONE,
    )

    estimated_time = models.DurationField(
        null=True, blank=True,
        help_text=_('Expected time to complete, e.g. "2:30:00" for 2 h 30 min.'),
    )

    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
        db_index=True,
    )
    ai_generated = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tasks_task'
        ordering = ['-created_at']
        verbose_name = _('task')
        indexes = [
            models.Index(fields=['user', 'status'],   name='task_user_status_idx'),
            models.Index(fields=['user', 'priority'], name='task_user_priority_idx'),
            models.Index(fields=['user', 'deadline'], name='task_user_deadline_idx'),
            models.Index(fields=['user', 'deleted_at'], name='task_user_softdel_idx'),
            models.Index(fields=['deadline', 'status'], name='task_deadline_status_idx'),
        ]
    def __str__(self) -> str:
        return self.title

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone
        return (
            self.deadline is not None
            and self.status not in (self.Status.COMPLETED, self.Status.CANCELLED)
            and timezone.now() > self.deadline
        )

    @property
    def estimated_minutes(self) -> int | None:
        if self.estimated_time is None:
            return None
        return int(self.estimated_time.total_seconds() // 60)
