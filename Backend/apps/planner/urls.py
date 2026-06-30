from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import PlannerViewSet

router = DefaultRouter()
router.register('planner/plans', PlannerViewSet, basename='planner-plan')

urlpatterns = [path('', include(router.urls))]
