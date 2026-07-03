from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.db import transaction
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from django.http import HttpResponse
import pandas as pd
import json
from .models import Group, OperationLog, Room, RuleConfig, ScheduleVersion, Student, Teacher
from .serializers import (
    OperationLogSerializer,
    RuleConfigSerializer,
    RoomSerializer,
    ScheduleVersionSerializer,
    StudentSerializer,
    TeacherSerializer,
    default_rule_config,
)


MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024


def split_time_text(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    normalized = str(value).replace('，', ',').replace(';', ',').replace('；', ',').replace('\n', ',')
    return [item.strip() for item in normalized.split(',') if item.strip()]


class AuthLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get('username', '')
        password = request.data.get('password', '')
        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({'error': '账号或密码错误'}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'username': user.get_username()})


class ImportMixin:
    @action(detail=False, methods=['post'])
    def import_data(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': '未提供文件'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response({'error': '文件大小不能超过 5MB'}, status=status.HTTP_400_BAD_REQUEST)
        
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
                                except:
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
                except Exception as e:
                    errors.append(f"行 {index + 2}: {str(e)}")
            
            if success_count == 0 and errors:
                return Response({
                    'message': f'导入失败，请检查文件格式。',
                    'errors': errors[:5]
                }, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                'message': f'成功导入 {success_count} 条数据',
                'errors': errors
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({'error': f'解析文件失败: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

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
        except Exception as e:
            return Response({'error': f'删除失败: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


class TeacherViewSet(ImportMixin, ModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer


class StudentViewSet(ImportMixin, ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer


class RoomViewSet(ImportMixin, ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class RuleConfigViewSet(ModelViewSet):
    queryset = RuleConfig.objects.all()
    serializer_class = RuleConfigSerializer

    def list(self, request, *args, **kwargs):
        defense_type = request.query_params.get('defense_type', 'pre')
        rule_config = RuleConfig.objects.filter(defense_type=defense_type).first()
        if not rule_config:
            return Response(default_rule_config(defense_type))
        return Response(self.get_serializer(rule_config).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)


class OperationLogViewSet(ModelViewSet):
    queryset = OperationLog.objects.all()
    serializer_class = OperationLogSerializer

    def clear(self, request):
        OperationLog.objects.all().delete()
        return Response({'message': '日志已清空'}, status=status.HTTP_200_OK)


class ScheduleViewSet(GenericViewSet):
    queryset = ScheduleVersion.objects.all()
    serializer_class = ScheduleVersionSerializer

    # 算法/检测产生的英文冲突类型 → 前端 ScheduleConflict 的中文类型与级别
    CONFLICT_TYPE_LABELS = {
        'time_conflict': ('时间冲突', 'error'),
        'teacher_time_conflict': ('时间冲突', 'error'),
        'room_conflict': ('教室冲突', 'error'),
        'room_or_time_unavailable': ('教室冲突', 'error'),
        'insufficient_experts': ('人员冲突', 'error'),
        'chair_unavailable': ('人员冲突', 'error'),
        'secretary_unavailable': ('人员冲突', 'error'),
        'supervisor_avoidance': ('导师回避冲突', 'error'),
        'secretary_student_conflict': ('秘书学生冲突', 'error'),
        'campus_mismatch': ('校区切换提示', 'warning'),
    }

    # 历史/前端旧版规则键 → 算法使用的规则键
    RULE_KEY_ALIASES = {
        'mentor_avoidance': 'avoid_supervisor',
    }

    def _normalize_rules(self, rules):
        """统一规则键：兼容旧键名别名，并补齐 defense_type 缺省值"""
        normalized = dict(rules or {})
        for alias, canonical in self.RULE_KEY_ALIASES.items():
            if alias in normalized and canonical not in normalized:
                normalized[canonical] = normalized[alias]
        normalized.setdefault('defense_type', 'pre')
        return normalized

    def _format_conflicts(self, schedule_version, raw_conflicts):
        """把英文冲突结构转换为前端 ScheduleConflict 形状（中文类型 + level/target/reason）"""
        group_name_map = {g.id: g.group_id for g in schedule_version.groups.all()}
        defense_label = schedule_version.get_defense_type_display()
        created_at = schedule_version.created_at.isoformat()

        formatted = []
        for index, item in enumerate(raw_conflicts or [], start=1):
            raw_type = item.get('type', '')
            label, level = self.CONFLICT_TYPE_LABELS.get(raw_type, (raw_type or '未知冲突', 'warning'))

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

    def _build_algorithm_input(self):
        teachers = list(Teacher.objects.all())
        students = list(Student.objects.all())
        rooms = list(Room.objects.all())
        teacher_by_name = {teacher.name: teacher for teacher in teachers}

        teacher_payload = []
        for teacher in teachers:
            forbidden_with = [
                teacher_by_name[name].id
                for name in [item.strip() for item in teacher.avoid_teacher_names.replace('，', ',').split(',') if item.strip()]
                if name in teacher_by_name
            ]
            teacher_payload.append({
                'id': teacher.id,
                'name': teacher.name,
                'college': teacher.college,
                'is_external': teacher.is_external,
                'title': teacher.title,
                'available_time': split_time_text(teacher.unavailable_times),
                'campus_preference': teacher.campus_preference,
                'forbidden_with': forbidden_with,
            })

        student_payload = []
        for student in students:
            mentor = teacher_by_name.get(student.mentor_name)
            secretary = teacher_by_name.get(student.secretary_name)
            student_payload.append({
                'id': student.id,
                'name': student.name,
                'type': student.student_type,
                'supervisor_id': mentor.id if mentor else None,
                'campus': student.campus,
                'secretary_id': secretary.id if secretary else None,
            })

        room_payload = [
            {
                'id': room.id,
                'campus': room.campus,
                'name': room.name,
                'available_time': split_time_text(room.available_times),
            }
            for room in rooms
        ]

        return {
            'teachers': teacher_payload,
            'students': student_payload,
            'rooms': room_payload,
        }

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """一键生成排期"""
        rules = self._normalize_rules(request.data.get('rules', {
            'defense_type': 'pre',
            'start_date': '2025-05-10',
            'avoid_weekend': True,
            'avoid_holiday': True,
        }))

        input_data = {**self._build_algorithm_input(), 'rules': rules}

        try:
            from algorithm import SchedulingError, generate_schedule
            result = generate_schedule(**input_data)
        except ImportError as exc:
            return Response({'error': f'排期算法加载失败: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except SchedulingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError) as exc:
            return Response({'error': f'排期参数错误: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            ScheduleVersion.objects.filter(defense_type=rules['defense_type']).update(is_current=False)

            version_num = ScheduleVersion.objects.filter(defense_type=rules['defense_type']).count() + 1
            schedule_version = ScheduleVersion.objects.create(
                version=version_num,
                defense_type=rules['defense_type'],
                rules_snapshot=rules,
                is_current=True
            )

            # 算法冲突里的组编号是 "G1" 这类字符串，入库后补上数据库组 ID 便于前端定位
            group_db_map = {}
            for group_data in result.get('groups', []):
                group = Group.objects.create(
                    schedule_version=schedule_version,
                    group_id=group_data['group_id'],
                    time=group_data.get('time') or '',
                    room_id=group_data.get('room_id'),
                    campus=group_data.get('campus') or '',
                    chair_id=group_data.get('chair_id'),
                    secretary_id=group_data.get('secretary_id')
                )
                group_db_map[group_data['group_id']] = group.id
                group.experts.add(*group_data.get('expert_ids', []))
                group.students.add(*group_data.get('student_ids', []))

            conflicts_snapshot = []
            for item in result.get('conflicts', []):
                enriched = dict(item)
                enriched['group_db_ids'] = [
                    group_db_map[related]
                    for related in item.get('related_ids', [])
                    if isinstance(related, str) and related in group_db_map
                ]
                conflicts_snapshot.append(enriched)

            schedule_version.conflicts_snapshot = conflicts_snapshot
            schedule_version.save(update_fields=['conflicts_snapshot'])

        request.query_params._mutable = True
        request.query_params['defense_type'] = rules['defense_type']
        return self.current(request)

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
                    'student_ids': [101, 102, 103]
                }
            ],
            'conflicts': []
        }

    @action(detail=False, methods=['get'])
    def current(self, request):
        """获取当前生效的排期"""
        defense_type = request.query_params.get('defense_type', 'pre')
        schedule_version = ScheduleVersion.objects.filter(
            defense_type=defense_type,
            is_current=True
        ).first()

        if not schedule_version:
            return Response({
                'defenseType': defense_type,
                'generatedAt': '',
                'groups': [],
                'conflicts': [],
                'message': '暂无排期结果'
            })

        groups = schedule_version.groups.all()
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
                'teachers': [
                    {'id': t.id, 'name': t.name, 'title': t.title, 'roles': getattr(t, 'roles', [])}
                    for t in group.experts.all()
                ],
                'students': [
                    {
                        'id': s.id, 
                        'name': s.name, 
                        'studentType': s.student_type,
                        'mentorName': s.mentor_name
                    }
                    for s in group.students.all()
                ]
            })

        return Response({
            'defenseType': schedule_version.get_defense_type_display(),
            'generatedAt': schedule_version.created_at.strftime('%Y-%m-%d %H:%M'),
            'groups': formatted_groups,
            'conflicts': self._format_conflicts(schedule_version, schedule_version.conflicts_snapshot)
        })

    @action(detail=False, methods=['post'], url_path='adjust-group')
    def adjust_group(self, request):
        """保存前端完整分组编辑表单。"""
        group_id = request.data.get('group_id')
        group_data = request.data.get('group_data') or {}
        if not group_id or not group_data:
            return Response({'error': '缺少必要参数'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=status.HTTP_404_NOT_FOUND)

        next_group_id = group_data.get('groupName') or group.group_id
        date = group_data.get('date')
        time_range = group_data.get('timeRange')
        next_time = group.time
        if date and time_range:
            next_time = f'{date} {time_range}'
        next_campus = group_data.get('campus') or group.campus

        room = None
        room_name = group_data.get('classroom')
        if room_name:
            room = Room.objects.filter(name=room_name, campus=next_campus).first() or Room.objects.filter(name=room_name).first()
            if not room:
                return Response({'error': f'教室不存在: {room_name}'}, status=status.HTTP_400_BAD_REQUEST)

        chair = None
        chair_name = group_data.get('chairman') or group_data.get('leader')
        if chair_name:
            chair = Teacher.objects.filter(name=chair_name).first()
            if not chair:
                return Response({'error': f'主席/组长不存在: {chair_name}'}, status=status.HTTP_400_BAD_REQUEST)

        secretary = None
        secretary_name = group_data.get('secretary')
        if secretary_name:
            secretary = Teacher.objects.filter(name=secretary_name).first()
            if not secretary:
                return Response({'error': f'秘书不存在: {secretary_name}'}, status=status.HTTP_400_BAD_REQUEST)

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

        return Response({
            'success': True,
            'message': '调整保存成功',
            'updatedGroup': group_data,
            'conflicts': self._check_conflicts(group.schedule_version),
        })

    @action(detail=False, methods=['post'])
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

    @action(detail=False, methods=['get'])
    def export(self, request):
        """导出当前排期为 Excel 文件"""
        defense_type = request.query_params.get('defense_type', 'pre')
        schedule_version = ScheduleVersion.objects.filter(
            defense_type=defense_type,
            is_current=True
        ).first()

        if not schedule_version:
            return Response({'error': '暂无排期结果可导出'}, status=404)

        wb = Workbook()
        default_sheet = wb.active
        wb.remove(default_sheet)

        groups = schedule_version.groups.all()

        colors = [
            'FFB3B3', 'B3FFB3', 'B3B3FF', 'FFFFB3', 'FFB3FF', 'B3FFFF',
        ]

        supervisor_color_map = {}
        color_index = 0

        for group in groups:
            sheet = wb.create_sheet(title=f"组{group.group_id}")

            sheet.column_dimensions['A'].width = 15
            sheet.column_dimensions['B'].width = 20
            sheet.column_dimensions['C'].width = 15
            sheet.column_dimensions['D'].width = 25

            title_font = Font(bold=True, size=14)
            title_cell = sheet['A1']
            title_cell.value = f"答辩排期表 - {group.group_id}"
            title_cell.font = title_font
            sheet.merge_cells('A1:D1')

            row = 3
            info_data = [
                ('时间', group.time),
                ('教室', group.room.name if group.room else '未分配'),
                ('校区', group.campus),
                ('主席/组长', group.chair.name if group.chair else '未分配'),
                ('秘书', group.secretary.name if group.secretary else '未分配'),
            ]

            for label, value in info_data:
                sheet[f'A{row}'] = label
                sheet[f'B{row}'] = value
                sheet[f'A{row}'].font = Font(bold=True)
                row += 1

            sheet[f'A{row}'] = '专家'
            sheet[f'A{row}'].font = Font(bold=True)
            expert_names = [e.name for e in group.experts.all()]
            sheet[f'B{row}'] = '、'.join(expert_names) if expert_names else '未分配'
            row += 2

            headers = ['学生姓名', '学生类型', '导师姓名', '导师职称']
            for col, header in enumerate(headers, 1):
                cell = sheet.cell(row=row, column=col, value=header)
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')

            row += 1

            for student in group.students.all():
                mentor_key = student.mentor_name or f"student-{student.id}"
                if mentor_key not in supervisor_color_map:
                    supervisor_color_map[mentor_key] = colors[color_index % len(colors)]
                    color_index += 1

                color = supervisor_color_map[mentor_key]
                fill = PatternFill(start_color=color, end_color=color, fill_type='solid')

                cell = sheet.cell(row=row, column=1, value=student.name)
                cell.fill = fill

                cell = sheet.cell(row=row, column=2, value=student.student_type)
                cell.fill = fill

                supervisor_name = student.mentor_name or '未分配'
                cell = sheet.cell(row=row, column=3, value=supervisor_name)
                cell.fill = fill

                supervisor_title = Teacher.objects.filter(name=student.mentor_name).values_list('title', flat=True).first() or ''
                cell = sheet.cell(row=row, column=4, value=supervisor_title)
                cell.fill = fill

                row += 1

            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )

            for r in range(3, row):
                for c in range(1, 5):
                    cell = sheet.cell(row=r, column=c)
                    cell.border = thin_border
                    cell.alignment = Alignment(horizontal='center', vertical='center')

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=defense_schedule_{defense_type}.xlsx'

        wb.save(response)
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
        schedule_version = ScheduleVersion.objects.filter(
            defense_type=defense_type,
            is_current=True
        ).first()

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
            from_group = Group.objects.get(id=from_group_id)
            to_group = Group.objects.get(id=to_group_id)

            from_group.students.remove(student_id)
            to_group.students.add(student_id)

            conflicts = self._check_conflicts(from_group.schedule_version)

            return Response({
                'status': 'ok',
                'message': f'学生 {student_id} 已从组 {from_group_id} 移动到组 {to_group_id}',
                'conflicts': conflicts
            })
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    def _change_expert(self, request):
        group_id = request.data.get('group_id')
        old_expert_id = request.data.get('old_expert_id')
        new_expert_id = request.data.get('new_expert_id')

        if not all([group_id, old_expert_id, new_expert_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.get(id=group_id)
            group.experts.remove(old_expert_id)
            group.experts.add(new_expert_id)

            conflicts = self._check_conflicts(group.schedule_version)

            return Response({
                'status': 'ok',
                'message': '专家已更换',
                'conflicts': conflicts
            })
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

    def _change_chair(self, request):
        group_id = request.data.get('group_id')
        new_chair_id = request.data.get('new_chair_id')

        if not all([group_id, new_chair_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.get(id=group_id)
            group.chair_id = new_chair_id
            group.save()

            conflicts = self._check_conflicts(group.schedule_version)

            return Response({
                'status': 'ok',
                'message': '主席已更换',
                'conflicts': conflicts
            })
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

    def _change_secretary(self, request):
        group_id = request.data.get('group_id')
        new_secretary_id = request.data.get('new_secretary_id')

        if not all([group_id, new_secretary_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.get(id=group_id)
            group.secretary_id = new_secretary_id
            group.save()

            conflicts = self._check_conflicts(group.schedule_version)

            return Response({
                'status': 'ok',
                'message': '秘书已更换',
                'conflicts': conflicts
            })
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

    def _change_time(self, request):
        group_id = request.data.get('group_id')
        new_time = request.data.get('new_time')

        if not all([group_id, new_time]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.get(id=group_id)
            group.time = new_time
            group.save()

            conflicts = self._check_conflicts(group.schedule_version)

            return Response({
                'status': 'ok',
                'message': f'时间已修改为 {new_time}',
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
            group = Group.objects.get(id=group_id)
            group.room_id = new_room_id
            group.save()

            conflicts = self._check_conflicts(group.schedule_version)

            return Response({
                'status': 'ok',
                'message': '教室已更换',
                'conflicts': conflicts
            })
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

    def _check_conflicts(self, schedule_version):
        conflicts = []
        groups = schedule_version.groups.all()

        teacher_time_map = {}

        for group in groups:
            if group.chair:
                key = (group.chair.id, group.time)
                if key in teacher_time_map:
                    conflicts.append({
                        'type': 'teacher_time_conflict',
                        'description': f"{group.chair.name} 在同一时间 {group.time} 被分配到多个组",
                        'teacher_id': group.chair.id,
                        'teacher_name': group.chair.name,
                        'time': group.time,
                        'group_ids': [teacher_time_map[key], group.id]
                    })
                else:
                    teacher_time_map[key] = group.id

            for expert in group.experts.all():
                key = (expert.id, group.time)
                if key in teacher_time_map:
                    conflicts.append({
                        'type': 'teacher_time_conflict',
                        'description': f"{expert.name} 在同一时间 {group.time} 被分配到多个组",
                        'teacher_id': expert.id,
                        'teacher_name': expert.name,
                        'time': group.time,
                        'group_ids': [teacher_time_map[key], group.id]
                    })
                else:
                    teacher_time_map[key] = group.id

            if group.secretary:
                key = (group.secretary.id, group.time)
                if key in teacher_time_map:
                    conflicts.append({
                        'type': 'teacher_time_conflict',
                        'description': f"{group.secretary.name} 在同一时间 {group.time} 被分配到多个组",
                        'teacher_id': group.secretary.id,
                        'teacher_name': group.secretary.name,
                        'time': group.time,
                        'group_ids': [teacher_time_map[key], group.id]
                    })
                else:
                    teacher_time_map[key] = group.id

        room_time_map = {}
        for group in groups:
            if group.room:
                key = (group.room.id, group.time)
                if key in room_time_map:
                    conflicts.append({
                        'type': 'room_conflict',
                        'description': f"{group.room.name} 在同一时间 {group.time} 被多个组使用",
                        'room_id': group.room.id,
                        'room_name': group.room.name,
                        'time': group.time,
                        'group_ids': [room_time_map[key], group.id]
                    })
                else:
                    room_time_map[key] = group.id

        for group in groups:
            if group.secretary:
                secretary_name = group.secretary.name
                for student in group.students.all():
                    if student.secretary_name and student.secretary_name == secretary_name:
                        conflicts.append({
                            'type': 'secretary_student_conflict',
                            'description': f"秘书 {group.secretary.name} 和自己的学生 {student.name} 在同一组",
                            'group_id': group.id,
                            'secretary_id': group.secretary.id,
                            'student_id': student.id
                        })

        return conflicts
