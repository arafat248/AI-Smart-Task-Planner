from __future__ import annotations
import logging
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from .serializers import (
    FullAnalyticsQuerySerializer,
    FullAnalyticsResponseSerializer,
    MonthlyProgressResponseSerializer,
    MonthlyQuerySerializer,
    OverviewResponseSerializer,
    WeeklyProgressResponseSerializer,
    WeeklyQuerySerializer,
)
from .services import DashboardService

logger = logging.getLogger(__name__)
_svc = DashboardService()
TAG  = ['dashboard']

def _rl_key(group, request):
    if request.user.is_authenticated:
        return f'u:{request.user.id}'
    return request.META.get('REMOTE_ADDR', 'unknown')

class DashboardViewSet(ViewSet):
    """
    Read-only dashboard analytics.
    All actions are GET-only — no create/update/destroy.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=TAG,
        summary='Dashboard overview',
        description=(
            'Returns all top-level KPIs in a single optimised response:\n\n'
            '- **Summary**: total, completed, pending, overdue, due_soon, productivity %\n'
            '- **Priority breakdown**: counts per priority level\n'
            '- **Category breakdown**: counts per category with overdue\n'
            '- **Tag breakdown**: top tags by usage\n'
            '- **Streak**: current and longest completion streaks\n'
            '- **Upcoming deadlines**: next 5 tasks due\n'
            '- **Recent completions**: last 5 completed tasks\n\n'
            'Query count: ~7 optimised aggregations, zero N+1.'
        ),
        responses={200: OverviewResponseSerializer},
    )
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    @action(detail=False, methods=['get'], url_path='overview')
    def overview(self, request):
        data = _svc.get_overview(request.user)
        return Response(OverviewResponseSerializer(data).data)

    @extend_schema(
        tags=TAG,
        summary='Weekly progress',
        description=(
            'Returns:\n\n'
            '- **daily**: completed + created counts for each of the last 7 days\n'
            '- **weekly**: completed + created counts per ISO week for the last N weeks\n\n'
            'All dates are zero-filled (no gaps in the series).'
        ),
        parameters=[
            OpenApiParameter(
                'weeks',
                description='Number of weeks to include (1–52, default 8)',
                type=int,
            )
        ],
        responses={200: WeeklyProgressResponseSerializer},
    )
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    @action(detail=False, methods=['get'], url_path='weekly')
    def weekly(self, request):
        query_s = WeeklyQuerySerializer(data=request.query_params)
        query_s.is_valid(raise_exception=True)
        data = _svc.get_weekly_progress(
            request.user,
            weeks=query_s.validated_data['weeks'],
        )
        return Response(WeeklyProgressResponseSerializer(data).data)

    @extend_schema(
        tags=TAG,
        summary='Monthly progress',
        description=(
            'Returns a monthly time series of completed and created tasks '
            'plus the month-on-month completion delta (%).\n\n'
            '`month_on_month_delta` is null when there are fewer than 2 months of data.'
        ),
        parameters=[
            OpenApiParameter(
                'months',
                description='Number of months to include (1–24, default 6)',
                type=int,
            )
        ],
        responses={200: MonthlyProgressResponseSerializer},
    )
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    @action(detail=False, methods=['get'], url_path='monthly')
    def monthly(self, request):
        query_s = MonthlyQuerySerializer(data=request.query_params)
        query_s.is_valid(raise_exception=True)
        data = _svc.get_monthly_progress(
            request.user,
            months=query_s.validated_data['months'],
        )
        return Response(MonthlyProgressResponseSerializer(data).data)

    @extend_schema(
        tags=TAG,
        summary='Full analytics (all sections in one call)',
        description=(
            'Combines overview + weekly + monthly into a single response.\n\n'
            'Use this endpoint when the client needs everything on first load to '
            'avoid multiple round-trips. ~10 DB queries, all aggregations.'
        ),
        parameters=[
            OpenApiParameter('weeks',  description='Weeks of weekly history (default 8)', type=int),
            OpenApiParameter('months', description='Months of monthly history (default 6)', type=int),
        ],
        responses={200: FullAnalyticsResponseSerializer},
    )
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    @action(detail=False, methods=['get'], url_path='analytics')
    def analytics(self, request):
        query_s = FullAnalyticsQuerySerializer(data=request.query_params)
        query_s.is_valid(raise_exception=True)
        d = query_s.validated_data
        data = _svc.get_full_analytics(
            request.user,
            weeks=d['weeks'],
            months=d['months'],
        )
        return Response(FullAnalyticsResponseSerializer(data).data)
