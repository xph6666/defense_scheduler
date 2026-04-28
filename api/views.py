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


# 排期视图
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

    def _move_student(self, request):
        """移动学生到另一个组"""
        student_id = request.data.get('student_id')
        from_group_id = request.data.get('from_group_id')
        to_group_id = request.data.get('to_group_id')

        if not all([student_id, from_group_id, to_group_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            from_group = Group.objects.get(id=from_group_id)
            to_group = Group.objects.get(id=to_group_id)

            # 从原组移除学生
            from_group.students.remove(student_id)
            # 添加到新组
            to_group.students.add(student_id)

            # 重新检测冲突
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
        """更换专家"""
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
        """更换主席/组长"""
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
        """更换秘书"""
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
        """修改组的时间"""
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
        """修改组使用的教室"""
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
        """检测一个排期版本的所有冲突"""
        conflicts = []
        groups = schedule_version.groups.all()

        # 1. 教师时间冲突：同一教师在同一时间出现在多个组
        teacher_time_map = {}

        for group in groups:
            # 检查主席
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

            # 检查专家
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

            # 检查秘书
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

        # 2. 教室冲突：同一教室同一时间多个组
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

        # 3. 秘书规则冲突：秘书和学生不能在同一组
        for group in groups:
            if group.secretary:
                secretary_id = group.secretary.id
                for student in group.students.all():
                    if student.secretary_id == secretary_id:
                        conflicts.append({
                            'type': 'secretary_student_conflict',
                            'description': f"秘书 {group.secretary.name} 和自己的学生 {student.name} 在同一组",
                            'group_id': group.id,
                            'secretary_id': secretary_id,
                            'student_id': student.id
                        })

        return conflicts