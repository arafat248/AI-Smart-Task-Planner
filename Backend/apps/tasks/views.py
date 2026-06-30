from __future__ import annotations
import logging
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import (
    OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.pagination import StandardPagination
from core.permissions import IsOwner
from .filters import TaskFilter
from .models import Category, Tag, Task
from .serializers import (
    BulkCompleteSerializer,
    CategorySerializer,
    TagSerializer,
    TaskReadSerializer,
    TaskStatsSummarySerializer,
    TaskWriteSerializer,
)
from .services import CategoryService, TagService, TaskService

logger = logging.getLogger(__name__)
_task_svc = TaskService()
_cat_svc  = CategoryService()
_tag_svc  = TagService()

TAG_TASKS      = ['tasks']
TAG_CATEGORIES = ['categories']
TAG_TAGS       = ['tags']

def _rl_key(group, request):
    if request.user.is_authenticated:
        return f'u:{request.user.id}'
    return request.META.get('REMOTE_ADDR', 'unknown')

@extend_schema_view(
    list=extend_schema(
        tags=TAG_TASKS,
        summary='List tasks',
        description=(
            'Returns a paginated, filtered, and sorted list of the current user\'s tasks. '
            'Supports full-text `search` across title, description, and tag names.'
        ),
        parameters=[
            OpenApiParameter('status', description='Filter by status (multi-value)'),
            OpenApiParameter('priority', description='Filter by priority (multi-value)'),
            OpenApiParameter('category', description='Filter by category ID'),
            OpenApiParameter('tag', description='Filter by tag ID'),
            OpenApiParameter('deadline_before', description='ISO-8601 datetime upper bound'),
            OpenApiParameter('deadline_after', description='ISO-8601 datetime lower bound'),
            OpenApiParameter('has_deadline', description='true/false'),
            OpenApiParameter('is_overdue', description='true/false'),
            OpenApiParameter('ai_generated', description='true/false'),
            OpenApiParameter('search', description='Full-text search in title, description, tags'),
            OpenApiParameter('ordering', description='-created_at | deadline | -deadline | priority | status | title'),
            OpenApiParameter('page', description='Page number'),
            OpenApiParameter('page_size', description='Items per page (max 100)'),
        ],
        responses={200: TaskReadSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=TAG_TASKS, summary='Retrieve a task',
        responses={200: TaskReadSerializer, 404: OpenApiResponse(description='Not found')},
    ),
    create=extend_schema(
        tags=TAG_TASKS, summary='Create a task',
        request=TaskWriteSerializer,
        responses={201: TaskReadSerializer, 400: OpenApiResponse(description='Validation error')},
    ),
    partial_update=extend_schema(
        tags=TAG_TASKS, summary='Partially update a task',
        request=TaskWriteSerializer,
        responses={200: TaskReadSerializer},
    ),
    destroy=extend_schema(
        tags=TAG_TASKS, summary='Soft-delete a task',
        responses={204: OpenApiResponse(description='Deleted')},
    ),
)
class TaskViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination
    filterset_class    = TaskFilter

    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def list(self, request):
        qs = _task_svc.list_tasks(request.user, dict(request.query_params))
        # Apply django-filter
        from django_filters.rest_framework import DjangoFilterBackend
        filterset = TaskFilter(request.query_params, queryset=qs, request=request)
        if filterset.is_valid():
            qs = filterset.qs

        ordering = request.query_params.get('ordering', '-created_at')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = TaskReadSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def retrieve(self, request, pk=None):
        task = _task_svc.get_task(pk, request.user)
        return Response(TaskReadSerializer(task).data)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def create(self, request):
        serializer = TaskWriteSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        task = _task_svc.create_task(request.user, serializer.validated_data)
        return Response(TaskReadSerializer(task).data, status=status.HTTP_201_CREATED)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def partial_update(self, request, pk=None):
        task = _task_svc.get_task(pk, request.user)
        serializer = TaskWriteSerializer(
            data=request.data, partial=True, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        task = _task_svc.update_task(task, serializer.validated_data)
        return Response(TaskReadSerializer(task).data)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def destroy(self, request, pk=None):
        task = _task_svc.get_task(pk, request.user)
        _task_svc.delete_task(task)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=TAG_TASKS,
        summary='Bulk complete tasks',
        request=BulkCompleteSerializer,
        responses={200: OpenApiResponse(description='{ updated: N }')},
    )
    @ratelimit(key=_rl_key, rate='10/m', block=True)
    @action(detail=False, methods=['post'], url_path='bulk-complete')
    def bulk_complete(self, request):
        serializer = BulkCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        count = _task_svc.bulk_complete(request.user, serializer.validated_data['task_ids'])
        return Response({'updated': count})

    @extend_schema(
        tags=TAG_TASKS,
        summary='Restore a soft-deleted task',
        responses={200: TaskReadSerializer, 404: OpenApiResponse(description='Not found')},
    )
    @ratelimit(key=_rl_key, rate='10/m', block=True)
    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        task = _task_svc.restore_task(pk, request.user)
        return Response(TaskReadSerializer(task).data)

    @extend_schema(
        tags=TAG_TASKS,
        summary='Task statistics for the current user',
        responses={200: TaskStatsSummarySerializer},
    )
    @ratelimit(key=_rl_key, rate='30/m', block=True)
    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        qs = Task.objects.filter(user=request.user, deleted_at__isnull=True)

        total = qs.count()
        completed = qs.filter(status='completed').count()
        in_progress = qs.filter(status='in_progress').count()
        todo = qs.filter(status='todo').count()
        cancelled = qs.filter(status='cancelled').count()
        overdue = qs.filter(
            deadline__lt=timezone.now()
        ).exclude(status__in=('completed', 'cancelled')).count()

        by_priority = {
            p: qs.filter(priority=p).count()
            for p in ('low', 'medium', 'high', 'urgent')
        }

        by_category = list(
            qs.filter(category__isnull=False)
            .values('category__id', 'category__name', 'category__color')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        total_seconds = (
            qs.exclude(estimated_time__isnull=True)
            .aggregate(s=Sum('estimated_time'))['s']
        )
        total_h = round((total_seconds.total_seconds() / 3600) if total_seconds else 0, 1)

        data = {
            'total': total, 'completed': completed, 'in_progress': in_progress,
            'todo': todo, 'cancelled': cancelled, 'overdue': overdue,
            'completion_rate': round((completed / total * 100) if total else 0, 1),
            'by_priority': by_priority,
            'by_category': [
                {
                    'id': r['category__id'],
                    'name': r['category__name'],
                    'color': r['category__color'],
                    'count': r['count'],
                }
                for r in by_category
            ],
            'total_estimated_h': total_h,
        }
        return Response(TaskStatsSummarySerializer(data).data)

@extend_schema_view(
    list=extend_schema(tags=TAG_CATEGORIES, summary='List categories'),
    retrieve=extend_schema(tags=TAG_CATEGORIES, summary='Retrieve a category'),
    create=extend_schema(tags=TAG_CATEGORIES, summary='Create a category',
                        request=CategorySerializer),
    partial_update=extend_schema(tags=TAG_CATEGORIES, summary='Update a category',
                                request=CategorySerializer),
    destroy=extend_schema(tags=TAG_CATEGORIES, summary='Delete a category'),
)
class CategoryViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination

    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def list(self, request):
        cats = _cat_svc.list_categories(request.user)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(cats, request)
        return paginator.get_paginated_response(CategorySerializer(page, many=True).data)

    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def retrieve(self, request, pk=None):
        cat = _cat_svc.get_category(pk, request.user)
        return Response(CategorySerializer(cat).data)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def create(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cat = _cat_svc.create_category(request.user, serializer.validated_data)
        return Response(CategorySerializer(cat).data, status=status.HTTP_201_CREATED)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def partial_update(self, request, pk=None):
        cat = _cat_svc.get_category(pk, request.user)
        serializer = CategorySerializer(cat, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        cat = _cat_svc.update_category(cat, serializer.validated_data)
        return Response(CategorySerializer(cat).data)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def destroy(self, request, pk=None):
        cat = _cat_svc.get_category(pk, request.user)
        _cat_svc.delete_category(cat)
        return Response(status=status.HTTP_204_NO_CONTENT)

@extend_schema_view(
    list=extend_schema(tags=TAG_TAGS, summary='List tags'),
    retrieve=extend_schema(tags=TAG_TAGS, summary='Retrieve a tag'),
    create=extend_schema(tags=TAG_TAGS, summary='Create a tag', request=TagSerializer),
    partial_update=extend_schema(tags=TAG_TAGS, summary='Update a tag', request=TagSerializer),
    destroy=extend_schema(tags=TAG_TAGS, summary='Delete a tag'),
)
class TagViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def list(self, request):
        tags = _tag_svc.list_tags(request.user)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(tags, request)
        return paginator.get_paginated_response(TagSerializer(page, many=True).data)

    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def retrieve(self, request, pk=None):
        tag = _tag_svc.get_tag(pk, request.user)
        return Response(TagSerializer(tag).data)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def create(self, request):
        serializer = TagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tag = _tag_svc.create_tag(request.user, serializer.validated_data)
        return Response(TagSerializer(tag).data, status=status.HTTP_201_CREATED)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def partial_update(self, request, pk=None):
        tag = _tag_svc.get_tag(pk, request.user)
        serializer = TagSerializer(tag, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tag = _tag_svc.update_tag(tag, serializer.validated_data)
        return Response(TagSerializer(tag).data)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def destroy(self, request, pk=None):
        tag = _tag_svc.get_tag(pk, request.user)
        _tag_svc.delete_tag(tag)
        return Response(status=status.HTTP_204_NO_CONTENT)
