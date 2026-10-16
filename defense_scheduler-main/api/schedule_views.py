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

    read_actions = {'current', 'export', 'export_excel', 'export_word', 'check_conflicts', 'versions'}

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
        'time_conflict': ('时间冲突', 'error'),
        'teacher_time_conflict': ('时间冲突', 'error'),
        'room_conflict': ('教室冲突', 'error'),
        'room_or_time_unavailable': ('教室冲突', 'error'),
        'insufficient_experts': ('人员冲突', 'error'),
        'chair_unavailable': ('人员冲突', 'error'),
        'secretary_unavailable': ('人员冲突', 'error'),
        'supervisor_avoidance': ('导师回避冲突', 'error'),
        'supervisor_missing': ('导师未与学生同组', 'error'),
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
        'external_mentor_concentration': ('外院教师集中安排提示', 'warning'),
        'software_participation_imbalance': ('软件学院评审次数均衡提示', 'warning'),
    }

    RULE_KEY_ALIASES = {
        'mentor_avoidance': 'avoid_supervisor',
    }

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

            formatted.append({
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
            })
        return formatted

    @action(detail=False, methods=['post'])
    @schedule_write
    def generate(self, request):
        rules = self._normalize_rules(request.data.get('rules', {}))
        request_key = request.data.get('request_key')
        if request_key and (not isinstance(request_key, str) or len(request_key) > 64):
            return Response({'error': '请求标识格式不正确'}, status=400)
        if request_key:
            previous = ScheduleVersion.objects.filter(request_key=request_key).first()
            if previous:
                if previous.rules_snapshot != rules:
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
        pre_rules = self._normalize_rules({**pre_raw, 'defense_type': 'pre', 'policy_version': 2})
        pre_rules.update(reserve_formal_resources=True, refresh_secretary_bindings=True)
        formal_rules = self._normalize_rules({**formal_raw, 'defense_type': 'formal', 'policy_version': 2,
            'preserve_pre_defense_groups': True, 'formal_mentor_same_session': True})
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
                if not all(previous) or any(v.rules_snapshot != r for v, r in zip(previous, (pre_rules, formal_rules))):
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

    def _version_result(self, schedule_version):
        if schedule_version.result_snapshot:
            return {**schedule_version.result_snapshot, 'status': schedule_version.status, 'revision': schedule_version.revision, 'isCurrent': schedule_version.is_current}
        groups = export_groups(schedule_version)
        formatted_groups = []
        for group in groups:
            time_parts = group.time.split(' ')
            date = time_parts[0] if len(time_parts) > 0 else ''
            time_range = time_parts[1] if len(time_parts) > 1 else ''

            formatted_groups.append({
                'id': group.id,
                'defenseType': schedule_version.get_defense_type_display(),
                'groupName': group.group_id,
                'campus': group.campus,
                'classroom': group.room.name if group.room else '未分配',
                'date': date,
                'timeRange': time_range,
                'chairman': group.chair.name if group.chair else None,
                'secretary': group.secretary.name if group.secretary else '未分配',
                'chairTitle': group.chair.title if group.chair else '',
                'chairId': group.chair_id,
                'secretaryId': group.secretary_id,
                'teachers': [
                    {'id': t.id, 'name': t.name, 'title': t.title, 'roles': getattr(t, 'roles', []), 'isExternal': t.is_external}
                    for t in group.experts.all()
                ],
                'students': [
                    {
                        'id': s.id,
                        'name': s.name,
                        'studentType': s.student_type,
                        'mentorName': s.mentor.name if getattr(s, 'mentor_id', None) and hasattr(s, 'mentor') else s.mentor_name,
                        'mentorId': getattr(s, 'mentor_id', None),
                        'secretaryId': getattr(s, 'bound_secretary_id', None),
                        'secretaryName': s.bound_secretary.name if getattr(s, 'bound_secretary_id', None) and hasattr(s, 'bound_secretary') else s.secretary_name,
                        'studentNo': s.student_no,
                        'remark': s.remark,
                    }
                    for s in group.students.all()
                ]
            })

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
            'groups': formatted_groups,
            'conflicts': self._format_conflicts(schedule_version, self._check_conflicts(schedule_version))
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

    @action(detail=False, methods=['get'], url_path='export_word')
    def export_word(self, request):
        """导出当前排期为 Word 时间安排表（版式对齐学院归档样例，导师与学生同色）"""
        defense_type = request.query_params.get('defense_type', 'pre')
        schedule_version = self._selected_version(request, defense_type)

        if not schedule_version:
            return Response({'error': '暂无排期结果可导出'}, status=404)

        from urllib.parse import quote

        from .export_word import export_schedule_word

        defense_label = DEFENSE_TYPE_LABELS.get(defense_type, defense_type)
        doc = export_schedule_word(schedule_version, defense_label)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        ascii_name = f'defense_schedule_{defense_type}.docx'
        utf8_name = quote(f'{defense_label}时间安排.docx')
        response['Content-Disposition'] = (
            f"attachment; filename={ascii_name}; filename*=UTF-8''{utf8_name}"
        )
        doc.save(response)
        return response

    @action(detail=False, methods=['get'])
    def export(self, request):
        from .services.export_excel import build_schedule_workbook
        defense_type = request.query_params.get('defense_type', 'pre')
        version = self._selected_version(request, defense_type)
        if not version:
            return Response({'error': '暂无排期结果可导出'}, status=404)
        conflicts = self._format_conflicts(version, self._check_conflicts(version))
        workbook = build_schedule_workbook(version, defense_type, conflicts)
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename=defense_schedule_{defense_type}.xlsx'
        workbook.save(response)
        return response

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
