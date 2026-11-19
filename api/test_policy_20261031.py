"""Current requirements, with historical policy snapshots kept readable."""
from copy import deepcopy

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from algorithm import GroupDraft, generate_schedule, parse_student, parse_teacher, parse_time_range
from api.models import Room, ScheduleVersion, Student, Teacher
from api.serializers import default_rule_config, validate_rule_config
from api.services.rules import normalize_schedule_rules
from scheduling.current import validate


def rules(stage='pre', **overrides):
    return normalize_schedule_rules(dict(policy_version=4, defense_type=stage,
        start_date='2026-11-02', end_date='2026-11-03', **overrides))


def staff():
    return [dict(id=i, name=f'T{i}', title='教授', roles=['组长', '普通专家'],
                 availability_confirmed=True, is_external=i == 3) for i in range(1, 12)] + [
        dict(id=12, name='秘书', title='讲师', roles=['秘书'], availability_confirmed=True)]


def cohort(count=10, campus='创新港', start=1):
    return [dict(id=i, name=f'S{i}', supervisor_id=1, campus=campus)
            for i in range(start, start + count)]


class CurrentRequirementTests(SimpleTestCase):
    def test_mid_fixed_counts_and_no_supervisor_restriction(self):
        config = rules('mid', avoid_supervisor=True, supervisor_policy='avoid')
        self.assertEqual((config['group_size'], config['group_min'], config['group_max']), (10, 10, 10))
        self.assertEqual((config['expert_count'], config['expert_min']), (5, 5))
        self.assertFalse(config['avoid_supervisor'])
        self.assertEqual(config['supervisor_policy'], 'none')
        for changed in [dict(group_max=12), dict(group_size=12, group_max=12),
                        dict(expert_count=6), dict(expert_min=4)]:
            with self.subTest(changed=changed), self.assertRaises(ValidationError):
                rules('mid', **changed)

    def test_mid_generation_keeps_ten_and_reports_each_campus_remainder(self):
        students = cohort(11) + cohort(9, '兴庆', 20)
        result = generate_schedule(staff(), students,
            [dict(id=1, campus='创新港', name='A', capacity=30)], rules('mid'))
        self.assertEqual([len(g['student_ids']) for g in result['groups']], [10])
        self.assertEqual(result['groups'][0]['campus'], '创新港')
        pending = {s['id'] for s in result['unassigned_students']}
        assigned = {sid for g in result['groups'] for sid in g['student_ids']}
        self.assertEqual(pending | assigned, {s['id'] for s in students})
        self.assertFalse(pending & assigned)
        self.assertEqual(len(pending), 10)
        self.assertTrue(all('不足 10 人' in s['reason'] for s in result['unassigned_students']))
        self.assertFalse(any(c['type'] in {'supervisor_avoidance', 'supervisor_missing',
            'expert_count_out_of_range'} for c in result['conflicts']))

    def test_mid_with_many_mentors_does_not_require_them_all_on_panel(self):
        students = cohort()
        for i, student in enumerate(students):
            student['supervisor_id'] = i + 1
        result = generate_schedule(staff(), students,
            [dict(id=1, campus='创新港', name='A', capacity=30)], rules('mid'))
        group = result['groups'][0]
        self.assertEqual(len({group['chair_id'], *group['expert_ids']}), 5)
        self.assertFalse(any(c['type'] in {'supervisor_missing', 'supervisor_avoidance'} for c in result['conflicts']))

    def test_pre_chair_is_senior_and_optional_external_is_not_preferred(self):
        teachers = staff()
        teachers[0]['title'] = '副教授'
        result = generate_schedule(teachers, cohort(6), [], rules())
        self.assertEqual(result['unassigned_students'], [])
        group = result['groups'][0]
        self.assertNotEqual(group['chair_id'], 1)
        self.assertNotIn(3, {group['chair_id'], *group['expert_ids']})
        self.assertFalse(any(c['type'] == 'external_distribution' for c in result['conflicts']))
        with self.assertRaises(ValidationError):
            rules(chair_title='副教授')

    def test_no_senior_chair_leaves_students_explicitly_unassigned(self):
        teachers = staff()
        for teacher in teachers[:-1]:
            teacher['title'] = '副教授'
        result = generate_schedule(teachers, cohort(6), [], rules())
        self.assertEqual(result['groups'], [])
        self.assertEqual(len(result['unassigned_students']), 6)

    def test_required_external_majority_is_an_explained_soft_exception(self):
        teachers = staff()
        teachers[1].update(is_external=True, title='副教授')
        teachers[2]['title'] = '副教授'
        students = cohort(6)
        for i, student in enumerate(students):
            student['supervisor_id'] = 2 if i < 3 else 3
        result = generate_schedule(teachers, students, [], rules())
        self.assertEqual(result['unassigned_students'], [])
        self.assertTrue(any(c['type'] == 'external_distribution' and '外院专家 2 位，本院专家 1 位' in c['description']
                            for c in result['conflicts']))

    def test_formal_translation_does_not_silently_drop_a_source_student(self):
        from scheduling.formal_rotation import rotate_panels
        from scheduling.policies import formal_rotation_rules
        students = cohort(5)
        source = [GroupDraft('G001', '创新港', list(range(1, 7)),
            parse_time_range('2026-11-02 09:00-12:00'), None, 1, [2, 3], 12)]
        result = rotate_panels(source, [parse_teacher(t) for t in staff()],
            [parse_student(s) for s in students], {**rules('formal'), **formal_rotation_rules('教授')})
        self.assertEqual(result['groups'], [])
        self.assertEqual(len(result['unassigned_students']), 5)
        self.assertTrue(all('参与学生已变化' in s['reason'] for s in result['unassigned_students']))

    def test_campus_mixing_and_inherited_mapping_are_hard_conflicts(self):
        students = cohort(6)
        for student in students:
            student.update(previous_group_id='G001', secretary_id=12)
        group = GroupDraft('G002', '兴庆', list(range(1, 7)),
            parse_time_range('2026-11-02 09:00-12:00'), None, 4, [5, 6, 7, 8], 11)
        config = {**rules('formal'), 'formal_rotation': True}
        conflicts = validate([group], [parse_student(s) for s in students],
                             [parse_teacher(t) for t in staff()], config)
        self.assertTrue(any(c['type'] == 'student_campus_mismatch' for c in conflicts))
        self.assertTrue(any(c['type'] == 'pre_group_mapping_broken' for c in conflicts))

    def test_config_api_and_engine_share_new_boundaries(self):
        for stage in ('pre', 'mid'):
            config = default_rule_config(stage)
            self.assertEqual(config['policyVersion'], 4)
            validate_rule_config(config)
            invalid = deepcopy(config)
            if stage == 'pre':
                invalid['roleQualification']['leaderMinTitle'] = '副教授'
            else:
                invalid['studentCount']['max'] = 12
            with self.assertRaises(ValidationError):
                validate_rule_config(invalid)
        legacy = normalize_schedule_rules(dict(policy_version=2, defense_type='mid'))
        self.assertEqual(legacy['group_max'], 12)
        self.assertEqual(legacy['supervisor_policy'], 'same_group')
        self.assertEqual(normalize_schedule_rules(dict(policy_version=3, defense_type='pre'))['chair_title'], '副教授')


class CurrentRequirementApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('current-admin', is_staff=True))
        self.teachers = [Teacher.objects.create(name=t['name'], title=t['title'],
            roles=t['roles'], availability_confirmed=True) for t in staff()]

    def test_mid_campus_tails_are_scheduled_and_flagged_for_review(self):
        for campus, count in [('创新港', 13), ('兴庆', 8)]:
            Room.objects.create(name='A101', campus=campus, capacity=30)
            for index in range(count):
                Student.objects.create(name=f'{campus}{index}', mentor=self.teachers[0],
                    campus=campus, defense_types=['中期答辩'])

        config = self.client.post('/api/rule-config/',
            {'defense_type': 'mid', 'allowMidRemainderGroup': True}, format='json')
        self.assertEqual(config.status_code, 200, config.data)
        response = self.client.post('/api/schedule/generate/',
            {'rules': rules('mid', allow_mid_remainder_group=config.data['allowMidRemainderGroup'])}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['unassignedStudents'], [])
        self.assertCountEqual([(g['campus'], len(g['students'])) for g in response.data['groups']],
            [('创新港', 10), ('创新港', 3), ('兴庆', 8)])
        issues = response.data['conflicts']
        self.assertFalse([c for c in issues if c['level'] == 'error'], issues)
        self.assertEqual(sum(c['type'] == '中期答辩尾组' and c['level'] == 'warning' for c in issues), 2)

        version = ScheduleVersion.objects.get(pk=response.data['versionId'])
        full, tail = sorted(version.groups.filter(campus='创新港'), key=lambda g: -g.students.count())
        moved = list(full.students.all()[:2])
        full.students.remove(*moved)
        tail.students.add(*moved)
        bad = self.client.post('/api/schedule/publish/', dict(version_id=version.pk,
            expected_revision=version.revision), format='json')
        self.assertEqual(bad.status_code, 400, bad.data)
        self.assertTrue(any(c['type'] == '人数规则冲突' for c in bad.data['conflicts']))

        tail.students.remove(*moved)
        full.students.add(*moved)
        publish = self.client.post('/api/schedule/publish/', dict(version_id=version.pk,
            expected_revision=version.revision), format='json')
        self.assertEqual(publish.status_code, 200, publish.data)

    def test_mid_without_tail_enforces_same_campus_rooms_and_students(self):
        Room.objects.create(name='A101', campus='创新港', capacity=30)
        for index in range(10):
            Student.objects.create(name=f'兴庆{index}', mentor=self.teachers[0],
                campus='兴庆', defense_types=['中期答辩'])

        response = self.client.post('/api/schedule/generate/', {'rules': rules('mid')}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['groups'][0]['classroom'], '待预约')
        self.assertTrue(any(c['type'] == '教室冲突' and c['level'] == 'error' for c in response.data['conflicts']))

        xingqing_room = Room.objects.create(name='X101', campus='兴庆', capacity=30)
        version = ScheduleVersion.objects.get(pk=response.data['versionId'])
        group = version.groups.get()
        group.room = Room.objects.get(campus='创新港')
        group.time = '2026-11-02 09:00-12:00'
        group.save()
        bad_room = self.client.post('/api/schedule/publish/', dict(version_id=version.pk,
            expected_revision=version.revision), format='json')
        self.assertEqual(bad_room.status_code, 400, bad_room.data)
        self.assertTrue(any(c['type'] == '学生校区冲突' for c in bad_room.data['conflicts']))

        group.room = xingqing_room
        group.save()
        wrong_student = Student.objects.create(name='误入创新港生', mentor=self.teachers[0],
            campus='创新港', defense_types=['中期答辩'])
        group.students.remove(group.students.first())
        group.students.add(wrong_student)
        bad_student = self.client.post('/api/schedule/publish/', dict(version_id=version.pk,
            expected_revision=version.revision), format='json')
        self.assertEqual(bad_student.status_code, 400, bad_student.data)
        self.assertTrue(any(c['type'] == '学生校区冲突' for c in bad_student.data['conflicts']))

    def test_mid_policy4_move_student_does_not_mutate_committee_or_chair(self):
        Room.objects.create(name='A101', campus='创新港', capacity=30)
        Room.objects.create(name='A102', campus='创新港', capacity=30)
        mentor = self.teachers[0]
        other_mentor = self.teachers[1]
        for index in range(20):
            Student.objects.create(name=f'中生{index}', mentor=mentor if index == 0 else other_mentor,
                campus='创新港', defense_types=['中期答辩'])

        generated = self.client.post('/api/schedule/generate/', {'rules': rules('mid')}, format='json')
        self.assertEqual(generated.status_code, 200, generated.data)
        version = ScheduleVersion.objects.get(pk=generated.data['versionId'])
        g1, g2 = list(version.groups.order_by('id'))
        student = Student.objects.get(name='中生0')
        source, target = (g1, g2) if g1.students.filter(pk=student.pk).exists() else (g2, g1)
        source.chair = mentor
        source.experts.set(self.teachers[2:6])
        source.save()
        target.chair = self.teachers[6]
        target.experts.set(self.teachers[7:11])
        target.save()
        source_experts_before = sorted(source.experts.values_list('pk', flat=True))
        target_experts_before = sorted(target.experts.values_list('pk', flat=True))

        moved = self.client.post('/api/schedule/adjust/', {
            'action': 'move_student', 'student_id': student.pk,
            'from_group_id': source.pk, 'to_group_id': target.pk,
            'expected_revision': version.revision, 'move_mentor': True,
        }, format='json')
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertFalse(moved.data['movement']['mentorMoved'])
        source.refresh_from_db(); target.refresh_from_db()
        self.assertEqual(source.chair_id, mentor.pk)
        self.assertEqual(sorted(source.experts.values_list('pk', flat=True)), source_experts_before)
        self.assertEqual(sorted(target.experts.values_list('pk', flat=True)), target_experts_before)

    def test_mid_generation_and_publish_with_own_mentor(self):
        for index in range(10):
            Student.objects.create(name=f'M{index}', mentor=self.teachers[0],
                campus='创新港', defense_types=['中期答辩'])
        Room.objects.create(name='A101', campus='创新港', capacity=30)
        response = self.client.post('/api/schedule/generate/', {'rules': rules('mid')}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['groups'][0]['students']), 10)
        version = ScheduleVersion.objects.get(pk=response.data['versionId'])
        group = version.groups.get()
        group.chair = self.teachers[0]
        group.experts.set(self.teachers[1:5])
        group.save()
        response = self.client.post('/api/schedule/publish/', dict(version_id=version.pk,
            expected_revision=version.revision), format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_linked_translation_retains_group_students_campus_and_secretary(self):
        for campus in ('创新港', '兴庆'):
            for index in range(6):
                Student.objects.create(name=f'{campus}{index}', mentor=self.teachers[0],
                    campus=campus, defense_types=['预答辩', '正式答辩'])
        response = self.client.post('/api/schedule/generate-linked/', dict(
            pre_rules=rules(), formal_rules={**rules('formal'), 'start_date': '2026-11-04',
                'end_date': '2026-11-05'}), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        pre, formal = response.data['pre'], response.data['formal']
        self.assertEqual(len(pre['groups']), 2)
        self.assertEqual(len(formal['groups']), 2)
        self.assertEqual(formal['sourcePreVersionId'], pre['versionId'])
        def identity(result):
            return {g['groupName']: (g['campus'], g['secretaryId'],
                    sorted(s['id'] for s in g['students'])) for g in result['groups']}
        self.assertEqual(identity(pre), identity(formal))
        self.assertFalse(any(c['level'] == 'error' for c in formal['conflicts']), formal['conflicts'])
        version = ScheduleVersion.objects.get(pk=formal['versionId'])
        group = version.groups.first()
        group.campus = '兴庆' if group.campus == '创新港' else '创新港'
        group.save()
        response = self.client.post('/api/schedule/publish/', dict(version_id=version.pk,
            expected_revision=version.revision), format='json')
        self.assertEqual(response.status_code, 400, response.data)
