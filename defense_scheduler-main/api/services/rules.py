"""Canonical API-to-engine rules, with an explicit legacy compatibility boundary."""
from rest_framework.exceptions import ValidationError
from ..serializers import default_rule_config


def normalize_schedule_rules(raw):
    if not isinstance(raw, dict):
        raise ValidationError('排期规则必须是对象')
    rules = dict(raw)
    for internal_key in ('_source_pre_version_id', 'reserve_formal_resources', 'refresh_secretary_bindings'):
        rules.pop(internal_key, None)
    defense_type = rules.setdefault('defense_type', 'pre')
    if defense_type not in ('pre', 'formal', 'mid'):
        raise ValidationError('未知答辩类型')
    if 'mentor_avoidance' in rules and 'avoid_supervisor' not in rules:
        rules['avoid_supervisor'] = rules['mentor_avoidance']
    # Historical integrations supplied low-level counts without a schema version.
    # Keep those contracts readable; all new UI configurations use schema 2.
    version = rules.setdefault('policy_version', 1 if 'expert_count' in raw else 2)
    if isinstance(version, bool) or not isinstance(version, int) or version not in (1, 2):
        raise ValidationError('不支持的规则版本')
    if version == 1:
        return rules
    config = default_rule_config(defense_type)
    defaults = {
        'start_date': config['startDate'], 'end_date': config['endDate'],
        'group_size': config['studentCount']['target'],
        'group_min': config['studentCount']['min'], 'group_max': config['studentCount']['max'],
        'expert_count': config['expertCount']['target'], 'expert_min': config['expertCount']['min'],
        'avoid_weekend': config['avoidWeekend'], 'avoid_holiday': config['avoidHoliday'],
        'exclude_dates': [], 'course_half_day_blocking': True,
        'formal_software_min': 3, 'include_remarks': True, 'preserve_pre_defense_groups': True,
        'formal_mentor_same_session': defense_type == 'formal',
        'chair_title': '教授' if defense_type == 'formal' else '副教授',
        'secretary_title': '讲师', 'prefer_senior': True,
        'grouping': 'secretary' if defense_type == 'formal' else 'supervisor',
        'campus_start_dates': {},
        'soft_weights': {
            'balance_student_count': config['softWeights']['balanceStudentCount'],
            'prefer_senior_teacher': config['softWeights']['preferSeniorTeacher'],
            'avoid_cross_campus': config['softWeights']['avoidCrossCampus'],
            'external_mentor_concentration': config['softWeights']['externalMentorConcentration'],
            'prefer_academic_master_first': config['softWeights']['preferAcademicMasterFirst'],
        },
    }
    for key, value in defaults.items():
        rules.setdefault(key, value)
    from datetime import datetime
    starts = rules['campus_start_dates']
    if not isinstance(starts, dict) or any(key not in ('创新港', '兴庆') for key in starts):
        raise ValidationError('分校区开始日期格式不正确')
    try:
        start_date = datetime.strptime(rules['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(rules['end_date'], '%Y-%m-%d').date()
        if end_date < start_date:
            raise ValueError
        for value in starts.values():
            day = datetime.strptime(value, '%Y-%m-%d').date()
            if not start_date <= day <= end_date:
                raise ValueError
    except (ValueError, TypeError):
        raise ValidationError('开始、结束及分校区日期必须有效，且校区日期需在本次排期范围内')
    for key in ('avoid_weekend', 'avoid_holiday', 'course_half_day_blocking', 'include_remarks',
                'preserve_pre_defense_groups', 'formal_mentor_same_session'):
        if not isinstance(rules[key], bool):
            raise ValidationError(f'{key} 必须为布尔值')
    if 'avoid_supervisor' in rules and not isinstance(rules['avoid_supervisor'], bool):
        raise ValidationError('导师回避开关必须为布尔值')
    rules['expert_count_includes_chair'] = True
    rules['need_chair'] = True
    rules['secretary_count'] = 1
    ranks = {'助教': 0, '讲师': 1, '副教授': 2, '副高': 2, '教授': 3, '正高': 3,
        'lecturer': 1, 'associate professor': 2, 'professor': 3, '副研究员': 2, '研究员': 3}
    if not isinstance(rules['chair_title'], str) or ranks.get(rules['chair_title'], -1) < (3 if defense_type == 'formal' else 2):
        raise ValidationError('主席/组长职称不能低于业务要求')
    if not isinstance(rules['secretary_title'], str) or ranks.get(rules['secretary_title'], -1) < 1:
        raise ValidationError('秘书职称必须为讲师及以上')
    if rules['course_half_day_blocking'] is not True:
        raise ValidationError('有课的半天不能安排答辩')
    if defense_type == 'formal' and rules['formal_mentor_same_session'] is not True:
        raise ValidationError('正式答辩导师必须与自己的学生同场到场')
    avoidance = bool(rules.get('avoid_supervisor', defense_type == 'formal'))
    rules['avoid_supervisor'] = defense_type == 'formal' and avoidance
    rules['supervisor_policy'] = ('avoid' if avoidance else 'none') if defense_type == 'formal' else 'same_group'
    if defense_type == 'formal' and (rules['expert_count'] != 5 or rules['expert_min'] != 5):
        raise ValidationError('正式答辩必须配置 5 位专家（含主席）')
    floor = 4 if defense_type == 'pre' else 5
    try:
        if any(isinstance(rules[k], bool) or not isinstance(rules[k], int) for k in (
            'expert_count', 'expert_min', 'group_min', 'group_size', 'group_max', 'formal_software_min')):
            raise ValueError
        if not floor <= rules['expert_min'] <= rules['expert_count']:
            raise ValueError
        if not 1 <= rules['group_min'] <= rules['group_size'] <= rules['group_max']:
            raise ValueError
        if defense_type == 'mid' and not 10 <= rules['group_min'] <= rules['group_size'] <= rules['group_max'] <= 13:
            raise ValueError
        if defense_type == 'formal' and not 3 <= rules['formal_software_min'] <= 5:
            raise ValueError
    except (TypeError, ValueError):
        raise ValidationError('人数规则不符合本类答辩的资格要求')
    return rules
