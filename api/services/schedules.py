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

    def prepare_generation_rules(self, rules):
        rules = dict(rules)
        if (rules.get('policy_version') == 3 and rules['defense_type'] == 'formal'
                and rules.get('preserve_pre_defense_groups', True)):
            source = ScheduleVersion.objects.filter(defense_type='pre', is_current=True).first()
            if not source or (not source.groups.exists() and not rules.get('linked_translation')):
                raise ValueError('请先生成并核对预答辩分组，再平移到正式答辩')
            if rules['start_date'] <= source.rules_snapshot.get('end_date', ''):
                raise ValueError('正式答辩开始日期必须晚于预答辩结束日期')
            if rules['expert_count'] < source.rules_snapshot.get('expert_count', 3):
                raise ValueError('平移后专家人数不能少于预答辩')
            rules.update(linked_translation=True,
                         external_expert_max=max(rules.get('external_expert_max', 1),
                                                source.rules_snapshot.get('external_expert_max', 1)),
                         source_chair_title=source.rules_snapshot.get('chair_title', '副教授'),
                         avoid_supervisor=False, supervisor_policy='same_group')
        return rules

    def preflight_check(self, rules, *, check_inherited_groups=True):
        """生成排期前的资料预检，返回可生成状态、错误、警告和统计信息。"""
        rules = self._normalize_rules(rules)
        payload, notices = self._build_algorithm_input(
            rules['defense_type'], self._extract_rule_date_range(rules), rules)

        defense_label = DEFENSE_TYPE_LABELS[rules['defense_type']]

        # 收集所有相关学生ID，用于批量查询姓名
        all_student_ids = set()
        for notice in notices:
            for rid in notice.get('related_ids', []):
                all_student_ids.add(rid)
        for s in payload['students']:
            all_student_ids.add(s['id'])

        student_names_by_id = {}
        if all_student_ids:
            student_names_by_id = dict(
                Student.objects.filter(id__in=all_student_ids).values_list('id', 'name')
            )

        # 阻断生成的错误类型
        ERROR_TYPES = set() if rules.get('policy_version') == 3 else {'mentor_missing'}
        if rules.get('policy_version', 1) == 2:
            ERROR_TYPES.update({'mentor_not_found', 'mentor_unavailable_for_defense'})

        # 按类型聚合 notices
        aggregated = {}
        for notice in notices:
            notice_type = notice.get('type', 'unknown')
            if notice_type not in aggregated:
                aggregated[notice_type] = {
                    'type': notice_type,
                    'student_ids': [],
                    'teacher_names': [],
                    'count': 0,
                }
            agg = aggregated[notice_type]
            related_ids = notice.get('related_ids', [])
            agg['student_ids'].extend(related_ids)
            teacher_name = notice.get('teacher_name')
            if teacher_name and teacher_name not in agg['teacher_names']:
                agg['teacher_names'].append(teacher_name)
            agg['count'] += len(related_ids) if related_ids else 1

        # 各类型的描述与建议
        TYPE_INFO = {
            'mentor_missing': {
                'description': '学生尚未设置导师',
                'suggestion': '前往学生名单补充导师信息',
                'has_students': True,
            },
            'mentor_not_found': {
                'description': '导师姓名在教师表中不存在',
                'suggestion': '核对导师姓名是否与教师表完全一致',
                'has_students': True,
            },
            'mentor_unavailable_for_defense': {
                'description': '导师未设置为可参加该答辩类型',
                'suggestion': '在教师数据中补充可参加答辩类型',
                'has_students': True,
            },
            'secretary_not_found': {
                'description': '秘书姓名在教师表中不存在',
                'suggestion': '核对秘书姓名是否与教师表完全一致',
                'has_students': True,
            },
            'secretary_unavailable_for_defense': {
                'description': '秘书未设置为可参加该答辩类型',
                'suggestion': '在教师数据中补充可参加答辩类型',
                'has_students': True,
            },
            'student_defense_type_missing': {
                'description': '学生未设置参加答辩类型',
                'suggestion': '在学生数据中设置参加答辩类型',
                'has_students': True,
            },
            'invalid_time_format': {
                'description': '时间格式无法识别',
                'suggestion': '检查教师或教室的时间格式是否正确',
                'has_students': False,
            },
            'availability_pending': {
                'description': '部分教师未提供额外时间限制，草稿暂按无额外限制计算，到场时间仍需核对',
                'suggestion': '已有课表及时间限制仍生效；请在教师资料核对额外限制，确认后可消除此提醒',
                'has_students': False,
            },
            'remark_confirmation': {
                'description': '部分教师备注需要确认，暂未转换为排班规则',
                'suggestion': '核对教师备注，使用可用时间及同组多名学生等结构化配置',
                'has_students': False,
            },
        }

        def _build_item(notice_type, agg, level):
            info = TYPE_INFO.get(notice_type, {
                'description': notice_type,
                'suggestion': '请检查相关数据',
                'has_students': True,
            })
            display_names = []
            if info['has_students']:
                # 收集学生姓名，去重并保持顺序，最多显示5个
                names = [student_names_by_id.get(sid, f'ID:{sid}') for sid in agg['student_ids']]
                seen = set()
                unique_names = []
                for n in names:
                    if n not in seen:
                        seen.add(n)
                        unique_names.append(n)
                display_names = unique_names[:5]
            count = agg['count']
            return {
                'type': notice_type,
                'level': level,
                'description': info['description'],
                'studentNames': display_names,
                'teacherNames': agg['teacher_names'],
                'count': count,
                'suggestion': info['suggestion'],
            }

        errors = []
        warnings = []

        for notice_type, agg in aggregated.items():
            level = 'error' if notice_type in ERROR_TYPES else 'warning'
            item = _build_item(notice_type, agg, level)
            if level == 'error':
                errors.append(item)
            else:
                warnings.append(item)

        # 没有学生参加本次答辩
        if not payload['students']:
            errors.append({
                'type': 'no_students',
                'level': 'error',
                'description': f'没有学生参加【{defense_label}】',
                'studentNames': [],
                'count': 0,
                'suggestion': '请检查学生数据中的"参加答辩类型"设置',
            })

        # 没有可参加的教师
        if not payload['teachers']:
            (warnings if rules.get('policy_version') == 3 else errors).append({
                'type': 'no_teachers',
                'level': 'warning' if rules.get('policy_version') == 3 else 'error',
                'description': f'没有可参加【{defense_label}】的教师',
                'studentNames': [],
                'count': 0,
                'suggestion': '请检查教师数据中的"可参加答辩类型"设置',
            })

        from scheduling.preflight import (external_mentor_capacity_issues, inherited_group_size_issues,
                                          resource_availability_issues)
        errors.extend(external_mentor_capacity_issues(payload, rules))
        if check_inherited_groups:
            errors.extend(inherited_group_size_issues(payload, rules))
        if rules.get('policy_version') != 3:
            warnings.extend(resource_availability_issues(payload, rules))
        can_generate = len(errors) == 0

        return {
            'canGenerate': can_generate,
            'errors': errors,
            'warnings': warnings,
            'stats': {
                'studentCount': len(payload['students']),
                'teacherCount': len(payload['teachers']),
                'roomCount': len(payload['rooms']),
            },
        }

    def generate_version(self, rules, request_key=None):
        """Compute and persist a draft. Caller holds the schedule write transaction."""
        rules = self.prepare_generation_rules(rules)
        from algorithm import SchedulingError, generate_schedule
        preflight = self.preflight_check(rules)
        if not preflight['canGenerate']:
            messages = [item['description'] for item in preflight['errors']]
            raise ValueError('生成前资料预检未通过：' + '；'.join(messages))
        source_pre = None
        if rules['defense_type'] == 'formal' and rules.get('preserve_pre_defense_groups', True):
            source_pre = ScheduleVersion.objects.filter(defense_type='pre', is_current=True).first()
        input_rules = {**rules, '_source_pre_version_id': source_pre.pk if source_pre else None}
        payload, notices = self._build_algorithm_input(
            rules['defense_type'], self._extract_rule_date_range(rules), input_rules)
        label = DEFENSE_TYPE_LABELS[rules['defense_type']]
        if not payload['students']:
            raise ValueError(f'没有学生参加【{label}】，请检查学生数据中的"参加答辩类型"设置')
        if not payload['teachers'] and rules.get('policy_version') != 3:
            raise ValueError(f'没有可参加【{label}】的教师，请检查教师数据中的"可参加答辩类型"设置')
        try:
            if rules.get('linked_translation') and source_pre:
                from algorithm import GroupDraft, parse_teacher, parse_student, parse_time_range
                from scheduling.translation import translate_panels
                source = [GroupDraft(g.group_id, g.campus, list(g.students.values_list('pk', flat=True)),
                    parse_time_range(g.time), None, g.chair_id, list(g.experts.values_list('pk', flat=True)), g.secretary_id)
                    for g in source_pre.groups.prefetch_related('students', 'experts')]
                result = translate_panels(source, [parse_teacher(t) for t in payload['teachers']],
                    [parse_student(s) for s in payload['students']], rules)
            else:
                from .pre_plan_cache import read_pre_plan, remember_pre_plan
                result = read_pre_plan(payload, rules) if rules['defense_type'] == 'pre' else None
                if result is None:
                    result = generate_schedule(**payload, rules=rules)
                if rules['defense_type'] == 'pre':
                    remember_pre_plan(payload, rules, result)
        except (SchedulingError, ValueError, TypeError) as exc:
            raise ValueError(f'排期参数错误: {exc}')
        # 将使用的随机种子持久化到规则快照，便于复现
        if result.get('random_seed') is not None:
            rules['random_seed'] = result['random_seed']
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
        if rules.get('policy_version') == 3 and any(c['type'] == 'missing_student' for c in conflicts):
            notices.extend(c for c in schedule_version.conflicts_snapshot if c.get('type') == 'search_limit')
        return deduplicate_conflicts(notices + conflicts)
