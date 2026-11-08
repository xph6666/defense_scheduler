"""Campus batches, stage mapping, timetable preview and actual generation progress."""
import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, SimpleTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from algorithm import generate_schedule
from api.models import Group, OperationLog, Room, ScheduleVersion, Student, Teacher
from api.schedule_views import ScheduleViewSet
from api.serializers import default_rule_config, validate_rule_config
from api.services.rules import normalize_schedule_rules
from api.services.scheduling_input import build_algorithm_input
from api.services.stage_mapping import build_stage_mapping
from api.services.generation_progress import progress_key


def rules(stage='pre', **changes):
    return normalize_schedule_rules(dict(policy_version=4, defense_type=stage,
        start_date='2026-11-02', end_date='2026-11-03', **changes))


class SeniorMidChairTests(SimpleTestCase):
    def test_mid_cannot_lower_chair_requirement(self):
        self.assertEqual(rules('mid')['chair_title'], '教授')
        with self.assertRaises(ValidationError):
            rules('mid', chair_title='副教授')
        config = default_rule_config('mid')
        self.assertEqual(config['roleQualification']['leaderMinTitle'], '教授')
        config['roleQualification']['leaderMinTitle'] = '副研究员'
        with self.assertRaises(ValidationError):
            validate_rule_config(config)

    def test_mid_has_no_junior_chair_fallback(self):
        teachers = [dict(id=i, name=f'T{i}', title='副教授', roles=['组长', '普通专家', '秘书']) for i in range(1, 8)]
        students = [dict(id=i, name=f'S{i}', campus='创新港', supervisor_id=1) for i in range(1, 11)]
        result = generate_schedule(teachers, students,
            [dict(id=1, campus='创新港', name='A', capacity=30)], rules('mid'))
        self.assertTrue(any(c['type'] in ('chair_unavailable', 'insufficient_experts') for c in result['conflicts']))
        self.assertFalse(any(g['chair_id'] for g in result['groups']))


class LatestRequirementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user('latest-admin', password='test', is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.teachers = [Teacher.objects.create(name=f'教师{i}', title='教授', roles=['组长', '普通专家'],
            availability_confirmed=True) for i in range(1, 12)]
        self.secretary = Teacher.objects.create(name='秘书甲', title='讲师', roles=['秘书'], availability_confirmed=True)
        for campus in ('创新港', '兴庆'):
            for i in range(6):
                Student.objects.create(name=f'{campus}学生{i}', student_no=f'{campus}{i}', campus=campus,
                    mentor=self.teachers[i % 3], mentor_name=self.teachers[i % 3].name,
                    defense_types=['预答辩', '正式答辩'])

    def generate(self, campus, key):
        response = self.client.post('/api/schedule/generate/', {
            'rules': rules(campus_scope=campus), 'request_key': key}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return ScheduleVersion.objects.get(pk=response.data['versionId'])

    def test_independent_campus_batches_share_teacher_reservations(self):
        first = self.generate('创新港', 'campus-a')
        self.assertEqual(first.campus_scope, '创新港', first.rules_snapshot)
        from api.services.campus_batches import other_batch_reservations
        self.assertTrue(other_batch_reservations(rules(campus_scope='兴庆')), list(ScheduleVersion.objects.values()))
        payload, _ = build_algorithm_input('pre', rules=rules(campus_scope='兴庆'))
        self.assertTrue(next(t['available_time'] for t in payload['teachers'] if t['id'] == self.teachers[0].pk), payload['teachers'])
        second = self.generate('兴庆', 'campus-b')
        first.refresh_from_db()
        self.assertTrue(first.is_current)
        self.assertTrue(second.is_current)
        self.assertEqual(first.groups.count(), 1)
        self.assertEqual(second.groups.count(), 1)
        left, right = first.groups.first(), second.groups.first()
        self.assertNotEqual(left.time, right.time, (list(left.experts.values_list('id', flat=True)), left.chair_id,
                            list(right.experts.values_list('id', flat=True)), right.chair_id,
                            first.rules_snapshot, second.rules_snapshot))
        self.assertEqual({s.campus for s in right.students.all()}, {'兴庆'})
        response = self.client.get('/api/schedule/current/', {'defense_type': 'pre', 'campus_scope': '创新港'})
        self.assertEqual(response.data['versionId'], first.pk)
        response = self.client.get('/api/schedule/versions/', {'defense_type': 'pre', 'campus_scope': '兴庆'})
        self.assertEqual([v['id'] for v in response.data], [second.pk])
        right.time = left.time
        right.save()
        conflicts = ScheduleViewSet()._check_conflicts(second)
        self.assertTrue(any(c['type'] == 'teacher_time_conflict' for c in conflicts), conflicts)
        response = self.client.post('/api/schedule/publish/', {
            'version_id': second.pk, 'expected_revision': second.revision}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_progress_uses_real_checkpoints_and_is_private(self):
        real = generate_schedule
        seen = []
        def observe(**kwargs):
            seen.append(cache.get(progress_key(self.user.pk, 'actual-progress')))
            return real(**kwargs)
        with patch('algorithm.generate_schedule', side_effect=observe):
            self.generate('创新港', 'actual-progress')
        self.assertEqual(seen[0]['stage'], 'solving')
        self.assertEqual(seen[0]['percent'], 25)
        response = self.client.get('/api/schedule/generation-progress/', {'request_key': 'actual-progress'})
        self.assertEqual((response.data['percent'], response.data['status']), (100, 'completed'))
        other = get_user_model().objects.create_user('other-admin', is_staff=True)
        self.client.force_authenticate(other)
        response = self.client.get('/api/schedule/generation-progress/', {'request_key': 'actual-progress'})
        self.assertEqual(response.data['status'], 'waiting')

    def test_failed_generation_reports_failure_and_rolls_back(self):
        response = self.client.post('/api/schedule/generate/', {'rules': {**rules(campus_scope='创新港'),
            'expert_count': 1}, 'request_key': 'failure'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ScheduleVersion.objects.exists())
        progress = cache.get(progress_key(self.user.pk, 'failure'))
        self.assertEqual(progress['status'], 'failed')
        self.assertLess(progress['percent'], 100)

    def test_linked_campus_generation_uses_its_fresh_roster(self):
        response = self.client.post('/api/schedule/generate-linked/', {
            'pre_rules': rules(campus_scope='创新港'),
            'formal_rules': {**rules('formal', campus_scope='创新港', use_confirmed_pre_students=True),
                             'start_date': '2026-11-04', 'end_date': '2026-11-05'},
            'request_key': 'linked-campus'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['formal']['sourcePreVersionId'], response.data['pre']['versionId'])
        self.assertEqual(response.data['formal']['campusScope'], '创新港')
        self.assertTrue(response.data['formal']['groups'])
        self.assertEqual(cache.get(progress_key(self.user.pk, 'linked-campus'))['percent'], 100)

    def test_mapping_tracks_actual_splits_merges_missing_and_duplicates(self):
        students = list(Student.objects.filter(campus='创新港'))
        pre = ScheduleVersion.objects.create(version=1, defense_type='pre', campus_scope='创新港')
        formal = ScheduleVersion.objects.create(version=1, defense_type='formal', campus_scope='创新港', source_pre_version=pre)
        p1 = Group.objects.create(schedule_version=pre, group_id='P1', campus='创新港', time='')
        p2 = Group.objects.create(schedule_version=pre, group_id='P2', campus='创新港', time='')
        f1 = Group.objects.create(schedule_version=formal, group_id='F1', campus='创新港', time='')
        f2 = Group.objects.create(schedule_version=formal, group_id='F2', campus='创新港', time='')
        p1.students.set(students[:3]); p2.students.set(students[3:5])
        f1.students.set([students[0], students[3], students[5]])
        f2.students.set([students[1], students[2]])
        data = build_stage_mapping(pre, formal)
        self.assertEqual(data['summary'], dict(matched=4, pending_formal=1, missing_pre=1, duplicate=0))
        self.assertEqual({(link['preGroup'], link['formalGroup']) for link in data['links']},
                         {('P1', 'F1'), ('P1', 'F2'), ('P2', 'F1')})
        f2.students.add(students[0])
        self.assertEqual(build_stage_mapping(pre, formal)['summary']['duplicate'], 1)
        response = self.client.get('/api/schedule/stage-mapping/', {'defense_type': 'formal', 'version_id': formal.pk})
        self.assertEqual(response.data['summary']['duplicate'], 1)

    def test_confirmed_roster_reads_pre_students_without_reimport(self):
        pre = self.generate('创新港', 'roster')
        pre.status = 'published'; pre.save()
        Student.objects.filter(campus='创新港').update(defense_types=['预答辩'])
        config = rules('formal', campus_scope='创新港', use_confirmed_pre_students=True,
                       preserve_pre_defense_groups=False)
        payload, _ = build_algorithm_input('formal', rules=config)
        self.assertEqual(len(payload['students']), 6)
        self.assertTrue(all(student['previous_group_id'] for student in payload['students']))

    def upload(self, rows):
        from openpyxl import Workbook
        import json
        key = json.dumps(rows, ensure_ascii=False)
        uploads = getattr(self, '_uploads', {})
        if key in uploads:
            return SimpleUploadedFile('timetable.xlsx', uploads[key])
        book = Workbook(); sheet = book.active
        for row in rows:
            sheet.append(row)
        stream = io.BytesIO(); book.save(stream)
        uploads[key] = stream.getvalue()
        self._uploads = uploads
        return SimpleUploadedFile('timetable.xlsx', uploads[key])

    def timetable(self, rows, **options):
        return self.client.post('/api/teachers/import_timetable/', {
            'file': self.upload(rows), 'semesterFirstMonday': '2026-11-02', **options}, format='multipart')

    def test_timetable_preview_does_not_write_and_reports_all_errors(self):
        teacher = self.teachers[0]
        rows = [['教师编号', '主讲教师', '时间地点'],
                [teacher.pk, teacher.name, '第1-4周 单周 星期一 上1,上2'],
                [None, '张乙', '第1-2周 星期二 下5,下6'],
                [None, teacher.name, '无法解析'],
                [9999, teacher.name, '第1-2周 星期三 上3,上4']]
        before = OperationLog.objects.count()
        result = self.timetable(rows, preview='true')
        self.assertEqual(result.status_code, 200, result.data)
        teacher.refresh_from_db()
        self.assertEqual(teacher.unavailable_times, '')
        self.assertEqual(OperationLog.objects.count(), before)
        self.assertEqual(result.data['unknownTeacherNames'], ['张乙'])
        self.assertEqual(len(result.data['warnings']), 2)
        matched = next(row for row in result.data['rows'] if row['teacherId'] == teacher.pk)
        self.assertEqual(matched['entries'], ['2026-11-02 08:00-10:00', '2026-11-16 08:00-10:00'])
        confirmed = self.timetable(rows, previewToken=result.data['previewToken'])
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        payload, _ = build_algorithm_input('pre', rules=rules(campus_scope='创新港'))
        busy = next(t['available_time'] for t in payload['teachers'] if t['id'] == teacher.pk)
        self.assertTrue(any('2026-11-02 00:00-2026-11-02 12:00' == text for text in busy), busy)
        again = self.timetable(rows, preview='true')
        self.assertEqual(again.data['duplicateCount'], 2)
        self.assertEqual(self.timetable(rows).data['updatedTeachers'], 0)

    def test_timetable_rejects_stale_preview_and_empty_parsing(self):
        teacher = self.teachers[0]
        rows = [['主讲教师', '时间地点'], [teacher.name, '第1-2周 星期一 上1,上2']]
        preview = self.timetable(rows, preview='true')
        teacher.unavailable_times = '2026-11-03 08:00-12:00'; teacher.save()
        self.assertEqual(self.timetable(rows, previewToken=preview.data['previewToken']).status_code, 409)
        bad = self.timetable([['主讲教师', '时间地点'], [teacher.name, 'bad']])
        self.assertEqual(bad.status_code, 400)
        self.assertIn('第 2 行', bad.data['warnings'][0])

    def test_both_export_channels_label_campus_batch(self):
        from api.export_word import export_schedule_word
        from api.services.export_excel import build_schedule_workbook
        version = self.generate('创新港', 'export-campus')
        workbook = build_schedule_workbook(version, 'pre')
        self.assertEqual(workbook['批次信息']['B1'].value, '创新港')
        document = export_schedule_word(version)
        self.assertIn('创新港', document.paragraphs[0].text)
