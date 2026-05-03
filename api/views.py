from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
import pandas as pd
import json
from .models import Teacher, Student, Room, ScheduleVersion, Group
from .serializers import TeacherSerializer, StudentSerializer, RoomSerializer, ScheduleVersionSerializer

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
            
            # 统一表头：去除空格，尝试匹配字段名
            df.columns = [c.strip() for c in df.columns]
            df = df.where(pd.notnull(df), None)
            data_list = df.to_dict(orient='records')
            
            success_count = 0
            errors = []
            
            for index, row in enumerate(data_list):
                try:
                    # 自动处理驼峰到下划线的映射，以兼容不同来源的 Excel
                    # 比如把 campusPreference 映射为 campus_preference，如果 serializer 没定义驼峰名
                    processed_row = {}
                    for k, v in row.items():
                        processed_row[k] = v
                        # 如果是驼峰，也存一份下划线版本
                        snake_k = ''.join(['_' + i.lower() if i.isupper() else i for i in k]).lstrip('_')
                        if snake_k not in processed_row:
                            processed_row[snake_k] = v

                    # 处理可能出现的 JSON 字符串或逗号分隔字符串
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
                    
                    # 针对 BooleanField 的特殊处理
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
                    'errors': errors[:5]  # 仅返回前5个错误避免过长
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

# 原有的 ViewSet
class TeacherViewSet(ImportMixin, ModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer


class StudentViewSet(ImportMixin, ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer


class RoomViewSet(ImportMixin, ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


# 新增的排期视图
class ScheduleViewSet(GenericViewSet):
    queryset = ScheduleVersion.objects.all()
    serializer_class = ScheduleVersionSerializer

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """一键生成排期"""
        # 1. 从数据库提取数据
        teachers = Teacher.objects.all().values()
        students = Student.objects.all().values()
        rooms = Room.objects.all().values()

        # 2. 获取规则参数
        rules = request.data.get('rules', {
            'defense_type': 'pre',
            'start_date': '2025-05-10',
            'avoid_weekend': True,
            'avoid_holiday': True,
        })

        # 3. 组装输入数据
        input_data = {
            'teachers': list(teachers),
            'students': list(students),
            'rooms': list(rooms),
            'rules': rules
        }

        # 4. 调用算法
        try:
            from algorithm import generate_schedule
            result = generate_schedule(**input_data)
        except ImportError:
            # 算法模块未就绪时使用内置模拟数据
            result = self._mock_schedule_result(input_data)

        # 5. 保存排期版本
        # 先将该类型的所有旧版本标记为非当前
        ScheduleVersion.objects.filter(defense_type=rules['defense_type']).update(is_current=False)
        
        version_num = ScheduleVersion.objects.filter(defense_type=rules['defense_type']).count() + 1
        schedule_version = ScheduleVersion.objects.create(
            version=version_num,
            defense_type=rules['defense_type'],
            rules_snapshot=rules,
            is_current=True
        )

        # 6. 保存分组数据
        for group_data in result.get('groups', []):
            group = Group.objects.create(
                schedule_version=schedule_version,
                group_id=group_data['group_id'],
                time=group_data['time'],
                room_id=group_data.get('room_id'),
                campus=group_data.get('campus', ''),
                chair_id=group_data.get('chair_id'),
                secretary_id=group_data.get('secretary_id')
            )
            # 处理多对多关系
            for expert_id in group_data.get('expert_ids', []):
                group.experts.through.objects.create(group_id=group.id, teacher_id=expert_id)
            for student_id in group_data.get('student_ids', []):
                group.students.through.objects.create(group_id=group.id, student_id=student_id)

        # 7. 返回结果 (复用 current 的逻辑返回完整对象)
        request.query_params._mutable = True
        request.query_params['defense_type'] = rules['defense_type']
        return self.current(request)

    def _mock_schedule_result(self, input_data):
        """模拟算法返回（算法未就绪时使用）"""
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
                'message': '暂无排期结果'
            })

        groups = schedule_version.groups.all()
        formatted_groups = []
        for group in groups:
            # 尝试拆分时间字段 "2025-05-10 09:00-12:00"
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
                    {'id': t.id, 'name': t.name, 'title': t.title, 'roles': t.roles}
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
            'groups': formatted_groups
        })

    @action(detail=False, methods=['post'], url_path='check-conflicts')
    def check_conflicts(self, request):
        """冲突检测"""
        # 目前返回空列表，后续集成算法逻辑
        return Response([])
