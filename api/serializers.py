from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from rest_framework import serializers
from scheduling.policies import scenario_policy

from .models import Group, OperationLog, Room, RuleConfig, ScheduleVersion, Student, Teacher
from .services.reference_data import ReferenceDataError, sync_student_references, sync_teacher_rename


DEFENSE_TYPE_LABELS = {
    'pre': '预答辩',
    'formal': '正式答辩',
    'mid': '中期答辩',
}

DEFENSE_TYPE_VALUES = {value: key for key, value in DEFENSE_TYPE_LABELS.items()}
DATE_FORMAT = '%Y-%m-%d'


def default_rule_config(defense_type='pre'):
    config = scenario_policy(defense_type)
    today = timezone.localdate()
    config.update(policyVersion=2, startDate=today.isoformat(),
                  endDate=(today + timedelta(days=10)).isoformat(), excludeDates=[])
    return config


def merge_rule_config(defaults, overrides):
    """Merge nested rule sections so partial API updates retain their bounds."""
    merged = dict(defaults)
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def parse_rule_config_date(config, key):
    try:
        return datetime.strptime(config.get(key), DATE_FORMAT).date()
    except (TypeError, ValueError):
        raise serializers.ValidationError({key: ['日期格式必须为 YYYY-MM-DD']})


def parse_non_negative_int(value, field_path):
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        raise serializers.ValidationError({field_path: ['必须是非负整数']})
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
    campus_dates = config.get('campusStartDates') or {}
    if not isinstance(campus_dates, dict) or any(key not in ('创新港', '兴庆') for key in campus_dates):
        raise serializers.ValidationError({'campusStartDates': ['分校区开始日期格式不正确']})
    for value in campus_dates.values():
        try:
            day = datetime.strptime(value, DATE_FORMAT).date()
            if not start_date <= day <= end_date:
                raise ValueError
        except (ValueError, TypeError):
            raise serializers.ValidationError({'campusStartDates': ['校区开始日期必须在本次排期范围内']})

    exclude_dates = config.get('excludeDates') or []
    if not isinstance(exclude_dates, list):
        raise serializers.ValidationError({'excludeDates': ['节假日日期必须是数组']})
    for raw in exclude_dates:
        try:
            datetime.strptime(str(raw), DATE_FORMAT)
        except (TypeError, ValueError):
            raise serializers.ValidationError({'excludeDates': [f'日期格式必须为 YYYY-MM-DD：{raw}']})

    validate_count_bounds(config, 'studentCount', require_max=True)
    validate_count_bounds(config, 'expertCount', require_max=False)
    defense_type = DEFENSE_TYPE_VALUES.get(config.get('defenseType'), config.get('defenseType'))
    if defense_type not in DEFENSE_TYPE_LABELS:
        raise serializers.ValidationError({'defenseType': ['不支持的答辩类型']})
    experts = config['expertCount']
    target = parse_non_negative_int(experts['target'], 'expertCount.target')
    minimum = parse_non_negative_int(experts['min'], 'expertCount.min')
    floor = 4 if defense_type == 'pre' else 5
    if minimum < floor:
        raise serializers.ValidationError({'expertCount': [f'专家人数含主席/组长，至少需要 {floor} 人']})
    if defense_type == 'formal' and (minimum != 5 or target != 5 or experts.get('max') not in (None, 5)):
        raise serializers.ValidationError({'expertCount': ['正式答辩专家人数必须固定为 5 人（含主席）']})
    if experts.get('max') is not None and target > parse_non_negative_int(experts['max'], 'expertCount.max'):
        raise serializers.ValidationError({'expertCount': ['目标值不能大于最大值']})
    if config.get('expertCountIncludesChair') is not True:
        raise serializers.ValidationError({'expertCountIncludesChair': ['主席/组长必须计入专家人数']})
    if 'includesChair' in experts and experts['includesChair'] is not True:
        raise serializers.ValidationError({'expertCount': ['主席/组长必须计入专家人数']})
    if defense_type != 'formal' and config['mentorAvoidance'] is not False:
        raise serializers.ValidationError({'mentorAvoidance': ['预答辩和中期答辩必须保持导师在场']})
    if config.get('courseHalfDayBlocking') is not True:
        raise serializers.ValidationError({'courseHalfDayBlocking': ['有课的半天不能安排答辩']})
    if parse_non_negative_int(config.get('secretaryCount'), 'secretaryCount') != 1:
        raise serializers.ValidationError({'secretaryCount': ['每组必须配备 1 名秘书']})
    if defense_type == 'formal' and not 3 <= parse_non_negative_int(config.get('formalSoftwareMin'), 'formalSoftwareMin') <= 5:
        raise serializers.ValidationError({'formalSoftwareMin': ['正式答辩软件学院导师人数必须在 3 到 5 人之间']})
    for key in ('enabled', 'avoidWeekend', 'avoidHoliday', 'mentorAvoidance', 'expertCountIncludesChair',
                'courseHalfDayBlocking', 'includeRemarks', 'preservePreDefenseGroups', 'formalMentorSameSession'):
        if not isinstance(config.get(key), bool):
            raise serializers.ValidationError({key: ['必须是布尔值']})
    qualifications = config.get('roleQualification')
    if not isinstance(qualifications, dict):
        raise serializers.ValidationError({'roleQualification': ['配置格式不正确']})
    ranks = {'助教': 0, '讲师': 1, '副教授': 2, '副高': 2, '教授': 3, '正高': 3,
             '副研究员': 2, '研究员': 3}
    for key, floor in (('leaderMinTitle', 2), ('chairmanMinTitle', 3), ('secretaryMinTitle', 1)):
        if ranks.get(qualifications.get(key), -1) < floor:
            raise serializers.ValidationError({f'roleQualification.{key}': ['职称门槛不能低于业务要求']})


