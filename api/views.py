from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from .models import Teacher, Student, Room, ScheduleVersion, Group
from .serializers import TeacherSerializer, StudentSerializer, RoomSerializer, ScheduleVersionSerializer


# 原有的 ViewSet
class TeacherViewSet(ModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer


class StudentViewSet(ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer


class RoomViewSet(ModelViewSet):
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

        # 7. 返回结果
        return Response({
            'schedule_version_id': schedule_version.id,
            'groups': result.get('groups', []),
            'conflicts': result.get('conflicts', [])
        }, status=status.HTTP_201_CREATED)

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
            return Response({'groups': [], 'message': '暂无排期结果'})

        groups = schedule_version.groups.all()
        result = []
        for group in groups:
            result.append({
                'group_id': group.group_id,
                'time': group.time,
                'room': group.room.name if group.room else None,
                'campus': group.campus,
                'chair': group.chair.name if group.chair else None,
                'experts': [t.name for t in group.experts.all()],
                'secretary': group.secretary.name if group.secretary else None,
                'students': [s.name for s in group.students.all()]
            })

        return Response({'groups': result})
