from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TeacherViewSet, StudentViewSet, RoomViewSet, ScheduleViewSet, RuleConfigViewSet

router = DefaultRouter()
router.register(r'teachers', TeacherViewSet)
router.register(r'students', StudentViewSet)
router.register(r'rooms', RoomViewSet)
router.register(r'schedule', ScheduleViewSet, basename='schedule')
router.register(r'rule-config', RuleConfigViewSet)

urlpatterns = [
    path('', include(router.urls)),
]