class TeacherSerializer(serializers.ModelSerializer):
    import_unique_fields = [('name', '教师姓名重复，请使用唯一姓名')]

    isExternal = serializers.BooleanField(source='is_external', default=False, required=False)
    isActive = serializers.BooleanField(source='is_active', default=True, required=False)
    memberEligible = serializers.BooleanField(source='member_eligible', default=True, required=False)
    isSoftwareTeacher = serializers.BooleanField(source='is_software_teacher', default=False, required=False)
    availableTypes = serializers.JSONField(source='available_types', default=list, required=False)
    campusPreference = serializers.CharField(source='campus_preference', allow_blank=True, required=False)
    unavailableTimes = serializers.CharField(source='unavailable_times', allow_blank=True, required=False)
    avoidTeacherNames = serializers.CharField(source='avoid_teacher_names', allow_blank=True, required=False)
    remark = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = Teacher
        fields = [
            'id', 'name', 'college', 'isExternal', 'isActive', 'memberEligible', 'isSoftwareTeacher', 'title', 'roles',
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['isSoftwareTeacher'] = instance.is_software_teacher or (
            not instance.is_external and '软件' in (instance.college or '')
        )
        return data

    @transaction.atomic
    def create(self, validated_data):
        instance = super().create(validated_data)
        sync_teacher_rename(instance, instance.name)
        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        previous_name = Teacher.objects.select_for_update().get(pk=instance.pk).name
        instance = super().update(instance, validated_data)
        sync_teacher_rename(instance, previous_name)
        return instance


class StudentSerializer(serializers.ModelSerializer):
    import_unique_fields = [('studentNo', '学号重复，请检查导入数据')]

    studentNo = serializers.CharField(source='student_no', allow_blank=True, allow_null=True, required=False)
    gender = serializers.CharField(allow_blank=True, required=False)
    studentType = serializers.CharField(source='student_type', required=False)
    mentorName = serializers.CharField(source='mentor_name', allow_blank=True, required=False)
    mentorId = serializers.PrimaryKeyRelatedField(source='mentor', queryset=Teacher.objects.all(), allow_null=True, required=False)
    defenseTypes = serializers.JSONField(source='defense_types', default=list, required=False)
    secretaryName = serializers.CharField(source='secretary_name', allow_blank=True, required=False)
    secretaryId = serializers.PrimaryKeyRelatedField(source='bound_secretary', queryset=Teacher.objects.all(), allow_null=True, required=False)
    remark = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = Student
        fields = [
            'id', 'name', 'studentNo', 'gender', 'studentType', 'mentorName', 'mentorId',
            'campus', 'defenseTypes', 'secretaryName', 'secretaryId', 'remark'
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
        try:
            return sync_student_references(attrs, self.instance)
        except ReferenceDataError as exc:
            raise serializers.ValidationError(exc.errors)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.mentor_id:
            data['mentorName'] = instance.mentor.name
        if instance.bound_secretary_id:
            data['secretaryName'] = instance.bound_secretary.name
        return data


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
        data = merge_rule_config(default_rule_config(instance.defense_type), instance.config)
        data['defenseType'] = DEFENSE_TYPE_LABELS.get(instance.defense_type, instance.defense_type)
        data['updatedAt'] = instance.updated_at.isoformat()
        return data

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({'config': ['规则配置必须是对象']})
        payload = dict(data)
        defense_type = payload.pop('defense_type', None) or DEFENSE_TYPE_VALUES.get(payload.get('defenseType'))
        if not defense_type and self.instance:
            defense_type = self.instance.defense_type
        if not defense_type:
            raise serializers.ValidationError({'defense_type': '缺少答辩类型'})
        if defense_type not in DEFENSE_TYPE_LABELS:
            raise serializers.ValidationError({'defense_type': ['不支持的答辩类型']})
        config = default_rule_config(defense_type)
        if self.instance and self.instance.defense_type == defense_type:
            config = merge_rule_config(config, self.instance.config)
        config = merge_rule_config(config, payload)
        config['defenseType'] = DEFENSE_TYPE_LABELS.get(defense_type, config.get('defenseType', defense_type))
        config.pop('updatedAt', None)
        config['policyVersion'] = 2
        config['softwareTeacherMin'] = config['formalSoftwareMin'] if defense_type == 'formal' else 0
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
