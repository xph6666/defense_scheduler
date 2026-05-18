from rest_framework import serializers

from .models import Group, OperationLog, Room, RuleConfig, ScheduleVersion, Student, Teacher


DEFENSE_TYPE_LABELS = {
    'pre': '预答辩',
    'formal': '正式答辩',
    'mid': '中期答辩',
}

DEFENSE_TYPE_VALUES = {value: key for key, value in DEFENSE_TYPE_LABELS.items()}


def default_rule_config(defense_type='pre'):
    return {
        'defenseType': DEFENSE_TYPE_LABELS.get(defense_type, defense_type),
        'enabled': True,
        'startDate': '2025-05-10',
        'avoidWeekend': True,
        'avoidHoliday': True,
        'mentorAvoidance': True,
        'studentCount': {'target': 5, 'min': 3, 'max': 8},
        'expertCount': {'target': 2, 'min': 1},
        'secretaryCount': 1,
        'roleQualification': {
            'leaderMinTitle': '副教授',
            'chairmanMinTitle': '教授',
            'secretaryMinTitle': '讲师',
            'preferSeniorTitle': True,
        },
        'softWeights': {
            'balanceStudentCount': 50,
            'preferSeniorTeacher': 50,
            'avoidCrossCampus': 50,
            'externalMentorConcentration': 50,
            'preferAcademicMasterFirst': 50,
        },
    }


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


class ScheduleVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduleVersion
        fields = '__all__'


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = '__all__'


class RuleConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = RuleConfig
        fields = ['id', 'defense_type', 'config', 'updated_at']

    def to_representation(self, instance):
        data = default_rule_config(instance.defense_type)
        data.update(instance.config or {})
        data['defenseType'] = DEFENSE_TYPE_LABELS.get(instance.defense_type, instance.defense_type)
        data['updatedAt'] = instance.updated_at.isoformat()
        return data

    def to_internal_value(self, data):
        payload = dict(data)
        defense_type = payload.pop('defense_type', None) or DEFENSE_TYPE_VALUES.get(payload.get('defenseType'))
        if not defense_type:
            raise serializers.ValidationError({'defense_type': '缺少答辩类型'})
        config = default_rule_config(defense_type)
        config.update(payload)
        config['defenseType'] = DEFENSE_TYPE_LABELS.get(defense_type, config.get('defenseType', defense_type))
        config.pop('updatedAt', None)
        return {
            'defense_type': defense_type,
            'config': config,
        }

    def create(self, validated_data):
        obj, _ = RuleConfig.objects.update_or_create(
            defense_type=validated_data['defense_type'],
            defaults={'config': validated_data['config']},
        )
        return obj

    def update(self, instance, validated_data):
        instance.defense_type = validated_data.get('defense_type', instance.defense_type)
        instance.config = validated_data.get('config', instance.config)
        instance.save()
        return instance


class OperationLogSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    operator = serializers.CharField(required=False, allow_blank=True, default='系统')
    result = serializers.CharField(required=False, allow_blank=True, default='成功')

    class Meta:
        model = OperationLog
        fields = ['id', 'type', 'module', 'description', 'operator', 'result', 'createdAt']
