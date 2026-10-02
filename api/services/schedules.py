"""Application operations for schedule generation and validation.

The HTTP facade supplies presentation and archival callbacks; all ORM-to-engine
conversion is isolated in scheduling_input and scenario rules live in scheduling.
"""
from datetime import datetime
from django.db.models import Max
from ..models import Group, ScheduleVersion, Student, Teacher
from ..serializers import DEFENSE_TYPE_LABELS
from .scheduling_input import build_algorithm_input
from .rules import normalize_schedule_rules

class ScheduleApplication:
    RULE_KEY_ALIASES = {'mentor_avoidance': 'avoid_supervisor'}

    def _build_algorithm_input(self, defense_type, date_range=None, rules=None, *, secretary_bindings=None):
        return build_algorithm_input(defense_type, date_range, rules, secretary_bindings=secretary_bindings)

    def _normalize_rules(self, rules):
        return normalize_schedule_rules(rules)

    def generate_version(self, rules, request_key=None):
        """Compute and persist a draft. Caller holds the schedule write transaction."""
        from algorithm import SchedulingError, generate_schedule
        source_pre = None
        if rules['defense_type'] == 'formal' and rules.get('preserve_pre_defense_groups', True):
            source_pre = ScheduleVersion.objects.filter(defense_type='pre', is_current=True).first()
        input_rules = {**rules, '_source_pre_version_id': source_pre.pk if source_pre else None}
        payload, notices = self._build_algorithm_input(
            rules['defense_type'], self._extract_rule_date_range(rules), input_rules)
        label = DEFENSE_TYPE_LABELS[rules['defense_type']]
        if not payload['students']:
            raise ValueError(f'没有学生参加【{label}】，请检查学生数据中的"参加答辩类型"设置')
        if not payload['teachers']:
            raise ValueError(f'没有可参加【{label}】的教师，请检查教师数据中的"可参加答辩类型"设置')
        try:
            result = generate_schedule(**payload, rules=rules)
        except (SchedulingError, ValueError, TypeError) as exc:
            raise ValueError(f'排期参数错误: {exc}')
        for old in ScheduleVersion.objects.filter(defense_type=rules['defense_type'], is_current=True):
            self._freeze_version(old)
        ScheduleVersion.objects.filter(defense_type=rules['defense_type']).update(is_current=False)
        number = (ScheduleVersion.objects.filter(defense_type=rules['defense_type']).aggregate(n=Max('version'))['n'] or 0) + 1
        version = ScheduleVersion.objects.create(version=number, defense_type=rules['defense_type'],
            rules_snapshot=rules, input_snapshot=payload, request_key=request_key,
            source_pre_version=source_pre, is_current=True)
        group_map = {}
        for row in result['groups']:
            group = Group.objects.create(schedule_version=version, group_id=row['group_id'],
                time=row.get('time') or '', room_id=row.get('room_id'), campus=row.get('campus') or '',
                chair_id=row.get('chair_id'), secretary_id=row.get('secretary_id'))
            group.experts.set(row.get('expert_ids', []))
            group.students.set(row.get('student_ids', []))
            group_map[group.group_id] = group.pk
        version.conflicts_snapshot = notices + [dict(c, group_db_ids=[group_map[g]
            for g in c.get('related_ids', []) if isinstance(g, str) and g in group_map]) for c in result['conflicts']]
        version.save(update_fields=['conflicts_snapshot'])
        if rules['defense_type'] == 'pre':
            self._sync_student_secretaries(version)
        return version


    @staticmethod
    def _extract_rule_date_range(rules):
        """从规则中提取排期日期范围（date 元组），供周期性时间描述展开；无效时返回 None"""
        try:
            start = datetime.strptime(str(rules.get('start_date') or ''), '%Y-%m-%d').date()
            end = datetime.strptime(str(rules.get('end_date') or ''), '%Y-%m-%d').date()
        except ValueError:
            return None
        if end < start:
            return None
        return (start, end)


    def _sync_student_secretaries(self, schedule_version, group_id=None):
        """把预答辩各组的秘书写回组内学生的"对应秘书姓名"字段"""
        groups = schedule_version.groups.select_related('secretary').prefetch_related('students')
        if group_id is not None:
            groups = groups.filter(pk=group_id)
        for group in groups:
            if not group.secretary:
                continue
            secretary_name = group.secretary.name
            for student in group.students.all():
                if student.secretary_name != secretary_name or student.bound_secretary_id != group.secretary_id:
                    student.secretary_name = secretary_name
                    student.bound_secretary_id = group.secretary_id
                    student.save(update_fields=['secretary_name', 'bound_secretary'])

    def _set_formal_secretary_bindings(self, version, student_ids, secretary_id):
        """An explicit formal-stage edit overrides this version's saved binding."""
        if version.defense_type != 'formal':
            return
        from copy import deepcopy
        payload = deepcopy(version.input_snapshot)
        for student in payload.get('students', []):
            if student['id'] in student_ids:
                student['secretary_id'] = secretary_id
        version.input_snapshot = payload
        version.save(update_fields=['input_snapshot'])


    def _check_conflicts(self, schedule_version):
        from algorithm import (GroupDraft, SchedulingError, detect_global_conflicts,
                               parse_teacher, parse_student, parse_room, parse_time_range, deduplicate_conflicts)
        if schedule_version.result_snapshot or schedule_version.export_snapshot:
            return schedule_version.conflicts_snapshot
        rules = schedule_version.rules_snapshot or {}
        validation_rules = {**rules, '_source_pre_version_id': schedule_version.source_pre_version_id}
        # Refresh is a generation command. Later edits must validate the binding
        # established by that command rather than clear it again.
        validation_rules.pop('refresh_secretary_bindings', None)
        original_bindings = {s['id']: s for s in schedule_version.input_snapshot.get('students', [])}
        secretary_bindings = ({sid: s.get('secretary_id') for sid, s in original_bindings.items()}
            if schedule_version.defense_type == 'formal' else None)
        payload, notices = self._build_algorithm_input(schedule_version.defense_type,
            self._extract_rule_date_range(rules), validation_rules, secretary_bindings=secretary_bindings)
        if schedule_version.defense_type == 'formal':
            for student in payload['students']:
                original = original_bindings.get(student['id'])
                if original:
                    student['previous_group_id'] = original.get('previous_group_id')
                    student['secretary_id'] = original.get('secretary_id')
        drafts, group_map = [], {}
        for group in schedule_version.groups.select_related('room', 'chair', 'secretary').prefetch_related('experts', 'students'):
            group_map[group.group_id] = group.id
            try:
                slot = parse_time_range(group.time) if group.time else None
            except SchedulingError:
                slot = None
            drafts.append(GroupDraft(group.group_id, group.campus, [s.id for s in group.students.all()],
                slot, group.room_id, group.chair_id, [t.id for t in group.experts.all()], group.secretary_id))
        conflicts = detect_global_conflicts(drafts, [parse_student(s) for s in payload['students']],
            [parse_teacher(t) for t in payload['teachers']], [parse_room(r) for r in payload['rooms']], rules)
        for conflict in conflicts:
            conflict['group_db_ids'] = [group_map[g] for g in conflict.get('related_ids', []) if isinstance(g, str) and g in group_map]
        return deduplicate_conflicts(notices + conflicts)
