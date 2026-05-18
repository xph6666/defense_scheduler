from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OperationLogViewSet, RoomViewSet, RuleConfigViewSet, ScheduleViewSet, StudentViewSet, TeacherViewSet

router = DefaultRouter()
router.register(r'teachers', TeacherViewSet)
router.register(r'students', StudentViewSet)
router.register(r'rooms', RoomViewSet)
router.register(r'rule-config', RuleConfigViewSet, basename='rule-config')
router.register(r'operation-logs', OperationLogViewSet, basename='operation-logs')
router.register(r'schedule', ScheduleViewSet, basename='schedule')

urlpatterns = [
    path('', include(router.urls)),
]