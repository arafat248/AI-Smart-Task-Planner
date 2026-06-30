from __future__ import annotations
from datetime import timedelta
from typing import Any
from django.db.models import Q, QuerySet
from django.utils import timezone
from .models import Category, Tag, Task

class TaskRepository:
    def get_by_id(self, task_id: Any, user) -> Task:
        return (
            Task.objects
            .select_related('category')
            .prefetch_related('tags')
            .get(id=task_id, user=user, deleted_at__isnull=True)
        )

    def filter_for_user(
        self,
        user,
        *,
        status: str | None = None,
        priority: str | None = None,
        category_id: Any = None,
        tag_id: Any = None,
        ai_generated: bool | None = None,
        is_overdue: bool | None = None,
        deadline_before: str | None = None,
        deadline_after: str | None = None,
        search: str | None = None,
        ordering: str = '-created_at',
    ) -> QuerySet:
        qs = (
            Task.objects
            .filter(user=user, deleted_at__isnull=True)
            .select_related('category')
            .prefetch_related('tags')
        )

        if status:
            qs = qs.filter(status=status)
        if priority:
            qs = qs.filter(priority=priority)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if tag_id:
            qs = qs.filter(tags__id=tag_id).distinct()
        if ai_generated is not None:
            qs = qs.filter(ai_generated=ai_generated)
        if deadline_before:
            qs = qs.filter(deadline__lte=deadline_before)
        if deadline_after:
            qs = qs.filter(deadline__gte=deadline_after)
        if is_overdue is True:
            qs = qs.filter(
                deadline__lt=timezone.now(),
            ).exclude(status__in=('completed', 'cancelled'))
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(tags__name__icontains=search)
            ).distinct()

        ALLOWED_ORDERINGS = {
            'created_at', '-created_at',
            'deadline', '-deadline',
            'priority', '-priority',
            'status', '-status',
            'title', '-title',
            'updated_at', '-updated_at',
        }
        if ordering not in ALLOWED_ORDERINGS:
            ordering = '-created_at'
        return qs.order_by(ordering)

    def get_recurring_due_today(self) -> QuerySet:
        today = timezone.now().date()
        return (
            Task.objects
            .filter(
                deadline__date=today,
                deleted_at__isnull=True,
            )
            .exclude(recurrence='none')
            .select_related('category', 'user')
            .prefetch_related('tags')
        )

    def create(self, **kwargs) -> Task:
        return Task.objects.create(**kwargs)

    def update(self, task: Task, **kwargs) -> Task:
        becoming_complete = (
            kwargs.get('status') == Task.Status.COMPLETED
            and task.status != Task.Status.COMPLETED
        )
        for key, val in kwargs.items():
            setattr(task, key, val)
        if becoming_complete:
            task.completed_at = timezone.now()
        elif kwargs.get('status') and kwargs['status'] != Task.Status.COMPLETED:
            task.completed_at = None
        task.save()
        return task

    def set_tags(self, task: Task, tag_ids: list) -> None:
        task.tags.set(Tag.objects.filter(id__in=tag_ids, user=task.user))

    def bulk_update_status(self, user, task_ids: list, new_status: str) -> int:
        return Task.objects.filter(
            id__in=task_ids, user=user, deleted_at__isnull=True
        ).update(status=new_status)

    def soft_delete(self, task: Task) -> None:
        task.soft_delete()

    def restore(self, task: Task) -> None:
        task.restore()

    def clone_for_recurrence(self, task: Task) -> Task:
        delta_map = {
            'daily': timedelta(days=1),
            'weekly': timedelta(weeks=1),
            'monthly': timedelta(days=30),
        }
        delta = delta_map.get(task.recurrence)
        if not delta or not task.deadline:
            return None
        new_task = Task.objects.create(
            user=task.user,
            category=task.category,
            title=task.title,
            description=task.description,
            priority=task.priority,
            estimated_time=task.estimated_time,
            deadline=task.deadline + delta,
            recurrence=task.recurrence,
        )
        new_task.tags.set(task.tags.all())
        return new_task

class CategoryRepository:

    def all_for_user(self, user) -> QuerySet:
        return Category.objects.filter(user=user).annotate(
            task_count=__import__('django.db.models', fromlist=['Count']).Count(
                'tasks', filter=Q(tasks__deleted_at__isnull=True)
            )
        )

    def get_by_id(self, category_id: Any, user) -> Category:
        return Category.objects.get(id=category_id, user=user)

    def create(self, **kwargs) -> Category:
        return Category.objects.create(**kwargs)

    def update(self, category: Category, **kwargs) -> Category:
        for key, val in kwargs.items():
            setattr(category, key, val)
        category.save()
        return category

    def delete(self, category: Category) -> None:
        category.delete()

class TagRepository:

    def all_for_user(self, user) -> QuerySet:
        return Tag.objects.filter(user=user).annotate(
            task_count=__import__('django.db.models', fromlist=['Count']).Count(
                'tasks', filter=Q(tasks__deleted_at__isnull=True)
            )
        )
    def get_by_id(self, tag_id: Any, user) -> Tag:
        return Tag.objects.get(id=tag_id, user=user)

    def create(self, **kwargs) -> Tag:
        return Tag.objects.create(**kwargs)

    def update(self, tag: Tag, **kwargs) -> Tag:
        for key, val in kwargs.items():
            setattr(tag, key, val)
        tag.save()
        return tag

    def delete(self, tag: Tag) -> None:
        tag.delete()
