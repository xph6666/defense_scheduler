from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

import algorithm
from .models import Group, Room, ScheduleVersion, Student, Teacher


class AuthContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='admin', password='strong-pass-123')
        Teacher.objects.create(name='教师1', college='计算机学院', title='教授')

    def test_api_requires_authentication_except_login(self):
        response = self.client.get('/api/teachers/')

        self.assertEqual(response.status_code, 401)

        login_response = self.client.post(
            '/api/auth/login/',
            {'username': 'admin', 'password': 'strong-pass-123'},
            format='json',
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIn('token', login_response.data)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login_response.data['token']}")
        authed_response = self.client.get('/api/teachers/')
        self.assertEqual(authed_response.status_code, 200)
        self.assertEqual(len(authed_response.data), 1)


class IntegrationContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='admin', password='strong-pass-123')
        self.client.force_authenticate(self.user)

    def test_rule_config_api_supports_frontend_contract(self):
        response = self.client.get('/api/rule-config/', {'defense_type': 'pre'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['defenseType'], '预答辩')
        self.assertIn('studentCount', response.data)

        response = self.client.post(
            '/api/rule-config/',
            {
                'defense_type': 'pre',
                'defenseType': '预答辩',
                'studentCount': {'target': 6, 'min': 3, 'max': 8},
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['studentCount']['target'], 6)

    def test_operation_logs_api_supports_frontend_contract(self):
        create_response = self.client.post(
            '/api/operation-logs/',
            {
                'type': 'save_rule_config',
                'module': 'rule-config',
                'description': 'updated rule config',
                'operator': 'admin',
                'result': 'success',
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertIn('createdAt', create_response.data)

        list_response = self.client.get('/api/operation-logs/')
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)

        clear_response = self.client.delete('/api/operation-logs/')
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.data['message'], '日志已清空')
        self.assertEqual(self.client.get('/api/operation-logs/').data, [])

    def test_import_rejects_oversized_files_before_parsing(self):
        oversized_file = SimpleUploadedFile(
            'teachers.csv',
            b'name,title\n' + (b'x' * (5 * 1024 * 1024 + 1)),
            content_type='text/csv',
        )

        response = self.client.post('/api/teachers/import_data/', {'file': oversized_file})

        self.assertEqual(response.status_code, 400)
        self.assertIn('文件大小不能超过', response.data['error'])
        self.assertEqual(Teacher.objects.count(), 0)


class ScheduleContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='admin', password='strong-pass-123')
        self.client.force_authenticate(self.user)
        for index, title in enumerate(['教授', '副教授', '讲师', '讲师'], start=1):
            Teacher.objects.create(
                name=f'教师{index}',
                college='计算机学院',
                title=title,
                roles=['专家', '秘书'],
                available_types=['预答辩'],
            )
        Room.objects.create(
            campus='创新港',
            name='A101',
            capacity=30,
            available_times='',
        )
        for index in range(1, 4):
            Student.objects.create(
                name=f'学生{index}',
                student_type='学硕',
                mentor_name='教师1',
                campus='创新港',
                defense_types=['预答辩'],
                secretary_name='教师4',
            )

    def test_schedule_generate_current_conflict_check_and_export_use_current_models(self):
        generate_response = self.client.post(
            '/api/schedule/generate/',
            {
                'rules': {
                    'defense_type': 'pre',
                    'start_date': '2025-05-10',
                    'end_date': '2025-05-10',
                    'group_size': 3,
                    'expert_count': 2,
                    'avoid_weekend': False,
                    'avoid_supervisor': False,
                }
            },
            format='json',
        )

        self.assertEqual(generate_response.status_code, 200)
        self.assertEqual(generate_response.data['defenseType'], '预答辩')
        self.assertEqual(generate_response.data['groups'][0]['students'][0]['studentType'], '学硕')
        self.assertEqual(generate_response.data['groups'][0]['students'][0]['mentorName'], '教师1')

        current_response = self.client.get('/api/schedule/current/', {'defense_type': 'pre'})
        self.assertEqual(current_response.status_code, 200)
        self.assertEqual(len(current_response.data['groups']), 1)

        conflicts_response = self.client.post(
            '/api/schedule/check-conflicts/',
            {'defense_type': 'pre'},
            format='json',
        )
        self.assertEqual(conflicts_response.status_code, 200)
        self.assertIsInstance(conflicts_response.data, list)

        export_response = self.client.get('/api/schedule/export/', {'defense_type': 'pre'})
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(
            export_response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_schedule_generation_maps_frontend_model_fields_for_constraints(self):
        Teacher.objects.all().delete()
        Student.objects.all().delete()
        Room.objects.all().delete()
        mentor = Teacher.objects.create(
            name='导师张',
            college='计算机学院',
            title='教授',
            roles=['专家'],
            available_types=['预答辩'],
        )
        eligible = Teacher.objects.create(
            name='专家李',
            college='计算机学院',
            title='副教授',
            roles=['专家'],
            available_types=['预答辩'],
        )
        Teacher.objects.create(
            name='秘书王',
            college='计算机学院',
            title='讲师',
            roles=['秘书'],
            available_types=['预答辩'],
        )
        Room.objects.create(campus='创新港', name='A101', capacity=30, available_times='')
        Student.objects.create(
            name='学生1',
            student_type='学硕',
            mentor_name=mentor.name,
            campus='创新港',
            defense_types=['预答辩'],
            secretary_name='秘书王',
        )

        response = self.client.post(
            '/api/schedule/generate/',
            {
                'rules': {
                    'defense_type': 'pre',
                    'start_date': '2025-05-10',
                    'end_date': '2025-05-10',
                    'group_size': 1,
                    'expert_count': 1,
                    'avoid_weekend': False,
                    'avoid_supervisor': True,
                }
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        group = response.data['groups'][0]
        self.assertNotIn(mentor.name, [teacher['name'] for teacher in group['teachers']])
        self.assertIn(eligible.name, [teacher['name'] for teacher in group['teachers']])

    def test_frontend_adjust_and_export_aliases_are_supported(self):
        teacher = Teacher.objects.first()
        secretary = Teacher.objects.last()
        room = Room.objects.first()
        student = Student.objects.first()
        version = ScheduleVersion.objects.create(
            version=1,
            defense_type='pre',
            is_current=True,
            rules_snapshot={},
        )
        group = Group.objects.create(
            schedule_version=version,
            group_id='G1',
            time='2025-05-10 09:00-12:00',
            room=room,
            campus='创新港',
            chair=teacher,
            secretary=secretary,
        )
        group.experts.add(teacher)
        group.students.add(student)

        adjust_response = self.client.post(
            '/api/schedule/adjust-group/',
            {
                'defense_type': 'pre',
                'group_id': group.id,
                'group_data': {
                    'groupName': 'G1-调整',
                    'date': '2025-05-11',
                    'timeRange': '14:00-16:00',
                    'campus': '兴庆',
                    'classroom': room.name,
                    'chairman': teacher.name,
                    'secretary': secretary.name,
                    'teachers': [{'id': teacher.id, 'name': teacher.name, 'title': teacher.title, 'roles': teacher.roles}],
                    'students': [{'id': student.id, 'name': student.name, 'studentType': student.student_type, 'mentorName': student.mentor_name}],
                },
            },
            format='json',
        )
        self.assertEqual(adjust_response.status_code, 200)
        group.refresh_from_db()
        self.assertEqual(group.group_id, 'G1-调整')
        self.assertEqual(group.time, '2025-05-11 14:00-16:00')

        export_response = self.client.get('/api/schedule/export-excel/', {'defenseType': '预答辩'})
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(
            export_response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_adjust_group_rejects_unknown_references_without_partial_update(self):
        teacher = Teacher.objects.first()
        secretary = Teacher.objects.last()
        room = Room.objects.first()
        student = Student.objects.first()
        version = ScheduleVersion.objects.create(
            version=1,
            defense_type='pre',
            is_current=True,
            rules_snapshot={},
        )
        group = Group.objects.create(
            schedule_version=version,
            group_id='G1',
            time='2025-05-10 09:00-12:00',
            room=room,
            campus='创新港',
            chair=teacher,
            secretary=secretary,
        )
        group.experts.add(teacher)
        group.students.add(student)

        response = self.client.post(
            '/api/schedule/adjust-group/',
            {
                'group_id': group.id,
                'group_data': {
                    'groupName': '不应保存',
                    'classroom': '不存在的教室',
                    'chairman': teacher.name,
                    'secretary': secretary.name,
                    'teachers': [{'id': 999999, 'name': '不存在的教师'}],
                    'students': [{'id': student.id, 'name': student.name}],
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('教室不存在', response.data['error'])
        group.refresh_from_db()
        self.assertEqual(group.group_id, 'G1')
        self.assertEqual(list(group.experts.values_list('id', flat=True)), [teacher.id])


class ScheduleConflictContractTests(TestCase):
    """生成排期时的冲突链路与规则键契约"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='admin', password='strong-pass-123')
        self.client.force_authenticate(self.user)

    def _generate(self, rules):
        return self.client.post('/api/schedule/generate/', {'rules': rules}, format='json')

    def test_generate_persists_and_returns_frontend_shaped_conflicts(self):
        # 唯一的老师同时是学生导师，且开启导师回避 → 必然缺专家、缺秘书
        mentor = Teacher.objects.create(name='导师张', college='计算机学院', title='教授')
        Room.objects.create(campus='创新港', name='A101', capacity=30, available_times='')
        Student.objects.create(
            name='学生1', student_type='学硕', mentor_name=mentor.name,
            campus='创新港', defense_types=['预答辩'],
        )

        response = self._generate({
            'defense_type': 'pre',
            'start_date': '2025-05-10',
            'end_date': '2025-05-10',
            'group_size': 1,
            'expert_count': 1,
            'avoid_weekend': False,
            'avoid_supervisor': True,
        })

        self.assertEqual(response.status_code, 200)
        conflicts = response.data['conflicts']
        self.assertTrue(conflicts, '数据不足时生成结果必须携带冲突提示')
        for conflict in conflicts:
            self.assertIn('type', conflict)
            self.assertIn(conflict['level'], ['error', 'warning', 'info'])
            self.assertTrue(conflict['reason'])
            self.assertEqual(conflict['defenseType'], '预答辩')
        self.assertIn('人员冲突', [conflict['type'] for conflict in conflicts])

        version = ScheduleVersion.objects.get(defense_type='pre', is_current=True)
        self.assertTrue(version.conflicts_snapshot, '冲突快照必须持久化')

        current_response = self.client.get('/api/schedule/current/', {'defense_type': 'pre'})
        self.assertEqual(current_response.status_code, 200)
        self.assertEqual(current_response.data['conflicts'], conflicts)

    def test_generate_normalizes_mentor_avoidance_alias(self):
        mentor = Teacher.objects.create(name='导师张', college='计算机学院', title='教授')
        Teacher.objects.create(name='专家李', college='计算机学院', title='副教授')
        Teacher.objects.create(name='秘书王', college='计算机学院', title='讲师')
        Room.objects.create(campus='创新港', name='A101', capacity=30, available_times='')
        Student.objects.create(
            name='学生1', student_type='学硕', mentor_name=mentor.name,
            campus='创新港', defense_types=['预答辩'],
        )

        # 旧键名 mentor_avoidance 也必须触发导师回避
        response = self._generate({
            'defense_type': 'pre',
            'start_date': '2025-05-10',
            'end_date': '2025-05-10',
            'group_size': 1,
            'expert_count': 1,
            'avoid_weekend': False,
            'mentor_avoidance': True,
        })

        self.assertEqual(response.status_code, 200)
        version = ScheduleVersion.objects.get(defense_type='pre', is_current=True)
        self.assertTrue(version.rules_snapshot.get('avoid_supervisor'))
        group = response.data['groups'][0]
        self.assertNotIn(mentor.name, [teacher['name'] for teacher in group['teachers']])

    def test_generate_assigns_chair_when_need_chair_rule_sent(self):
        Teacher.objects.create(name='教授A', college='计算机学院', title='教授')
        Teacher.objects.create(name='讲师B', college='计算机学院', title='讲师')
        Teacher.objects.create(name='讲师C', college='计算机学院', title='讲师')
        Room.objects.create(campus='创新港', name='A101', capacity=30, available_times='')
        Student.objects.create(
            name='学生1', student_type='学硕', mentor_name='',
            campus='创新港', defense_types=['预答辩'],
        )

        response = self._generate({
            'defense_type': 'pre',
            'start_date': '2025-05-10',
            'end_date': '2025-05-10',
            'group_size': 1,
            'expert_count': 1,
            'avoid_weekend': False,
            'avoid_supervisor': False,
            'need_chair': True,
            'chair_title': '教授',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['groups'][0]['chairman'], '教授A')


class AlgorithmTitleRankTests(TestCase):
    """算法职称等级判断：不允许"教授" in "副教授"这类子串误配"""

    def _teacher(self, title):
        return algorithm.Teacher(id=1, name='教师', title=title)

    def test_associate_professor_does_not_satisfy_professor_requirement(self):
        rules = {'chair_title': '教授'}
        self.assertFalse(algorithm.meets_chair_requirement(self._teacher('副教授'), rules))
        self.assertTrue(algorithm.meets_chair_requirement(self._teacher('教授'), rules))

    def test_higher_title_satisfies_lower_requirement(self):
        rules = {'chair_title': '副教授'}
        self.assertTrue(algorithm.meets_chair_requirement(self._teacher('教授'), rules))
        self.assertFalse(algorithm.meets_chair_requirement(self._teacher('讲师'), rules))

    def test_no_requirement_always_passes(self):
        self.assertTrue(algorithm.meets_chair_requirement(self._teacher('讲师'), {}))
        self.assertTrue(algorithm.meets_chair_requirement(self._teacher(None), {'chair_title': ''}))

    def test_unknown_requirement_falls_back_to_exact_match(self):
        rules = {'chair_title': '特聘研究员'}
        self.assertTrue(algorithm.meets_chair_requirement(self._teacher('特聘研究员'), rules))
        self.assertFalse(algorithm.meets_chair_requirement(self._teacher('教授'), rules))
