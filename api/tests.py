import ast
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

import algorithm
from .models import Group, Room, ScheduleVersion, Student, Teacher


class DesktopStartupDependencyTests(TestCase):
    def test_api_views_defers_heavy_spreadsheet_imports_until_needed(self):
        source = Path(__file__).with_name('views.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        top_level_imports = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level_imports.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level_imports.add(node.module.split('.')[0])

        self.assertNotIn('pandas', top_level_imports)
        self.assertNotIn('openpyxl', top_level_imports)


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
        self.assertFalse(login_response.data['isAdmin'])

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login_response.data['token']}")
        authed_response = self.client.get('/api/teachers/')
        self.assertEqual(authed_response.status_code, 200)
        self.assertEqual(len(authed_response.data), 1)


class PermissionContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='viewer', password='strong-pass-123')
        self.client.force_authenticate(self.user)
        Teacher.objects.create(name='教师1', college='计算机学院', title='教授')

    def assert_forbidden(self, response):
        self.assertEqual(response.status_code, 403)

    def test_regular_user_can_read_reference_data_and_schedule_state(self):
        self.assertEqual(self.client.get('/api/teachers/').status_code, 200)
        self.assertEqual(self.client.get('/api/students/').status_code, 200)
        self.assertEqual(self.client.get('/api/rooms/').status_code, 200)
        self.assertEqual(self.client.get('/api/rule-config/', {'defense_type': 'pre'}).status_code, 200)
        self.assertEqual(self.client.get('/api/operation-logs/').status_code, 200)
        self.assertEqual(self.client.get('/api/schedule/current/', {'defense_type': 'pre'}).status_code, 200)
        self.assertEqual(
            self.client.post('/api/schedule/check-conflicts/', {'defense_type': 'pre'}, format='json').status_code,
            200,
        )

    def test_regular_user_cannot_modify_operational_data(self):
        unsafe_requests = [
            self.client.post(
                '/api/teachers/',
                {'name': '教师2', 'college': '计算机学院', 'title': '副教授'},
                format='json',
            ),
            self.client.post('/api/teachers/import_data/', {}, format='multipart'),
            self.client.post('/api/teachers/batch_delete/', {'ids': [1]}, format='json'),
            self.client.post('/api/rule-config/', {'defense_type': 'pre', 'defenseType': '预答辩'}, format='json'),
            self.client.post('/api/schedule/generate/', {'rules': {'defense_type': 'pre'}}, format='json'),
            self.client.post('/api/schedule/adjust-group/', {'group_id': 1, 'group_data': {'groupName': 'G1'}}, format='json'),
            self.client.delete('/api/operation-logs/'),
        ]

        for response in unsafe_requests:
            self.assert_forbidden(response)

    def test_admin_user_can_modify_operational_data(self):
        admin = User.objects.create_superuser(username='admin', password='strong-pass-123')
        self.client.force_authenticate(admin)

        response = self.client.post(
            '/api/teachers/',
            {'name': '教师2', 'college': '计算机学院', 'title': '副教授'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)


class IntegrationContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser(username='admin', password='strong-pass-123')
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
        self.user = User.objects.create_superuser(username='admin', password='strong-pass-123')
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
        self.user = User.objects.create_superuser(username='admin', password='strong-pass-123')
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


class ScheduleTypeFilterTests(TestCase):
    """按答辩类型过滤学生与教师资格"""

    BASE_RULES = {
        'defense_type': 'pre',
        'start_date': '2025-05-10',
        'end_date': '2025-05-10',
        'group_size': 2,
        'expert_count': 1,
        'avoid_weekend': False,
        'avoid_supervisor': False,
    }

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser(username='admin', password='strong-pass-123')
        self.client.force_authenticate(self.user)
        Room.objects.create(campus='创新港', name='A101', capacity=30, available_times='')

    def _generate(self, **overrides):
        return self.client.post(
            '/api/schedule/generate/',
            {'rules': {**self.BASE_RULES, **overrides}},
            format='json',
        )

    def _scheduled_student_names(self, response):
        return [
            student['name']
            for group in response.data['groups']
            for student in group['students']
        ]

    def _scheduled_teacher_names(self, response):
        names = []
        for group in response.data['groups']:
            names.extend(teacher['name'] for teacher in group['teachers'])
            names.extend(name for name in [group.get('chairman'), group.get('secretary')] if name)
        return names

    def test_students_filtered_by_defense_type(self):
        Teacher.objects.create(name='老师甲', title='教授')
        Teacher.objects.create(name='老师乙', title='讲师')
        Student.objects.create(
            name='预答辩学生', student_type='学硕', campus='创新港', defense_types=['预答辩'],
        )
        Student.objects.create(
            name='正式答辩学生', student_type='学硕', campus='创新港', defense_types=['正式答辩'],
        )

        response = self._generate()

        self.assertEqual(response.status_code, 200)
        names = self._scheduled_student_names(response)
        self.assertIn('预答辩学生', names)
        self.assertNotIn('正式答辩学生', names)

    def test_student_without_defense_types_skipped_with_notice(self):
        Teacher.objects.create(name='老师甲', title='教授')
        Teacher.objects.create(name='老师乙', title='讲师')
        Student.objects.create(
            name='正常学生', student_type='学硕', campus='创新港', defense_types=['预答辩'],
        )
        Student.objects.create(
            name='漏填学生', student_type='学硕', campus='创新港', defense_types=[],
        )

        response = self._generate()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('漏填学生', self._scheduled_student_names(response))
        notices = [c for c in response.data['conflicts'] if c['type'] == '数据完整性提示']
        self.assertEqual(len(notices), 1)
        self.assertIn('漏填学生', notices[0]['reason'])
        self.assertEqual(notices[0]['level'], 'warning')

    def test_teachers_filtered_by_available_types(self):
        Teacher.objects.create(name='不限老师', title='教授', available_types=[])
        Teacher.objects.create(name='预答辩老师', title='讲师', available_types=['预答辩'])
        Teacher.objects.create(name='仅正式老师', title='讲师', available_types=['正式答辩'])
        Student.objects.create(
            name='学生1', student_type='学硕', campus='创新港', defense_types=['预答辩'],
        )

        response = self._generate(expert_count=2)

        self.assertEqual(response.status_code, 200)
        names = self._scheduled_teacher_names(response)
        self.assertNotIn('仅正式老师', names)
        self.assertIn('不限老师', names)

    def test_generate_rejects_when_no_students_match_defense_type(self):
        Teacher.objects.create(name='老师甲', title='教授')
        Student.objects.create(
            name='正式答辩学生', student_type='学硕', campus='创新港', defense_types=['正式答辩'],
        )

        response = self._generate()

        self.assertEqual(response.status_code, 400)
        self.assertIn('没有学生参加【预答辩】', response.data['error'])

    def test_generate_rejects_when_no_teachers_match_defense_type(self):
        Teacher.objects.create(name='仅正式老师', title='教授', available_types=['正式答辩'])
        Student.objects.create(
            name='学生1', student_type='学硕', campus='创新港', defense_types=['预答辩'],
        )

        response = self._generate()

        self.assertEqual(response.status_code, 400)
        self.assertIn('没有可参加【预答辩】的教师', response.data['error'])


class AlgorithmGroupSizeTests(TestCase):
    """每组人数上下限的算法行为"""

    @staticmethod
    def _students(count):
        return [algorithm.Student(id=i, name=f'S{i}', campus='创新港') for i in range(1, count + 1)]

    def test_small_tail_group_merges_into_previous(self):
        rules = {'group_size': 3, 'group_min': 2, 'group_max': 5}
        groups = algorithm.build_student_groups(self._students(4), rules)
        self.assertEqual([len(g) for g in groups], [4])

    def test_tail_group_kept_when_merge_would_exceed_max(self):
        rules = {'group_size': 3, 'group_min': 2, 'group_max': 3}
        groups = algorithm.build_student_groups(self._students(4), rules)
        self.assertEqual([len(g) for g in groups], [3, 1])

    def test_grouping_unchanged_without_min_max(self):
        rules = {'group_size': 3}
        groups = algorithm.build_student_groups(self._students(4), rules)
        self.assertEqual([len(g) for g in groups], [3, 1])

    def test_check_group_size_flags_out_of_range(self):
        rules = {'group_min': 2, 'group_max': 5}
        below = algorithm.check_group_size('G1', 1, rules)
        self.assertEqual(below[0]['type'], 'group_size_out_of_range')
        above = algorithm.check_group_size('G1', 6, rules)
        self.assertEqual(above[0]['type'], 'group_size_out_of_range')
        self.assertEqual(algorithm.check_group_size('G1', 3, rules), [])


class ScheduleRuleEffectTests(TestCase):
    """秘书职称门槛、资深优先、专家下限降级的端到端效果"""

    BASE_RULES = {
        'defense_type': 'pre',
        'start_date': '2025-05-10',
        'end_date': '2025-05-10',
        'group_size': 1,
        'expert_count': 1,
        'avoid_weekend': False,
        'avoid_supervisor': False,
    }

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser(username='admin', password='strong-pass-123')
        self.client.force_authenticate(self.user)
        Room.objects.create(campus='创新港', name='A101', capacity=30, available_times='')

    def _generate(self, **overrides):
        return self.client.post(
            '/api/schedule/generate/',
            {'rules': {**self.BASE_RULES, **overrides}},
            format='json',
        )

    def _setup_three_teachers_one_student(self):
        Teacher.objects.create(name='陈教授', title='教授')
        Teacher.objects.create(name='李副教授', title='副教授')
        Teacher.objects.create(name='张讲师', title='讲师')
        Student.objects.create(
            name='学生1', student_type='学硕', campus='创新港', defense_types=['预答辩'],
        )

    def test_secretary_title_threshold_blocks_low_rank(self):
        # 主席=陈教授、专家=李副教授（资深优先），剩余张讲师低于"副教授"门槛 → 秘书缺位
        self._setup_three_teachers_one_student()

        response = self._generate(
            need_chair=True, chair_title='教授',
            secretary_title='副教授', prefer_senior=True,
        )

        self.assertEqual(response.status_code, 200)
        group = response.data['groups'][0]
        self.assertEqual(group['chairman'], '陈教授')
        self.assertEqual(group['secretary'], '未分配')
        self.assertIn('人员冲突', [c['type'] for c in response.data['conflicts']])

    def test_secretary_title_threshold_allows_qualified(self):
        self._setup_three_teachers_one_student()

        response = self._generate(
            need_chair=True, chair_title='教授',
            secretary_title='讲师', prefer_senior=True,
        )

        self.assertEqual(response.status_code, 200)
        group = response.data['groups'][0]
        self.assertEqual(group['secretary'], '张讲师')

    def test_prefer_senior_picks_highest_title_expert(self):
        self._setup_three_teachers_one_student()

        response = self._generate(prefer_senior=True)

        self.assertEqual(response.status_code, 200)
        expert_names = [t['name'] for t in response.data['groups'][0]['teachers']]
        self.assertEqual(expert_names, ['陈教授'])

    def test_expert_shortage_downgrades_to_warning_when_min_met(self):
        # 导师被回避后可用专家 2 人：低于目标 3 但达到下限 2 → warning 而非 error
        mentor = Teacher.objects.create(name='王教授', title='教授')
        Teacher.objects.create(name='李副教授', title='副教授')
        Teacher.objects.create(name='张讲师', title='讲师')
        Student.objects.create(
            name='学生1', student_type='学硕', mentor_name=mentor.name,
            campus='创新港', defense_types=['预答辩'],
        )

        response = self._generate(avoid_supervisor=True, expert_count=3, expert_min=2)

        self.assertEqual(response.status_code, 200)
        shortage = [c for c in response.data['conflicts'] if 'experts' in c['reason']]
        self.assertEqual(len(shortage), 1)
        self.assertEqual(shortage[0]['level'], 'warning')

    def test_expert_shortage_stays_error_below_min(self):
        mentor = Teacher.objects.create(name='王教授', title='教授')
        Teacher.objects.create(name='李副教授', title='副教授')
        Student.objects.create(
            name='学生1', student_type='学硕', mentor_name=mentor.name,
            campus='创新港', defense_types=['预答辩'],
        )

        response = self._generate(avoid_supervisor=True, expert_count=3, expert_min=2)

        self.assertEqual(response.status_code, 200)
        shortage = [c for c in response.data['conflicts'] if 'experts' in c['reason']]
        self.assertEqual(len(shortage), 1)
        self.assertEqual(shortage[0]['level'], 'error')


class TimeToleranceAndTimezoneTests(TestCase):
    """时间格式容错与本地时区显示"""

    RULES = {
        'defense_type': 'pre',
        'start_date': '2025-05-10',
        'end_date': '2025-05-10',
        'group_size': 1,
        'expert_count': 1,
        'avoid_weekend': False,
        'avoid_supervisor': False,
    }

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser(username='admin', password='strong-pass-123')
        self.client.force_authenticate(self.user)
        Student.objects.create(
            name='学生1', student_type='学硕', campus='创新港', defense_types=['预答辩'],
        )

    def _generate(self):
        return self.client.post('/api/schedule/generate/', {'rules': self.RULES}, format='json')

    def _assigned_teacher_names(self, response):
        names = []
        for group in response.data['groups']:
            names.extend(teacher['name'] for teacher in group['teachers'])
            names.extend(name for name in [group.get('chairman'), group.get('secretary')] if name and name != '未分配')
        return names

    def test_fullwidth_and_slash_time_formats_are_normalized(self):
        # 全角冒号 + 斜杠日期 + 波浪线的不可用时间应被归一化并真实生效
        Teacher.objects.create(
            name='忙碌老师', title='教授',
            unavailable_times='2025/05/10 09：00～12：00',
        )
        Teacher.objects.create(name='空闲老师甲', title='副教授')
        Teacher.objects.create(name='空闲老师乙', title='讲师')
        Room.objects.create(
            campus='创新港', name='A101', capacity=30,
            available_times='2025-05-10 09:00-12:00',
        )

        response = self._generate()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('忙碌老师', self._assigned_teacher_names(response))
        notices = [c for c in response.data['conflicts'] if c['type'] == '数据完整性提示']
        self.assertEqual(notices, [])

    def test_unparseable_time_generates_notice_instead_of_error(self):
        Teacher.objects.create(name='王老师', title='教授', unavailable_times='周一上午')
        Teacher.objects.create(name='李老师', title='讲师')
        Room.objects.create(campus='创新港', name='A101', capacity=30, available_times='')

        response = self._generate()

        self.assertEqual(response.status_code, 200)
        notices = [c for c in response.data['conflicts'] if c['type'] == '数据完整性提示']
        self.assertEqual(len(notices), 1)
        self.assertIn('王老师', notices[0]['reason'])
        self.assertIn('周一上午', notices[0]['reason'])
        # 无法解析的时间被忽略，教师本身仍参与排期
        self.assertIn('王老师', self._assigned_teacher_names(response))

    def test_room_invalid_time_falls_back_with_notice(self):
        Teacher.objects.create(name='王老师', title='教授')
        Teacher.objects.create(name='李老师', title='讲师')
        Room.objects.create(campus='创新港', name='B202', capacity=30, available_times='随时')

        response = self._generate()

        self.assertEqual(response.status_code, 200)
        notices = [c for c in response.data['conflicts'] if c['type'] == '数据完整性提示']
        self.assertEqual(len(notices), 1)
        self.assertIn('B202', notices[0]['reason'])
        # 教室时间被忽略后回退到默认时段，分组仍可排出时间
        self.assertTrue(response.data['groups'][0]['date'])

    def test_generated_at_uses_local_timezone(self):
        from django.utils import timezone as dj_timezone

        Teacher.objects.create(name='王老师', title='教授')
        Teacher.objects.create(name='李老师', title='讲师')
        Room.objects.create(campus='创新港', name='A101', capacity=30, available_times='')

        response = self._generate()

        self.assertEqual(response.status_code, 200)
        version = ScheduleVersion.objects.get(defense_type='pre', is_current=True)
        expected = dj_timezone.localtime(version.created_at).strftime('%Y-%m-%d %H:%M')
        self.assertEqual(response.data['generatedAt'], expected)
