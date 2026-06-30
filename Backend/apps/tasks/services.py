from __future__ import annotations
import logging
from datetime import timedelta
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from .models import Category, Tag, Task
from .repositories import CategoryRepository, TagRepository, TaskRepository

logger = logging.getLogger(__name__)
_task_repo = TaskRepository()
_cat_repo  = CategoryRepository()
_tag_repo  = TagRepository()

class TaskService:
    def list_tasks(self, user, query_params: dict):
        return _task_repo.filter_for_user(
            user,
            status=query_params.get('status'),
            priority=query_params.get('priority'),
            category_id=query_params.get('category'),
            tag_id=query_params.get('tag'),
            ai_generated=_parse_bool(query_params.get('ai_generated')),
            is_overdue=_parse_bool(query_params.get('is_overdue')),
            deadline_before=query_params.get('deadline_before'),
            deadline_after=query_params.get('deadline_after'),
            search=query_params.get('search'),
            ordering=query_params.get('ordering', '-created_at'),
        )

    def get_task(self, task_id, user) -> Task:
        try:
            return _task_repo.get_by_id(task_id, user)
        except Task.DoesNotExist:
            raise NotFound('Task not found.')

    def create_task(self, user, validated_data: dict) -> Task:
        tag_ids    = validated_data.pop('tag_ids', [])
        category   = validated_data.pop('category', None)

        self._validate_deadline(validated_data.get('deadline'))

        task = _task_repo.create(user=user, category=category, **validated_data)

        if tag_ids:
            _task_repo.set_tags(task, tag_ids)

        if task.deadline:
            self._schedule_reminder(task)

        logger.info('Task created id=%s user=%s', task.id, user.id)
        return _task_repo.get_by_id(task.id, user)

    def update_task(self, task: Task, validated_data: dict) -> Task:
        tag_ids  = validated_data.pop('tag_ids', None)
        category = validated_data.pop('category', ...)

        if 'deadline' in validated_data:
            self._validate_deadline(validated_data['deadline'])

        if category is not ...:
            validated_data['category'] = category

        task = _task_repo.update(task, **validated_data)

        if tag_ids is not None:
            _task_repo.set_tags(task, tag_ids)

        if task.status == Task.Status.COMPLETED:
            self._cancel_reminder(task)

        logger.info('Task updated id=%s', task.id)
        return _task_repo.get_by_id(task.id, task.user)

    def delete_task(self, task: Task) -> None:
        _task_repo.soft_delete(task)
        logger.info('Task soft-deleted id=%s', task.id)

    def bulk_complete(self, user, task_ids: list) -> int:
        if not task_ids:
            raise ValidationError({'task_ids': 'Provide at least one task ID.'})
        count = _task_repo.bulk_update_status(user, task_ids, Task.Status.COMPLETED)
        logger.info('Bulk completed %d tasks for user=%s', count, user.id)
        return count

    def restore_task(self, task_id, user) -> Task:
        try:
            task = Task.objects.get(id=task_id, user=user)
        except Task.DoesNotExist:
            raise NotFound('Task not found (including deleted).')
        if not task.deleted_at:
            raise ValidationError({'detail': 'Task is not deleted.'})
        _task_repo.restore(task)
        return _task_repo.get_by_id(task.id, user)

    @staticmethod
    def _validate_deadline(deadline) -> None:
        if deadline and deadline < timezone.now():
            raise ValidationError({'deadline': 'Deadline cannot be in the past.'})

    @staticmethod
    def _schedule_reminder(task: Task) -> None:
        try:
            from apps.notifications.services import NotificationService
            NotificationService().schedule_reminder(task)
        except Exception as exc:
            logger.warning('Could not schedule reminder for task=%s: %s', task.id, exc)

    @staticmethod
    def _cancel_reminder(task: Task) -> None:
        try:
            from apps.notifications.services import NotificationService
            NotificationService().cancel_reminder(task)
        except Exception as exc:
            logger.warning('Could not cancel reminder for task=%s: %s', task.id, exc)

class CategoryService:

    def list_categories(self, user):
        return _cat_repo.all_for_user(user)

    def get_category(self, category_id, user) -> Category:
        try:
            return _cat_repo.get_by_id(category_id, user)
        except Category.DoesNotExist:
            raise NotFound('Category not found.')

    def create_category(self, user, validated_data: dict) -> Category:
        name = validated_data['name']
        if Category.objects.filter(user=user, name__iexact=name).exists():
            raise ValidationError({'name': f'Category "{name}" already exists.'})
        return _cat_repo.create(user=user, **validated_data)

    def update_category(self, category: Category, validated_data: dict) -> Category:
        if 'name' in validated_data:
            name = validated_data['name']
            if (
                Category.objects
                .filter(user=category.user, name__iexact=name)
                .exclude(id=category.id)
                .exists()
            ):
                raise ValidationError({'name': f'Category "{name}" already exists.'})
        return _cat_repo.update(category, **validated_data)

    def delete_category(self, category: Category) -> None:
        _cat_repo.delete(category)

class TagService:

    def list_tags(self, user):
        return _tag_repo.all_for_user(user)

    def get_tag(self, tag_id, user) -> Tag:
        try:
            return _tag_repo.get_by_id(tag_id, user)
        except Tag.DoesNotExist:
            raise NotFound('Tag not found.')

    def create_tag(self, user, validated_data: dict) -> Tag:
        name = validated_data['name']
        if Tag.objects.filter(user=user, name__iexact=name).exists():
            raise ValidationError({'name': f'Tag "{name}" already exists.'})
        return _tag_repo.create(user=user, **validated_data)

    def update_tag(self, tag: Tag, validated_data: dict) -> Tag:
        if 'name' in validated_data:
            name = validated_data['name']
            if (
                Tag.objects
                .filter(user=tag.user, name__iexact=name)
                .exclude(id=tag.id)
                .exists()
            ):
                raise ValidationError({'name': f'Tag "{name}" already exists.'})
        return _tag_repo.update(tag, **validated_data)

    def delete_tag(self, tag: Tag) -> None:
        _tag_repo.delete(tag)

def _parse_bool(value) -> bool | None:
    if value is None:
        return None
    return str(value).lower() in ('true', '1', 'yes')
