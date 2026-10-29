"""Schedule HTTP endpoints and frontend response presentation."""
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet
from .models import Group, Room, ScheduleVersion, Student, Teacher
from .permissions import IsAdminUser, is_admin_user
from .schedule_integrity import schedule_write, audit, capture_export_groups, export_groups
from .serializers import DEFENSE_TYPE_LABELS, ScheduleVersionSerializer
from .services.schedules import ScheduleApplication
from .services.time_data import validate_schedule_time_text

class ScheduleViewSet(ScheduleApplication, GenericViewSet):
    queryset = ScheduleVersion.objects.all()

    serializer_class = ScheduleVersionSerializer

    read_actions = {
        'current', 'export', 'export_excel', 'export_word', 'export_conclusion',
        'check_conflicts', 'versions', 'record_pdf_export',
    }

    def get_permissions(self):
        if self.action in self.read_actions:
            return [IsAuthenticated()]
        return [IsAdminUser()]

    CONFLICT_TYPE_LABELS = {
        **{key: (label, 'error') for key, label in {
            'duplicate_student': '学生重复分组', 'missing_student': '学生未分组',
            'teacher_unavailable': '人员不可用', 'role_conflict': '人员角色冲突',
            'room_capacity': '教室容量不足',
        }.items()},
        'half_day_coverage': ('上午下午覆盖提示', 'warning'),
        'external_distribution': ('外院专家分布提示', 'warning'),
        'student_group_exception': ('学生分组人数提示', 'warning'),
        'mentor_student_imbalance': ('组内导师学生数不均衡', 'warning'),
        'mentor_share_exception': ('已解释的导师人数例外', 'info'),
        'chair_title_relaxed': ('主席职称放宽提示', 'warning'),
        'formal_group_order': ('正式答辩组号时序冲突', 'error'),
        'pre_group_order': ('预答辩组号时序冲突', 'error'),
        'pre_group_capacity': ('预答辩人数与组长资格冲突', 'warning'),
        'remark_confirmation': ('教师备注待确认', 'warning'),
        'availability_pending': ('教师可用时间待确认', 'warning'),
        'search_limit': ('排期搜索范围提示', 'warning'),
        'time_conflict': ('时间冲突', 'error'),
        'teacher_time_conflict': ('时间冲突', 'error'),
        'room_conflict': ('教室冲突', 'error'),
        'room_or_time_unavailable': ('教室冲突', 'error'),
        'insufficient_experts': ('人员冲突', 'error'),
        'chair_unavailable': ('人员冲突', 'error'),
        'secretary_unavailable': ('人员冲突', 'error'),
        'supervisor_avoidance': ('导师回避冲突', 'error'),
        'supervisor_missing': ('导师未与学生同组', 'error'),
        'pre_reviewer_without_student': ('预答辩评审无本组学生', 'error'),
        'secretary_student_conflict': ('秘书学生冲突', 'error'),
        'secretary_is_supervisor': ('秘书学生冲突', 'error'),
        'secretary_continuity_broken': ('秘书连续性提示', 'warning'),
        'campus_mismatch': ('校区切换提示', 'warning'),
        'student_defense_type_missing': ('数据完整性提示', 'warning'),
        'group_size_out_of_range': ('人数规则冲突', 'error'),
        'invalid_time_format': ('数据完整性提示', 'error'),
        'mentor_not_found': ('数据完整性提示', 'warning'),
        'mentor_unavailable_for_defense': ('数据完整性提示', 'warning'),
        'secretary_not_found': ('数据完整性提示', 'warning'),
        'secretary_unavailable_for_defense': ('数据完整性提示', 'warning'),
        'expert_count_out_of_range': ('专家人数冲突', 'error'),
        'software_majority': ('软件学院专家人数不足', 'error'),
        'member_ineligible': ('组员资格冲突', 'error'),
        'role_qualification': ('角色资格冲突', 'error'),
        'teacher_inactive': ('人员已停用', 'error'),
        'formal_mentor_session_missing': ('导师与学生场次不一致', 'error'),
        'mentor_missing': ('学生缺少导师', 'error'),
        # [TASK-P05 新增] 外院导师组数不符作为错误，阻止发布。
        'external_mentor_group_count': ('外院导师分组冲突', 'error'),
        'external_mentor_concentration': ('外院教师集中安排提示', 'warning'),
        'software_participation_imbalance': ('软件学院评审次数均衡提示', 'warning'),
        'external_half_day_visit': ('外院教师半天到访提示', 'warning'),
        'cross_campus_same_day': ('教师同日跨校区提示', 'warning'),
    }

    RULE_KEY_ALIASES = {
        'mentor_avoidance': 'avoid_supervisor',
    }

    # 比较规则快照时忽略的内部字段（运行时生成，不影响业务规则一致性）
    _RULES_COMPARE_IGNORE = {'random_seed', '_source_pre_version_id',
                             'reserve_formal_resources', 'refresh_secretary_bindings',
                             'linked_translation', 'source_chair_title', 'formal_rotation', 'formal_group_order', 'pre_group_order'}

    @classmethod
    def _rules_equivalent(cls, a, b):
        """比较两份规则是否业务等价，忽略运行时生成的内部字段。"""
        if not isinstance(a, dict) or not isinstance(b, dict):
            return a == b
        # A server-generated seed must not break retries that omitted it. An
        # explicit seed in the new request is a business input and must match.
        if 'random_seed' in b and a.get('random_seed') != b['random_seed']:
            return False
        keys_a = set(a.keys()) - cls._RULES_COMPARE_IGNORE
        keys_b = set(b.keys()) - cls._RULES_COMPARE_IGNORE
        if keys_a != keys_b:
            return False
        for k in keys_a:
            if a[k] != b[k]:
                return False
        return True

    def _format_conflicts(self, schedule_version, raw_conflicts):
        """把英文冲突结构转换为前端 ScheduleConflict 形状（中文类型 + level/target/reason）"""
        group_name_map = {g.id: g.group_id for g in schedule_version.groups.all()}
        defense_label = schedule_version.get_defense_type_display()
        created_at = timezone.localtime(schedule_version.created_at).isoformat()

        formatted = []
        for index, item in enumerate(raw_conflicts or [], start=1):
            raw_type = item.get('type', '')
            label, level = self.CONFLICT_TYPE_LABELS.get(raw_type, (raw_type or '未知冲突', 'warning'))
            if schedule_version.rules_snapshot.get('policy_version', 1) >= 2 and raw_type in {
                'mentor_not_found', 'mentor_unavailable_for_defense', 'secretary_not_found', 'secretary_unavailable_for_defense',
                'secretary_continuity_broken'}:
                level = 'error'
            if raw_type == 'insufficient_experts':
                # 专家数达到配置下限时降级为警告，未达下限保持错误
                min_required = item.get('min_required') or 0
                if min_required and (item.get('assigned') or 0) >= min_required:
                    level = 'warning'

            group_ids = [
                gid for gid in (item.get('group_db_ids') or item.get('group_ids') or [])
                if gid in group_name_map
            ]
            if not group_ids and item.get('group_id') in group_name_map:
                group_ids = [item['group_id']]

            target = item.get('teacher_name') or item.get('room_name') or ''
            if not target and group_ids:
                target = group_name_map.get(group_ids[0], '')

            conflict = {
                'id': index,
                'defenseType': defense_label,
                'groupId': group_ids[0] if group_ids else None,
                'groupName': group_name_map.get(group_ids[0], '') if group_ids else '',
                'type': label,
                'level': level,
                'target': target,
                'reason': item.get('description', ''),
                'relatedGroupIds': group_ids,
                'createdAt': created_at,
            }
            if raw_type == 'software_participation_imbalance' and all(
                    item.get(key) is not None for key in (
                        'difference', 'max_count', 'max_teacher_names', 'min_count', 'min_teacher_names')):
                conflict['details'] = {
                    'softwareParticipationImbalance': {
                        'difference': item.get('difference'),
                        'maxCount': item.get('max_count'),
                        'maxTeachers': item.get('max_teacher_names', []),
                        'minCount': item.get('min_count'),
                        'minTeachers': item.get('min_teacher_names', []),
                    },
                }
            formatted.append(conflict)
        return formatted

    @action(detail=False, methods=['post'])
    def preflight(self, request):
        """生成排期前的资料预检，检查导师资料等是否齐全。"""
        from rest_framework.exceptions import ValidationError
        rules_raw = request.data.get('rules', {})
        if not isinstance(rules_raw, dict):
            return Response({'error': '规则必须是对象'}, status=400)
        linked_generation = request.data.get('linked_generation', False)
        if not isinstance(linked_generation, bool):
            return Response({'error': '联合预检标记必须为布尔值'}, status=400)
        try:
            # A linked plan will replace old pre-defense groups. Actual formal
            # generation still validates the freshly generated source groups.
            result = self.preflight_check(rules_raw, check_inherited_groups=not linked_generation)
        except ValidationError as exc:
            return Response({'error': str(exc.detail if hasattr(exc, 'detail') else exc)}, status=400)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        return Response(result)

    @action(detail=False, methods=['post'])
    @schedule_write
    def generate(self, request):
        rules = self._normalize_rules(request.data.get('rules', {}))
        try:
            rules = self.prepare_generation_rules(rules)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        request_key = request.data.get('request_key')
        if request_key and (not isinstance(request_key, str) or len(request_key) > 64):
            return Response({'error': '请求标识格式不正确'}, status=400)
        if request_key:
            previous = ScheduleVersion.objects.filter(request_key=request_key).first()
            if previous:
                if not self._rules_equivalent(previous.rules_snapshot, rules):
                    return Response({'error': '该请求标识已用于其他规则，请重新生成'}, status=409)
                return Response(self._version_result(previous))
        try:
            return Response(self._version_result(self.generate_version(rules, request_key or None)))
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)

    @action(detail=False, methods=['post'], url_path='generate-linked')
    @schedule_write
    def generate_linked(self, request):
        """Generate both stages atomically, preserving the pre-defense grouping."""
        import hashlib
        pre_raw, formal_raw = request.data.get('pre_rules', {}), request.data.get('formal_rules', {})
        if not isinstance(pre_raw, dict) or not isinstance(formal_raw, dict):
            return Response({'error': '两阶段规则必须是对象'}, status=400)
        pre_rules = self._normalize_rules({**pre_raw, 'defense_type': 'pre', 'policy_version': pre_raw.get('policy_version', 3)})
        pre_rules.update(reserve_formal_resources=True, refresh_secretary_bindings=True)
        formal_rules = self._normalize_rules({**formal_raw, 'defense_type': 'formal', 'policy_version': formal_raw.get('policy_version', 3),
            'preserve_pre_defense_groups': True, 'formal_mentor_same_session': True})
        if pre_rules['policy_version'] == 3:
            # 正式答辩沿用本轮预答辩的学生和秘书，评审全部轮换；派生规则与单独生成一致
            self._apply_formal_rules(formal_rules, pre_rules['chair_title'])
        if formal_rules['start_date'] <= pre_rules['end_date']:
            return Response({'error': '正式答辩开始日期必须晚于预答辩结束日期'}, status=400)
        key = request.data.get('request_key')
        if key and (not isinstance(key, str) or len(key) > 64):
            return Response({'error': '请求标识格式不正确'}, status=400)
        keys = [hashlib.sha256(f'linked:{key}:{stage}'.encode()).hexdigest() if key else None
            for stage in ('pre', 'formal')]
        if key:
            previous = [ScheduleVersion.objects.filter(request_key=k).first() for k in keys]
            if any(previous):
                if not all(previous) or any(
                    not self._rules_equivalent(v.rules_snapshot, r)
                    for v, r in zip(previous, (pre_rules, formal_rules))
                ):
                    return Response({'error': '该请求标识已用于其他联合规则'}, status=409)
                return Response({'pre': self._version_result(previous[0]), 'formal': self._version_result(previous[1])})
        try:
            pre_version = self.generate_version(pre_rules, keys[0])
            formal_version = self.generate_version(formal_rules, keys[1])
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        return Response({'pre': self._version_result(pre_version), 'formal': self._version_result(formal_version)})

    @action(detail=False, methods=['get'])
    def current(self, request):
        """获取当前生效的排期"""
        defense_type = request.query_params.get('defense_type', 'pre')
        schedule_version = self._selected_version(request, defense_type)

        if not schedule_version:
            return Response({
                'defenseType': defense_type,
                'generatedAt': '',
                'groups': [],
                'conflicts': [],
                'message': '暂无排期结果'
            })

        return Response(self._version_result(schedule_version))

    def _selected_version(self, request, defense_type):
        from rest_framework.exceptions import ValidationError
        queryset = ScheduleVersion.objects.filter(defense_type=defense_type)
        if not is_admin_user(request.user):
            queryset = queryset.filter(status='published')
        version_id = request.query_params.get('version_id') or request.data.get('version_id')
        if version_id:
            try:
                return queryset.filter(pk=int(version_id)).first()
            except (ValueError, TypeError):
                raise ValidationError('版本 ID 格式不正确')
        return queryset.filter(is_current=True).first() if is_admin_user(request.user) else queryset.first()

    # [TASK-P09/P12 修改] 实时及冻结版本响应补足评分和版本化导出所需字段。
    def _version_result(self, schedule_version):
        if schedule_version.result_snapshot:
            result = {**schedule_version.result_snapshot}
            teacher_snapshot = {str(teacher.get('id')): teacher
                               for teacher in schedule_version.input_snapshot.get('teachers', [])}
            result['groups'] = [{**group, 'students': [
                {**student, 'mentorIsExternal': student.get('mentorIsExternal',
                    teacher_snapshot.get(str(student.get('mentorId')), {}).get('is_external'))}
                for student in group.get('students', [])
            ]} for group in result.get('groups', [])]
            result.setdefault('rules', schedule_version.rules_snapshot)
            return {**result, 'status': schedule_version.status, 'revision': schedule_version.revision, 'isCurrent': schedule_version.is_current}
        groups = export_groups(schedule_version)
        formatted_groups = []
        teacher_external_by_id = dict(Teacher.objects.values_list('id', 'is_external'))
        teacher_external_by_name = dict(Teacher.objects.values_list('name', 'is_external'))
        for group in groups:
            time_parts = group.time.split(' ')
            date = time_parts[0] if len(time_parts) > 0 else ''
            time_range = time_parts[1] if len(time_parts) > 1 else ''

            formatted_groups.append({
                'id': group.id,
                'defenseType': schedule_version.get_defense_type_display(),
                'groupName': group.group_id,
                'campus': group.campus,
                'classroom': group.room.name if group.room else '待预约',
                'date': date,
                'timeRange': time_range,
                'chairman': group.chair.name if group.chair else None,
                'secretary': group.secretary.name if group.secretary else '未分配',
                'chairTitle': group.chair.title if group.chair else '',
                'chairIsExternal': group.chair.is_external if group.chair else None,
                'chairId': group.chair_id,
                'secretaryId': group.secretary_id,
                'teachers': [
                    {'id': t.id, 'name': t.name, 'title': t.title, 'roles': getattr(t, 'roles', []), 'isExternal': t.is_external}
                    for t in group.experts.all()
                ],
                'students': [self._student_schedule_payload(s, teacher_external_by_id, teacher_external_by_name)
                             for s in group.students.all()]
            })

        raw_conflicts = self._check_conflicts(schedule_version)
        return {
            'isCurrent': schedule_version.is_current,
            'versionId': schedule_version.id,
            'sourcePreVersionId': schedule_version.source_pre_version_id,
            'version': schedule_version.version,
            'revision': schedule_version.revision,
            'status': schedule_version.status,
            'rules': schedule_version.rules_snapshot,
            'defenseType': schedule_version.get_defense_type_display(),
            'generatedAt': timezone.localtime(schedule_version.created_at).strftime('%Y-%m-%d %H:%M'),
            'groups': sorted(formatted_groups, key=lambda g: (g['date'] or '9999', g['timeRange'], g['groupName'])),
            **self._allocation_summary(schedule_version, formatted_groups, raw_conflicts),
            'conflicts': self._format_conflicts(schedule_version, raw_conflicts)
        }

    def _allocation_summary(self, version, groups, conflicts):
        if version.rules_snapshot.get('policy_version') != 3:
            return {}
        scheduled = {s['id'] for group in groups for s in group['students']}
        reasons = {c.get('student_id'): c['description'] for c in [*conflicts, *version.conflicts_snapshot] if c.get('type') == 'missing_student'}
        students = version.input_snapshot.get('students', [])
        unassigned = [{'id': s['id'], 'name': s['name'], 'reason': reasons.get(s['id'], '未找到满足教师时间与专家资格的安排，已尝试局部补排')} for s in students if s['id'] not in scheduled]
        work = []
        for teacher in version.input_snapshot.get('teachers', []):
            tid = teacher['id']
            tasks = [g for g in groups if tid in {g.get('chairId'), g.get('secretaryId'), *[t['id'] for t in g['teachers']], *[s.get('mentorId') for s in g['students']]}]
            work.append({'id': tid, 'name': teacher['name'], 'supervisedStudents': sum(s.get('supervisor_id') == tid for s in students), 'groupCount': len(tasks), 'studentCount': sum(len(g['students']) for g in tasks), 'sessions': sorted({g['date'] + ' ' + g['timeRange'] for g in tasks})})
        return {'unassignedStudents': unassigned, 'teacherWorkloads': work, 'allocationStatus': 'partial' if unassigned else 'scheduled', 'totalStudents': len(students)}

    @staticmethod
    def _student_schedule_payload(student, teacher_external_by_id, teacher_external_by_name):
        mentor_id = getattr(student, 'mentor_id', None)
        mentor_name = student.mentor.name if mentor_id and hasattr(student, 'mentor') else student.mentor_name
        if mentor_id in teacher_external_by_id:
            mentor_is_external = teacher_external_by_id[mentor_id]
        else:
            mentor_is_external = teacher_external_by_name.get(mentor_name) if mentor_name else None
        return {
            'id': student.id,
            'name': student.name,
            'studentType': student.student_type,
            'mentorName': mentor_name,
            'mentorId': mentor_id,
            'mentorIsExternal': mentor_is_external,
            'secretaryId': getattr(student, 'bound_secretary_id', None),
            'secretaryName': student.bound_secretary.name if getattr(student, 'bound_secretary_id', None) and hasattr(student, 'bound_secretary') else student.secretary_name,
            'studentNo': student.student_no,
            'remark': student.remark,
        }

    @action(detail=False, methods=['post'], url_path='adjust-group')
    @schedule_write
    def adjust_group(self, request):
        """保存前端完整分组编辑表单。"""
        group_id = request.data.get('group_id')
        group_data = request.data.get('group_data') or {}
        if not isinstance(group_data, dict):
            return Response({'error': '分组数据格式不正确'}, status=400)
        for key in ('teachers', 'students'):
            if key in group_data and (not isinstance(group_data[key], list) or any(
                    not isinstance(item, dict) or type(item.get('id')) is not int or item['id'] <= 0
                    for item in group_data[key])):
                return Response({'error': f'{key} 必须提供有效的人员 ID 列表'}, status=400)
        if not group_id or not group_data:
            return Response({'error': '缺少必要参数'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=status.HTTP_404_NOT_FOUND)

        next_group_id = group_data.get('groupName') or group.group_id
        if not isinstance(next_group_id, str) or len(next_group_id) > 20:
            return Response({'error': '组名必须为不超过 20 个字符的文本'}, status=400)
        if (group.schedule_version.rules_snapshot.get('policy_version') == 3
                and group.schedule_version.defense_type in ('pre', 'formal')
                and next_group_id != group.group_id):
            return Response({'error': '预答辩组号确定后固定，正式答辩沿用同一组号'}, status=400)
        date = group_data.get('date')
        time_range = group_data.get('timeRange')
        next_time = group.time
        if date and time_range:
            try:
                next_time = validate_schedule_time_text(f'{date} {time_range}')
            except ValueError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        next_campus = group_data.get('campus') or group.campus

        room = None
        room_name = group_data.get('classroom')
        if group.schedule_version.rules_snapshot.get('policy_version') == 3 and room_name in ('待预约', '未分配'):
            room_name = None
        if room_name:
            room = Room.objects.filter(name=room_name, campus=next_campus).first()
            if not room:
                return Response({'error': f'教室不存在: {room_name}'}, status=status.HTTP_400_BAD_REQUEST)

        chair = None
        chair_name = group_data.get('chairman') or group_data.get('leader')
        chair_id = group_data.get('chairId')
        if chair_name or chair_id:
            try:
                chair = Teacher.objects.filter(pk=chair_id).first() if chair_id else Teacher.objects.filter(name=chair_name).first()
            except (ValueError, TypeError):
                return Response({'error': '主席/组长 ID 格式不正确'}, status=400)
            if not chair:
                return Response({'error': f'主席/组长不存在: {chair_name}'}, status=status.HTTP_400_BAD_REQUEST)
            if chair_name and chair_name != chair.name:
                return Response({'error': '主席/组长姓名与 ID 不一致，请刷新后重试'}, status=400)

        secretary = None
        secretary_name = group_data.get('secretary')
        secretary_id = group_data.get('secretaryId')
        if secretary_name or secretary_id:
            try:
                secretary = Teacher.objects.filter(pk=secretary_id).first() if secretary_id else Teacher.objects.filter(name=secretary_name).first()
            except (ValueError, TypeError):
                return Response({'error': '秘书 ID 格式不正确'}, status=400)
            if not secretary:
                return Response({'error': f'秘书不存在: {secretary_name}'}, status=status.HTTP_400_BAD_REQUEST)
            if secretary_name and secretary_name != secretary.name:
                return Response({'error': '秘书姓名与 ID 不一致，请刷新后重试'}, status=400)

        teacher_ids = [item.get('id') for item in group_data.get('teachers', []) if item.get('id')]
        student_ids = [item.get('id') for item in group_data.get('students', []) if item.get('id')]
        if teacher_ids:
            existing_teacher_ids = set(Teacher.objects.filter(id__in=teacher_ids).values_list('id', flat=True))
            missing_teacher_ids = sorted(set(teacher_ids) - existing_teacher_ids)
            if missing_teacher_ids:
                return Response({'error': f'教师不存在: {missing_teacher_ids}'}, status=status.HTTP_400_BAD_REQUEST)
        if student_ids:
            existing_student_ids = set(Student.objects.filter(id__in=student_ids).values_list('id', flat=True))
            missing_student_ids = sorted(set(student_ids) - existing_student_ids)
            if missing_student_ids:
                return Response({'error': f'学生不存在: {missing_student_ids}'}, status=status.HTTP_400_BAD_REQUEST)

        if len(student_ids) != len(set(student_ids)):
            return Response({'error': '学生列表包含重复人员'}, status=400)
        if Group.objects.filter(schedule_version=group.schedule_version, students__id__in=student_ids).exclude(pk=group.pk).exists():
            return Response({'error': '学生已在其他组，请使用移动学生操作'}, status=400)
        if Group.objects.filter(schedule_version=group.schedule_version, group_id=next_group_id).exclude(pk=group.pk).exists():
            return Response({'error': '同一版本内组名不能重复'}, status=400)
        if 'students' in group_data and group.students.exclude(pk__in=student_ids).exists():
            return Response({'error': '请使用移动学生操作将学生调到目标组，不能直接移除已分组学生'}, status=400)
        secretary_changed = secretary is not None and secretary.pk != group.secretary_id
        with transaction.atomic():
            group.group_id = next_group_id
            group.time = next_time
            group.campus = next_campus
            if room:
                group.room = room
            if chair:
                group.chair = chair
            if secretary:
                group.secretary = secretary
            group.save()
            if 'teachers' in group_data:
                group.experts.set(teacher_ids)
            if 'students' in group_data:
                group.students.set(student_ids)
            if secretary_changed:
                self._set_formal_secretary_bindings(group.schedule_version,
                    set(group.students.values_list('pk', flat=True)), secretary.pk)

        return Response({
            'success': True,
            'message': '调整保存成功',
            'updatedGroup': group_data,
            'conflicts': self._check_conflicts(group.schedule_version),
        })

    @action(detail=False, methods=['post'])
    @schedule_write
    def adjust(self, request):
        """人工调整：移动学生、更换专家、修改时间/教室"""
        action_type = request.data.get('action')

        if action_type == 'move_student':
            return self._move_student(request)
        elif action_type == 'change_expert':
            return self._change_expert(request)
        elif action_type == 'change_time':
            return self._change_time(request)
        elif action_type == 'change_room':
            return self._change_room(request)
        elif action_type == 'change_chair':
            return self._change_chair(request)
        elif action_type == 'change_secretary':
            return self._change_secretary(request)
        else:
            return Response(
                {'error': f'未知的 action: {action_type}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    # [TASK-P12 修改] Word 导出按所选版本传递备注配置和冲突信息。
    @action(detail=False, methods=['get'], url_path='export_word')
    def export_word(self, request):
        """导出学院归档格式的《学位论文答辩时间安排》Word 文档"""
        from .export_word import export_arrangement_document

        return self._word_form_response(request, export_arrangement_document,
                                        document_name='时间安排', audit_format='Word',
                                        ascii_slug='schedule')

    @action(detail=False, methods=['get'], url_path='export_conclusion')
    def export_conclusion(self, request):
        """导出学院归档格式的《评审小组结论》Word 文档（每组一页）"""
        from .export_conclusion import export_conclusion_document

        return self._word_form_response(request, export_conclusion_document,
                                        document_name='评审小组结论',
                                        audit_format='Word-评审结论',
                                        ascii_slug='conclusion')

    def _word_form_response(self, request, builder, *, document_name, audit_format, ascii_slug):
        """两种 Word 归档表共用的选版本、硬冲突拦截、备注开关和审计逻辑。"""
        defense_type = request.query_params.get('defense_type', 'pre')
        schedule_version = self._selected_version(request, defense_type)
        if not schedule_version:
            return Response({'error': '暂无排期结果可导出'}, status=404)
        blocking_conflicts = self._blocking_export_conflicts(schedule_version)
        if blocking_conflicts:
            return Response({
                'error': '当前排期存在硬冲突，处理冲突后才能导出',
                'conflicts': blocking_conflicts,
            }, status=400)

        from urllib.parse import quote

        defense_label = DEFENSE_TYPE_LABELS.get(defense_type, defense_type)
        conflicts = self._format_conflicts(schedule_version, self._check_conflicts(schedule_version))
        notes = self._include_remarks(schedule_version, request.query_params.get('include_remarks'))
        doc = builder(schedule_version, defense_type, notes, conflicts)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = (
            f"attachment; filename=defense_{ascii_slug}_{defense_type}.docx; "
            f"filename*=UTF-8''{quote(f'{defense_label}{document_name}.docx')}"
        )
        doc.save(response)
        audit(request, '导出', f'导出{defense_label}{document_name}（Word）',
              format=audit_format, defense_type=defense_type,
              version_id=schedule_version.id, version=schedule_version.version)
        return response

    @staticmethod
    def _include_remarks(schedule_version, raw_value):
        """备注开关：请求参数优先，否则沿用版本生成时的规则快照。"""
        if raw_value is not None:
            return raw_value.strip().lower() in {'1', 'true', 'yes', 'on'}
        rules = schedule_version.rules_snapshot or {}
        return rules.get('include_remarks', rules.get('includeRemarks', True))

    @action(detail=False, methods=['get'])
    def export(self, request):
        from .services.export_excel import build_schedule_workbook
        defense_type = request.query_params.get('defense_type', 'pre')
        version = self._selected_version(request, defense_type)
        if not version:
            return Response({'error': '暂无排期结果可导出'}, status=404)
        blocking_conflicts = self._blocking_export_conflicts(version)
        if blocking_conflicts:
            return Response({
                'error': '当前排期存在硬冲突，处理冲突后才能导出',
                'conflicts': blocking_conflicts,
            }, status=400)
        conflicts = self._format_conflicts(version, self._check_conflicts(version))
        include_remarks_param = request.query_params.get('include_remarks')
        include_remarks = (
            include_remarks_param.strip().lower() in {'1', 'true', 'yes', 'on'}
            if include_remarks_param is not None
            else None
        )
        workbook = build_schedule_workbook(version, defense_type, conflicts, include_remarks)
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename=defense_schedule_{defense_type}.xlsx'
        workbook.save(response)
        audit(request, '导出', f'导出{version.get_defense_type_display()}排期（Excel）',
              format='Excel', defense_type=defense_type,
              version_id=version.id, version=version.version)
        return response

    @action(detail=False, methods=['post'], url_path='record-pdf-export')
    def record_pdf_export(self, request):
        """Record that the browser successfully prepared the selected schedule for printing."""
        defense_type = request.data.get('defense_type', 'pre')
        version = self._selected_version(request, defense_type)
        if not version:
            return Response({'error': '暂无排期结果可记录'}, status=404)
        blocking_conflicts = self._blocking_export_conflicts(version)
        if blocking_conflicts:
            return Response({
                'error': '当前排期存在硬冲突，处理冲突后才能导出',
                'conflicts': blocking_conflicts,
            }, status=400)
        audit(request, '导出', f'准备打印{version.get_defense_type_display()}排期（PDF）',
              format='PDF', defense_type=defense_type,
              version_id=version.id, version=version.version)
        return Response({'message': 'PDF 打印操作已记录'})

    def _blocking_export_conflicts(self, version):
        conflicts = self._format_conflicts(version, self._check_conflicts(version))
        return [conflict for conflict in conflicts if conflict['level'] == 'error']

    @action(detail=False, methods=['get'], url_path='export-excel')
    def export_excel(self, request):
        defense_type = request.query_params.get('defense_type')
        defense_label = request.query_params.get('defenseType')
        if not defense_type and defense_label:
            defense_type = {'预答辩': 'pre', '正式答辩': 'formal', '中期答辩': 'mid'}.get(defense_label, defense_label)

        request.GET._mutable = True
        request.GET['defense_type'] = defense_type or 'pre'
        return self.export(request)

    @action(detail=False, methods=['post'], url_path='check-conflicts')
    def check_conflicts(self, request):
        """检测当前排期冲突"""
        defense_type = request.data.get('defense_type', 'pre')
        schedule_version = self._selected_version(request, defense_type)

        if not schedule_version:
            return Response([], status=status.HTTP_200_OK)

        return Response(
            self._format_conflicts(schedule_version, self._check_conflicts(schedule_version)),
            status=status.HTTP_200_OK,
        )

    def _move_student(self, request):
        student_id = request.data.get('student_id')
        from_group_id = request.data.get('from_group_id')
        to_group_id = request.data.get('to_group_id')

        if not all([student_id, from_group_id, to_group_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            from_group = Group.objects.select_related('schedule_version').get(id=from_group_id)
            to_group = Group.objects.get(id=to_group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        student = Student.objects.filter(id=student_id).first()
        if not student:
            return Response({'error': f'学生不存在: {student_id}'}, status=400)
        if not from_group.students.filter(id=student.id).exists():
            return Response({'error': f'学生不在原组: {student_id}'}, status=400)

        if from_group.pk == to_group.pk:
            return Response({'error': '请选择不同的目标组'}, status=400)
        preserve = request.data.get('preserve_secretary', True)
        move_mentor = request.data.get('move_mentor', True)
        if not isinstance(preserve, bool) or not isinstance(move_mentor, bool):
            return Response({'error': '关联移动选项必须为布尔值'}, status=400)
        replacement = None
        if not preserve and 'secretary_id' in request.data:
            try:
                replacement = Teacher.objects.filter(pk=request.data['secretary_id']).first()
            except (ValueError, TypeError):
                return Response({'error': '秘书 ID 格式不正确'}, status=400)
            if replacement is None:
                return Response({'error': '请选择有效的秘书'}, status=400)
        from .services.adjustments import move_student_bundle
        with transaction.atomic():
            movement = move_student_bundle(student, from_group, to_group,
                preserve_secretary=preserve, move_mentor=move_mentor, replacement_secretary=replacement)
            if not preserve:
                self._set_formal_secretary_bindings(from_group.schedule_version, {student.pk}, student.bound_secretary_id)

        conflicts = self._check_conflicts(from_group.schedule_version)

        return Response({
            'status': 'ok',
            'message': f'学生 {student_id} 已从组 {from_group_id} 移动到组 {to_group_id}',
            'conflicts': conflicts,
            'movement': movement,
        })

    def _change_expert(self, request):
        group_id = request.data.get('group_id')
        old_expert_id = request.data.get('old_expert_id')
        new_expert_id = request.data.get('new_expert_id')

        if not all([group_id, old_expert_id, new_expert_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        old_expert = Teacher.objects.filter(id=old_expert_id).first()
        new_expert = Teacher.objects.filter(id=new_expert_id).first()
        missing_ids = [
            teacher_id
            for teacher_id, teacher in ((old_expert_id, old_expert), (new_expert_id, new_expert))
            if teacher is None
        ]
        if missing_ids:
            return Response({'error': f'教师不存在: {missing_ids}'}, status=400)
        if not group.experts.filter(id=old_expert.id).exists():
            return Response({'error': f'原专家不在当前组: {old_expert_id}'}, status=400)

        with transaction.atomic():
            group.experts.remove(old_expert)
            group.experts.add(new_expert)

        conflicts = self._check_conflicts(group.schedule_version)

        return Response({
            'status': 'ok',
            'message': '专家已更换',
            'conflicts': conflicts
        })

    def _change_chair(self, request):
        group_id = request.data.get('group_id')
        new_chair_id = request.data.get('new_chair_id')

        if not all([group_id, new_chair_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        chair = Teacher.objects.filter(id=new_chair_id).first()
        if not chair:
            return Response({'error': f'主席不存在: {new_chair_id}'}, status=400)

        group.chair = chair
        group.save()

        conflicts = self._check_conflicts(group.schedule_version)

        return Response({
            'status': 'ok',
            'message': '主席已更换',
            'conflicts': conflicts
        })

    def _change_secretary(self, request):
        group_id = request.data.get('group_id')
        new_secretary_id = request.data.get('new_secretary_id')

        if not all([group_id, new_secretary_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        secretary = Teacher.objects.filter(id=new_secretary_id).first()
        if not secretary:
            return Response({'error': f'秘书不存在: {new_secretary_id}'}, status=400)

        group.secretary = secretary
        group.save()
        self._set_formal_secretary_bindings(group.schedule_version,
            set(group.students.values_list('pk', flat=True)), secretary.pk)

        # 预答辩阶段手动更换秘书时同步学生绑定，保持"学生跟随同一秘书"
        if group.schedule_version.defense_type == 'pre':
            for student in group.students.all():
                if student.secretary_name != secretary.name:
                    student.secretary_name = secretary.name
                    student.save(update_fields=['secretary_name'])

        conflicts = self._check_conflicts(group.schedule_version)

        return Response({
            'status': 'ok',
            'message': '秘书已更换',
            'conflicts': conflicts
        })

    def _change_time(self, request):
        group_id = request.data.get('group_id')
        new_time = request.data.get('new_time')

        if not all([group_id, new_time]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            normalized_time = validate_schedule_time_text(new_time)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
            group.time = normalized_time
            group.save()

            conflicts = self._check_conflicts(group.schedule_version)

            return Response({
                'status': 'ok',
                'message': f'时间已修改为 {normalized_time}',
                'conflicts': conflicts
            })
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

    def _change_room(self, request):
        group_id = request.data.get('group_id')
        new_room_id = request.data.get('new_room_id')

        if not all([group_id, new_room_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        room = Room.objects.filter(id=new_room_id).first()
        if not room:
            return Response({'error': f'教室不存在: {new_room_id}'}, status=400)

        group.room = room
        group.save()

        conflicts = self._check_conflicts(group.schedule_version)

        return Response({
            'status': 'ok',
            'message': '教室已更换',
            'conflicts': conflicts
        })

    def _freeze_version(self, version):
        if version.result_snapshot:
            return
        version.conflicts_snapshot = self._check_conflicts(version)
        version.result_snapshot = self._version_result(version)
        version.export_snapshot = capture_export_groups(version)
        version.save(update_fields=['conflicts_snapshot', 'result_snapshot', 'export_snapshot'])

    @action(detail=False, methods=['get'])
    def versions(self, request):
        queryset = ScheduleVersion.objects.filter(defense_type=request.query_params.get('defense_type', 'pre'))
        if not is_admin_user(request.user):
            queryset = queryset.filter(status='published')
        return Response(list(queryset.values('id', 'version', 'status', 'is_current', 'created_at', 'published_at', 'revision')[:100]))

    @action(detail=False, methods=['post'])
    @schedule_write
    def publish(self, request):
        try:
            version = ScheduleVersion.objects.get(pk=request.data.get('version_id'), is_current=True)
        except (ScheduleVersion.DoesNotExist, ValueError, TypeError):
            return Response({'error': '当前草稿不存在，请刷新'}, status=404)
        if str(request.data.get('expected_revision')) != str(version.revision):
            return Response({'error': '排期已发生变化，请刷新后重新发布'}, status=409)
        if version.status == 'published':
            return Response(self._version_result(version))
        conflicts = self._format_conflicts(version, self._check_conflicts(version))
        if any(c['level'] == 'error' for c in conflicts):
            return Response({'error': '仍存在必须处理的冲突，不能发布', 'conflicts': conflicts}, status=400)
        if not version.groups.exists():
            return Response({'error': '空排期不能发布'}, status=400)
        version.status = 'published'
        version.published_at = timezone.now()
        version.revision += 1
        version.save(update_fields=['status', 'published_at', 'revision'])
        self._freeze_version(version)
        audit(request, '发布', f'发布 {version.defense_type} v{version.version}', version_id=version.id)
        return Response(self._version_result(version))
