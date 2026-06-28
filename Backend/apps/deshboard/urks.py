from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import DashboardViewSet

router = DefaultRouter()
router.register('dashboard', DashboardViewSet, basename='dashboard')

urlpatterns = [path('', include(router.urls))]
