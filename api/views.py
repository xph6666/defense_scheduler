import io
import json
from collections import defaultdict

import pandas as pd
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ViewSet

from .models import Group, OperationLog, Room, RuleConfig, ScheduleVersion, Student, Teacher
from .serializers import (
    DEFENSE_TYPE_LABELS,
    DEFENSE_TYPE_VALUES,
    OperationLogSerializer,
    RoomSerializer,
    RuleConfigSerializer,
    ScheduleVersionSerializer,
    StudentSerializer,
    TeacherSerializer,
    default_rule_config,
)


class ImportMixin:
    @action(detail=False, methods=['post'])
    def import_data(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': '未提供文件'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            elif file.name.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file)
            else:
                return Response({'error': '不支持的文件格式'}, status=status.HTTP_400_BAD_REQUEST)

            df.columns = [c.strip() for c in df.columns]
            df = df.where(pd.notnull(df), None)
            data_list = df.to_dict(orient='records')

            success_count = 0
            errors = []

            for index, row in enumerate(data_list):
                try:
                    processed_row = {}
                    for k, v in row.items():
                        processed_row[k] = v
                        snake_k = ''.join(['_' + i.lower() if i.isupper() else i for i in k]).lstrip('_')
                        if snake_k not in processed_row:
                            processed_row[snake_k] = v

                    json_fields = ['roles', 'available_types', 'availableTypes', 'defense_types', 'defenseTypes']
                    for field in json_fields:
                        if field in processed_row and isinstance(processed_row[field], str):
                            val = processed_row[field].strip()
                            if not val:
                                processed_row[field] = []
                            elif (val.startswith('[') and val.endswith(']')) or (val.startswith('{') and val.endswith('}')):
                                try:
                                    processed_row[field] = json.loads(val.replace("'", '"'))
                                except json.JSONDecodeError:
                                    processed_row[field] = [item.strip() for item in val.split(',') if item.strip()]
                            else:
                                processed_row[field] = [item.strip() for item in val.split(',') if item.strip()]

                    bool_fields = ['isExternal', 'is_external']
                    for field in bool_fields:
                        if field in processed_row and isinstance(processed_row[field], str):
                            processed_row[field] = processed_row[field].lower() in ['true', '1', '是', 'yes']

                    serializer = self.get_serializer(data=processed_row)
                    if serializer.is_valid():
                        serializer.save()
                        success_count += 1
                    else:
                        errors.append(f"行 {index + 2}: {serializer.errors}")
                except Exception as exc:
                    errors.append(f"行 {index + 2}: {str(exc)}")

            if success_count == 0 and errors:
                return Response({
                    'message': '导入失败，请检查文件格式。',
                    'errors': errors[:5]
                }, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                'message': f'成功导入 {success_count} 条数据',
                'errors': errors
            }, status=status.HTTP_200_OK)

        except Exception as exc:
            return Response({'error': f'解析文件失败: {str(exc)}'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def batch_delete(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': '未提供待删除的 ID 列表'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            queryset = self.get_queryset().filter(id__in=ids)
            count = queryset.count()
            queryset.delete()
            return Response({'message': f'成功删除 {count} 条数据'}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({'error': f'删除失败: {str(exc)}'}, status=status.HTTP_400_BAD_REQUEST)


class TeacherViewSet(ImportMixin, ModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer


class StudentViewSet(ImportMixin, ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer


class RoomViewSet(ImportMixin, ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class RuleConfigViewSet(ViewSet):
    def list(self, request):
        defense_type = request.query_params.get('defense_type', 'pre')
        config = RuleConfig.objects.filter(defense_type=defense_type).first()
        if config:
            return Response(RuleConfigSerializer(config).data)
        data = default_rule_config(defense_type)
        data['updatedAt'] = timezone.now().isoformat()
        return Response(data)

    def create(self, request):
        serializer = RuleConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = serializer.save()
        return Response(RuleConfigSerializer(config).data)


class OperationLogViewSet(ModelViewSet):
    queryset = OperationLog.objects.all()
    serializer_class = OperationLogSerializer
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def destroy(self, request, *args, **kwargs):
        OperationLog.objects.all().delete()
        return Response({'message': '日志已清空'})

    def delete(self, request, *args, **kwargs):
        OperationLog.objects.all().delete()
        return Response({'message': '日志已清空'})


class ScheduleViewSet(GenericViewSet):
    queryset = ScheduleVersion.objects.all()
    serializer_class = ScheduleVersionSerializer

    @action(detail=False, methods=['post'])
    def generate(self, request):
        teachers = Teacher.objects.all().values()
        students = Student.objects.all().values()
        rooms = Room.objects.all().values()
        rules = request.data.get('rules') or default_rule_config('pre')
        rules['defense_type'] = rules.get('defense_type') or DEFENSE_TYPE_VALUES.get(rules.get('defenseType'), 'pre')

        input_data = {
            'teachers': list(teachers),
            'students': list(students),
            'rooms': list(rooms),
            'rules': rules,
        }

        try:
            from algorithm import generate_schedule
            result = generate_schedule(**input_data)
        except ImportError:
            result = self._mock_schedule_result(input_data)

        ScheduleVersion.objects.filter(defense_type=rules['defense_type']).update(is_current=False)
        version_num = ScheduleVersion.objects.filter(defense_type=rules['defense_type']).count() + 1
        schedule_version = ScheduleVersion.objects.create(
            version=version_num,
            defense_type=rules['defense_type'],
            rules_snapshot=rules,
            is_current=True,
        )

        for group_data in result.get('groups', []):
            group = Group.objects.create(
                schedule_version=schedule_version,
                group_id=group_data['group_id'],
                time=group_data['time'],
                room_id=group_data.get('room_id'),
                campus=group_data.get('campus', ''),
                chair_id=group_data.get('chair_id'),
                secretary_id=group_data.get('secretary_id'),
            )
            group.experts.set(group_data.get('expert_ids', []))
            group.students.set(group_data.get('student_ids', []))

        return Response(self._format_schedule(schedule_version))

    def _mock_schedule_result(self, input_data):
        return {
            'groups': [
                {
                    'group_id': 'G1',
                    'time': '2025-05-10 09:00-12:00',
                    'room_id': 1,
                    'campus': '创新港',
                    'chair_id': 1,
                    'expert_ids': [2, 3],
                    'secretary_id': 4,
                    'student_ids': [101, 102, 103],
                }
            ],
            'conflicts': [],
        }

    @action(detail=False, methods=['get'])
    def current(self, request):
        defense_type = request.query_params.get('defense_type', 'pre')
        schedule_version = self._get_current_schedule(defense_type)
        if not schedule_version:
            return Response({
                'defenseType': DEFENSE_TYPE_LABELS.get(defense_type, defense_type),
                'generatedAt': '',
                'groups': [],
                'message': '暂无排期结果',
            })
        return Response(self._format_schedule(schedule_version))

    @action(detail=False, methods=['post'], url_path='check-conflicts')
    def check_conflicts(self, request):
        defense_type = request.data.get('defense_type', 'pre')
        schedule_version = self._get_current_schedule(defense_type)
        if not schedule_version:
            return Response([])
        return Response(self._detect_conflicts(schedule_version))

    @action(detail=False, methods=['post'], url_path='adjust-group')
    def adjust_group(self, request):
        defense_type = request.data.get('defense_type', 'pre')
        group_id = request.data.get('group_id')
        group_data = request.data.get('group_data') or {}
        group = Group.objects.filter(id=group_id, schedule_version__defense_type=defense_type).first()
        if not group:
            return Response({'message': '未找到对应排期分组'}, status=status.HTTP_404_NOT_FOUND)

        self._update_group(group, group_data)
        group.refresh_from_db()
        return Response({
            'success': True,
            'message': '调整保存成功',
            'updatedGroup': self._format_group(group),
        })

    @action(detail=False, methods=['get'], url_path='export-excel')
    def export_excel(self, request):
        defense_label = request.query_params.get('defenseType', '预答辩')
        defense_type = DEFENSE_TYPE_VALUES.get(defense_label, request.query_params.get('defense_type', 'pre'))
        schedule_version = self._get_current_schedule(defense_type)
        if not schedule_version:
            return Response({'message': '暂无排期结果'}, status=status.HTTP_404_NOT_FOUND)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = '排期结果'
        sheet.append(['组名', '答辩类型', '日期', '时间段', '校区', '教室', '主席/组长', '秘书', '专家', '学生'])
        for group in schedule_version.groups.select_related('room', 'chair', 'secretary').prefetch_related('experts', 'students'):
            formatted = self._format_group(group)
            sheet.append([
                formatted['groupName'],
                formatted['defenseType'],
                formatted['date'],
                formatted['timeRange'],
                formatted['campus'],
                formatted['classroom'],
                formatted.get('chairman') or formatted.get('leader') or '',
                formatted['secretary'],
                '、'.join(teacher['name'] for teacher in formatted['teachers']),
                '、'.join(student['name'] for student in formatted['students']),
            ])

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        filename = f"schedule-{defense_type}.xlsx"
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _get_current_schedule(self, defense_type):
        return ScheduleVersion.objects.filter(defense_type=defense_type, is_current=True).first()

    def _format_schedule(self, schedule_version):
        return {
            'defenseType': schedule_version.get_defense_type_display(),
            'generatedAt': schedule_version.created_at.isoformat(),
            'groups': [self._format_group(group) for group in schedule_version.groups.all()],
        }

    def _format_group(self, group):
        time_parts = group.time.split(' ', 1)
        date = time_parts[0] if time_parts else ''
        time_range = time_parts[1] if len(time_parts) > 1 else ''
        defense_type = group.schedule_version.get_defense_type_display()
        leader_key = 'chairman' if group.schedule_version.defense_type == 'formal' else 'leader'
        leader_value = group.chair.name if group.chair else None
        return {
            'id': group.id,
            'defenseType': defense_type,
            'groupName': group.group_id,
            'campus': group.campus,
            'classroom': group.room.name if group.room else '未分配',
            'date': date,
            'timeRange': time_range,
            leader_key: leader_value,
            'secretary': group.secretary.name if group.secretary else '未分配',
            'teachers': [
                {
                    'id': teacher.id,
                    'name': teacher.name,
                    'title': teacher.title,
                    'roles': teacher.roles,
                    'college': teacher.college,
                    'isExternal': teacher.is_external,
                }
                for teacher in group.experts.all()
            ],
            'students': [
                {
                    'id': student.id,
                    'name': student.name,
                    'studentType': student.student_type,
                    'mentorName': student.mentor_name,
                    'secretaryName': student.secretary_name,
                }
                for student in group.students.all()
            ],
            'remark': '',
        }

    def _update_group(self, group, group_data):
        group.group_id = group_data.get('groupName', group.group_id)
        date = group_data.get('date')
        time_range = group_data.get('timeRange')
        if date and time_range:
            group.time = f'{date} {time_range}'
        group.campus = group_data.get('campus', group.campus)
        classroom = group_data.get('classroom')
        if classroom:
            group.room = Room.objects.filter(name=classroom, campus=group.campus).first()

        chair_name = group_data.get('chairman') or group_data.get('leader')
        if chair_name:
            group.chair = Teacher.objects.filter(name=chair_name).first()
        secretary_name = group_data.get('secretary')
        if secretary_name:
            group.secretary = Teacher.objects.filter(name=secretary_name).first()
        group.save()

        expert_ids = [item['id'] for item in group_data.get('teachers', []) if item.get('id')]
        student_ids = [item['id'] for item in group_data.get('students', []) if item.get('id')]
        group.experts.set(expert_ids)
        group.students.set(student_ids)

    def _detect_conflicts(self, schedule_version):
        conflicts = []
        now = timezone.now().isoformat()
        groups = list(schedule_version.groups.select_related('room', 'chair', 'secretary').prefetch_related('experts', 'students'))
        config = RuleConfig.objects.filter(defense_type=schedule_version.defense_type).first()
        rules = (config.config if config else default_rule_config(schedule_version.defense_type)) or {}
        student_rule = rules.get('studentCount', {})
        min_students = student_rule.get('min', 0)
        max_students = student_rule.get('max', 9999)

        def add_conflict(group, conflict_type, level, target, reason, suggestion='', related_group_ids=None):
            conflicts.append({
                'id': len(conflicts) + 1,
                'defenseType': schedule_version.get_defense_type_display(),
                'groupId': group.id if group else None,
                'groupName': group.group_id if group else None,
                'type': conflict_type,
                'level': level,
                'target': target,
                'reason': reason,
                'suggestion': suggestion,
                'relatedGroupIds': related_group_ids or [],
                'createdAt': now,
            })

        teacher_time_map = defaultdict(list)
        room_time_map = defaultdict(list)
        student_time_map = defaultdict(list)

        for group in groups:
            teachers = [teacher for teacher in [group.chair, group.secretary] if teacher] + list(group.experts.all())
            students = list(group.students.all())
            for teacher in teachers:
                teacher_time_map[(teacher.id, group.time)].append(group)
            for student in students:
                student_time_map[(student.id, group.time)].append(group)
            if group.room:
                room_time_map[(group.room.id, group.time)].append(group)

            teacher_names = {teacher.name for teacher in teachers}
            for student in students:
                if student.mentor_name and student.mentor_name in teacher_names:
                    add_conflict(
                        group,
                        '导师回避冲突',
                        'error',
                        student.name,
                        f'学生导师 {student.mentor_name} 出现在同组教师中',
                        '请将该学生或导师调整到其他分组',
                    )

            for teacher in teachers:
                avoid_names = [name.strip() for name in teacher.avoid_teacher_names.replace('，', ',').split(',') if name.strip()]
                matched_names = [name for name in avoid_names if name in teacher_names]
                if matched_names:
                    add_conflict(
                        group,
                        '不宜同组冲突',
                        'warning',
                        teacher.name,
                        f'{teacher.name} 与 {"、".join(matched_names)} 不宜同组',
                        '请调整专家组成员',
                    )

                if teacher.campus_preference and teacher.campus_preference != group.campus:
                    add_conflict(
                        group,
                        '校区切换提示',
                        'info',
                        teacher.name,
                        f'{teacher.name} 偏好 {teacher.campus_preference}，当前安排在 {group.campus}',
                        '如需降低跨校区成本，可调整教室或教师',
                    )

            if len(students) < min_students or len(students) > max_students:
                add_conflict(
                    group,
                    '人数规则提示',
                    'warning',
                    group.group_id,
                    f'当前 {len(students)} 人，不满足 {min_students}-{max_students} 人规则',
                    '请调整学生数量',
                )

        for (_, _), conflict_groups in teacher_time_map.items():
            if len(conflict_groups) > 1:
                first_group = conflict_groups[0]
                add_conflict(
                    first_group,
                    '时间冲突',
                    'error',
                    first_group.time,
                    '同一教师在同一时间段被安排到多个分组',
                    '请调整教师或时间段',
                    [group.id for group in conflict_groups],
                )

        for (_, _), conflict_groups in room_time_map.items():
            if len(conflict_groups) > 1:
                first_group = conflict_groups[0]
                add_conflict(
                    first_group,
                    '教室冲突',
                    'error',
                    first_group.room.name if first_group.room else '未分配',
                    '同一教室在同一时间段被多个分组使用',
                    '请调整教室或时间段',
                    [group.id for group in conflict_groups],
                )

        for (_, _), conflict_groups in student_time_map.items():
            if len(conflict_groups) > 1:
                first_group = conflict_groups[0]
                add_conflict(
                    first_group,
                    '人员冲突',
                    'error',
                    first_group.time,
                    '同一学生在同一时间段出现在多个分组',
                    '请移除重复学生',
                    [group.id for group in conflict_groups],
                )

        return conflicts
