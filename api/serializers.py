from rest_framework import serializers
from .models import Teacher, Student, Room

class TeacherSerializer(serializers.ModelSerializer):
    isExternal = serializers.BooleanField(source='is_external', default=False, required=False)
    availableTypes = serializers.JSONField(source='available_types', default=list, required=False)
    campusPreference = serializers.CharField(source='campus_preference', allow_blank=True, required=False)
    unavailableTimes = serializers.CharField(source='unavailable_times', allow_blank=True, required=False)
    avoidTeacherNames = serializers.CharField(source='avoid_teacher_names', allow_blank=True, required=False)
    remark = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = Teacher
        fields = [
            'id', 'name', 'college', 'isExternal', 'title', 'roles', 
            'availableTypes', 'campusPreference', 'unavailableTimes', 
            'avoidTeacherNames', 'remark'
        ]

class StudentSerializer(serializers.ModelSerializer):
    studentType = serializers.CharField(source='student_type', required=False)
    mentorName = serializers.CharField(source='mentor_name', allow_blank=True, required=False)
    defenseTypes = serializers.JSONField(source='defense_types', default=list, required=False)
    secretaryName = serializers.CharField(source='secretary_name', allow_blank=True, required=False)
    remark = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = Student
        fields = [
            'id', 'name', 'studentType', 'mentorName', 'campus', 
            'defenseTypes', 'secretaryName', 'remark'
        ]

class RoomSerializer(serializers.ModelSerializer):
    availableTimes = serializers.CharField(source='available_times', allow_blank=True, required=False)
    remark = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = Room
        fields = ['id', 'campus', 'name', 'capacity', 'availableTimes', 'remark']
from .models import ScheduleVersion, Group

class ScheduleVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduleVersion
        fields = '__all__'

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = '__all__'