from __future__ import annotations
import django_filters
from django.db.models import Q
from .models import Task

class TaskFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=Task.Status.choices)
    priority = django_filters.MultipleChoiceFilter(choices=Task.Priority.choices)
    recurrence = django_filters.ChoiceFilter(choices=Task.Recurrence.choices)
    deadline_before = django_filters.IsoDateTimeFilter(
        field_name='deadline', lookup_expr='lte',
        label='Deadline on or before (ISO-8601)',
    )
    deadline_after = django_filters.IsoDateTimeFilter(
        field_name='deadline', lookup_expr='gte',
        label='Deadline on or after (ISO-8601)',
    )
    has_deadline = django_filters.BooleanFilter(
        field_name='deadline', lookup_expr='isnull',
        label='Has a deadline set',
        method='filter_has_deadline',
    )
    category = django_filters.NumberFilter(field_name='category__id')
    tag = django_filters.NumberFilter(field_name='tags__id')
    ai_generated = django_filters.BooleanFilter()
    is_overdue = django_filters.BooleanFilter(method='filter_is_overdue', label='Is overdue')
    search = django_filters.CharFilter(method='filter_search', label='Full-text search')

    class Meta:
        model = Task
        fields = [
            'status', 'priority', 'recurrence',
            'deadline_before', 'deadline_after', 'has_deadline',
            'category', 'tag',
            'ai_generated', 'is_overdue',
            'search',
        ]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value)
            | Q(description__icontains=value)
            | Q(tags__name__icontains=value)
        ).distinct()

    def filter_is_overdue(self, queryset, name, value):
        from django.utils import timezone
        if value is True:
            return queryset.filter(
                deadline__lt=timezone.now(),
            ).exclude(status__in=('completed', 'cancelled'))
        if value is False:
            return queryset.filter(
                Q(deadline__isnull=True)
                | Q(deadline__gte=timezone.now())
                | Q(status__in=('completed', 'cancelled'))
            )
        return queryset

    def filter_has_deadline(self, queryset, name, value):
        if value is True:
            return queryset.filter(deadline__isnull=False)
        if value is False:
            return queryset.filter(deadline__isnull=True)
        return queryset
