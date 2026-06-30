from django.shortcuts import render
from __future__ import annotations
import logging
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.pagination import StandardPagination
from .models import AIPlan, PlanStatus
from .serializers import (
    AIPlanDetailSerializer,
    AIPlanListSerializer,
    GeneratePlanSerializer,
    PlanQuerySerializer,
)
from .services import PlannerService
from .tasks import generate_plan_async

logger = logging.getLogger(__name__)
_svc = PlannerService()
TAG  = ['planner']

def _rl_key(group, request):
    if request.user.is_authenticated:
        return f'u:{request.user.id}'
    return request.META.get('REMOTE_ADDR', 'unknown')

@extend_schema_view(
    create=extend_schema(
        tags=TAG,
        summary='Generate an AI plan',
        description=(
            'Creates a pending plan record, enqueues async AI generation via Celery, '
            'and returns the plan ID immediately (HTTP 202). '
            'Poll GET /planner/plans/{id}/status/ to track progress.'
        ),
        request=GeneratePlanSerializer,
        responses={
            202: AIPlanListSerializer,
            400: OpenApiResponse(description='Validation error'),
            429: OpenApiResponse(description='Rate limit exceeded (5 per hour per user)'),
        },
    ),
    list=extend_schema(
        tags=TAG,
        summary='List AI plan history',
        parameters=[
            OpenApiParameter('plan_type', description='daily or weekly'),
        ],
        responses={200: AIPlanListSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=TAG,
        summary='Retrieve a plan with full AI output',
        responses={
            200: AIPlanDetailSerializer,
            404: OpenApiResponse(description='Not found'),
        },
    ),
    destroy=extend_schema(
        tags=TAG,
        summary='Delete a plan',
        responses={204: OpenApiResponse(description='Deleted')},
    ),
)
class PlannerViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination

    @ratelimit(key=_rl_key, rate='5/h', block=True)
    def create(self, request):
        """Create pending plan + dispatch async Celery task."""
        serializer = GeneratePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        plan = _svc.create_pending_plan(
            user            = request.user,
            plan_type       = d['plan_type'],
            plan_date       = str(d['plan_date']),
            available_hours = float(d['available_hours']),
            work_start_time = str(d['work_start_time']),
            work_end_time   = str(d['work_end_time']),
        )

        generate_plan_async.delay(plan_id=plan.id)

        logger.info('Plan id=%s enqueued for user=%s', plan.id, request.user.id)
        return Response(
            AIPlanListSerializer(plan).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def list(self, request):
        """Return paginated history of completed plans."""
        query_s = PlanQuerySerializer(data=request.query_params)
        query_s.is_valid(raise_exception=True)
        plan_type = query_s.validated_data.get('plan_type')

        plans = _svc.get_history(request.user, plan_type)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(plans, request)
        return paginator.get_paginated_response(AIPlanListSerializer(page, many=True).data)

    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def retrieve(self, request, pk=None):
        """Return full plan detail including all AI sections."""
        plan = _svc.get_plan(pk, request.user)
        return Response(AIPlanDetailSerializer(plan).data)

    @ratelimit(key=_rl_key, rate='30/m', block=True)
    def destroy(self, request, pk=None):
        plan = _svc.get_plan(pk, request.user)
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=TAG,
        summary='Get the latest completed plan',
        parameters=[OpenApiParameter('plan_type', description='daily or weekly')],
        responses={200: AIPlanDetailSerializer, 204: OpenApiResponse(description='No plan yet')},
    )
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    @action(detail=False, methods=['get'], url_path='latest')
    def latest(self, request):
        plan_type = request.query_params.get('plan_type', AIPlan.PlanType.DAILY)
        plan = _svc.get_latest(request.user, plan_type)
        if plan is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(AIPlanDetailSerializer(plan).data)

    @extend_schema(
        tags=TAG,
        summary='Poll plan generation status',
        responses={
            200: OpenApiResponse(description='{ id, status, overall_score, generation_ms, error_message }'),
            404: OpenApiResponse(description='Not found'),
        },
    )
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    @action(detail=True, methods=['get'], url_path='status')
    def plan_status(self, request, pk=None):
        plan = _svc.get_plan(pk, request.user)
        return Response({
            'id':             plan.id,
            'status':         plan.status,
            'overall_score':  plan.overall_score,
            'generation_ms':  plan.generation_ms,
            'error_message':  plan.error_message or None,
            'is_ready':       plan.is_ready,
        })

    @extend_schema(
        tags=TAG,
        summary='Re-generate a failed or outdated plan',
        responses={
            202: AIPlanListSerializer,
            400: OpenApiResponse(description='Plan is not in a re-generable state'),
        },
    )
    @ratelimit(key=_rl_key, rate='5/h', block=True)
    @action(detail=True, methods=['post'], url_path='regenerate')
    def regenerate(self, request, pk=None):
        plan = _svc.get_plan(pk, request.user)
        if plan.status == PlanStatus.GENERATING:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'Plan is currently being generated. Please wait.'})

        plan.status        = PlanStatus.PENDING
        plan.error_message = ''
        plan.retry_count   = plan.retry_count + 1
        plan.save(update_fields=['status', 'error_message', 'retry_count'])

        generate_plan_async.delay(plan_id=plan.id)
        return Response(AIPlanListSerializer(plan).data, status=status.HTTP_202_ACCEPTED)
