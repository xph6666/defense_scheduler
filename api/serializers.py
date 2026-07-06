from datetime import datetime

from rest_framework import serializers

from .models import Group, OperationLog, Room, RuleConfig, ScheduleVersion, Student, Teacher


DEFENSE_TYPE_LABELS = {
    'pre': '预答辩',
    'formal': '正式答辩',
    'mid': '中期答辩',
}

DEFENSE_TYPE_VALUES = {value: key for key, value in DEFENSE_TYPE_LABELS.items()}
DATE_FORMAT = '%Y-%m-%d'


def default_rule_config(defense_type='pre'):
    return {
        'defenseType': DEFENSE_TYPE_LABELS.get(defense_type, defense_type),
        'enabled': True,
        'startDate': '2025-05-10',
        'endDate': '2025-05-20',
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


def parse_rule_config_date(config, key):
    try:
        return datetime.strptime(config.get(key), DATE_FORMAT).date()
    except (TypeError, ValueError):
        raise serializers.ValidationError({key: ['日期格式必须为 YYYY-MM-DD']})


def parse_non_negative_int(value, field_path):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise serializers.ValidationError({field_path: ['必须是非负整数']})
    if number < 0:
        raise serializers.ValidationError({field_path: ['必须是非负整数']})
    return number


def validate_count_bounds(config, key, *, require_max):
    value = config.get(key)
    if not isinstance(value, dict):
        raise serializers.ValidationError({key: ['配置格式不正确']})

    target = parse_non_negative_int(value.get('target'), f'{key}.target')
    minimum = parse_non_negative_int(value.get('min'), f'{key}.min')
    if minimum > target:
        raise serializers.ValidationError({key: ['最小值不能大于目标值']})

    if require_max:
        maximum = parse_non_negative_int(value.get('max'), f'{key}.max')
        if target > maximum:
            raise serializers.ValidationError({key: ['目标值不能大于最大值']})


def validate_rule_config(config):
    start_date = parse_rule_config_date(config, 'startDate')
    end_date = parse_rule_config_date(config, 'endDate')
    if end_date < start_date:
        raise serializers.ValidationError({'endDate': ['排期结束日期不能早于开始日期']})

    validate_count_bounds(config, 'studentCount', require_max=True)
    validate_count_bounds(config, 'expertCount', require_max=False)


class TeacherSerializer(serializers.ModelSerializer):
    import_unique_fields = [('name', '教师姓名重复，请使用唯一姓名')]

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

    def validate_name(self, value):
        name = value.strip()
        queryset = Teacher.objects.filter(name=name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('教师姓名已存在，请使用唯一姓名')
        return name


class StudentSerializer(serializers.ModelSerializer):
    import_unique_fields = [('studentNo', '学号重复，请检查导入数据')]

    studentNo = serializers.CharField(source='student_no', allow_blank=True, allow_null=True, required=False)
    gender = serializers.CharField(allow_blank=True, required=False)
    studentType = serializers.CharField(source='student_type', required=False)
    mentorName = serializers.CharField(source='mentor_name', allow_blank=True, required=False)
    defenseTypes = serializers.JSONField(source='defense_types', default=list, required=False)
    secretaryName = serializers.CharField(source='secretary_name', allow_blank=True, required=False)
    remark = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = Student
        fields = [
            'id', 'name', 'studentNo', 'gender', 'studentType', 'mentorName',
            'campus', 'defenseTypes', 'secretaryName', 'remark'
        ]

    def validate_name(self, value):
        return value.strip()

    def validate_studentNo(self, value):
        # 空学号统一存 NULL，避免空字符串之间触发唯一约束冲突
        if value is None:
            return None
        student_no = str(value).strip()
        if not student_no:
            return None
        queryset = Student.objects.filter(student_no=student_no)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('学号已存在，请检查是否重复录入')
        return student_no

    def validate(self, attrs):
        # 未提供学号时按姓名兜底查重，防止同名学生在无学号场景下混淆；
        # 有学号的同名学生是合法数据（真实名单存在重名），不做姓名唯一限制
        name = attrs.get('name', self.instance.name if self.instance else None)
        student_no = attrs.get('student_no', self.instance.student_no if self.instance else None)
        if name and not student_no:
            # 批量导入时的批内查重：状态挂在 view 上，逐行按顺序消费
            view = self.context.get('view')
            seen_names = getattr(view, '_import_seen_unnumbered_names', None) if view else None
            if seen_names is not None:
                if name in seen_names:
                    raise serializers.ValidationError({'name': ['文件中存在同名且无学号的学生，无法区分，请补充学号']})
                seen_names.add(name)

            queryset = Student.objects.filter(name=name, student_no__isnull=True)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError({'name': ['已存在同名且无学号的学生，请补充学号以区分']})
        return attrs


class RoomSerializer(serializers.ModelSerializer):
    import_unique_fields = [(('campus', 'name'), '同一校区的教室名称重复')]

    availableTimes = serializers.CharField(source='available_times', allow_blank=True, required=False)
    remark = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = Room
        fields = ['id', 'campus', 'name', 'capacity', 'availableTimes', 'remark']
        validators = []

    def validate(self, attrs):
        campus = attrs.get('campus', self.instance.campus if self.instance else None)
        name = attrs.get('name', self.instance.name if self.instance else None)
        if isinstance(campus, str):
            campus = campus.strip()
            attrs['campus'] = campus
        if isinstance(name, str):
            name = name.strip()
            attrs['name'] = name

        if campus and name:
            queryset = Room.objects.filter(campus=campus, name=name)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError({'name': ['同一校区的教室名称已存在']})
        return attrs


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
        validate_rule_config(config)
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
