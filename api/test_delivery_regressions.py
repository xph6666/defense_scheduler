"""Behavior regressions from the 2026-10-26 delivery audit; synthetic data only."""
import json
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .mentor_colors import build_mentor_color_map, build_mentor_color_pairs
from .models import Group, Room, ScheduleVersion, Student, Teacher
from .tests import make_xlsx_upload


class StudentImportDeliveryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('delivery-import-admin', is_staff=True))

    def upload(self, rows, preview=False):
        return self.client.post('/api/students/import_data/', {
            'file': make_xlsx_upload('synthetic-students.xlsx', rows),
            'preview': str(preview).lower(), 'defenseTypes': json.dumps(['中期答辩']),
        }, format='multipart')

    def test_location_headings_preserve_campus_in_preview_and_saved_student(self):
        for index, heading in enumerate(['中期答辩地点（创新港/兴庆）',
                '中期答辩地点 ( 创新港 / 兴庆 )', '正式答辩地点（兴庆、创新港）']):
            with self.subTest(heading=heading):
                number = f'CAMPUS-{index}'
                rows = [['学号', '姓名', '导师姓名', heading], [number, f'合成学生{index}', '合成导师', '兴庆']]
                before = Student.objects.count()
                preview = self.upload(rows, preview=True)
                self.assertTrue(preview.data['canImport'], preview.data)
                self.assertEqual(preview.data['rows'][0]['values']['campus'], '兴庆')
                self.assertEqual(Student.objects.count(), before)
                response = self.upload(rows)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(Student.objects.get(student_no=number).campus, '兴庆')

    def test_json_participation_preserves_all_types_and_merges_existing_valid_types(self):
        student = Student.objects.create(name='合成学生', student_no='JSON-01', campus='兴庆', defense_types=['中期答辩'])
        rows = [['学号', '姓名', '校区', '参与答辩类型'],
                ['JSON-01', '合成学生', '兴庆', '["预答辩","正式答辩","预答辩"]']]
        preview = self.upload(rows, preview=True)
        self.assertTrue(preview.data['canImport'], preview.data)
        self.assertEqual(preview.data['rows'][0]['values']['defenseTypes'], ['中期答辩', '预答辩', '正式答辩'])
        student.refresh_from_db()
        self.assertEqual(student.defense_types, ['中期答辩'])
        self.assertEqual(self.upload(rows).status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.defense_types, ['中期答辩', '预答辩', '正式答辩'])

    def test_multiple_location_columns_are_not_silently_chosen(self):
        rows = [['学号', '姓名', '校区', '中期答辩地点（创新港/兴庆）'],
                ['AMBIGUOUS', '合成学生', '创新港', '兴庆']]
        for preview in (True, False):
            response = self.upload(rows, preview=preview)
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Student.objects.exists())

    def test_bad_json_or_unknown_participation_rejects_entire_upload(self):
        for bad in ['["预答辩",', '["未知环节"]', '{"预答辩":true}', '[1]', '预答辩、未知环节']:
            with self.subTest(value=bad):
                rows = [['学号', '姓名', '校区', '参与环节'],
                        ['GOOD', '正确行', '兴庆', '正式答辩'], ['BAD', '错误行', '兴庆', bad]]
                preview = self.upload(rows, preview=True)
                self.assertFalse(preview.data['canImport'], preview.data)
                response = self.upload(rows)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(Student.objects.exists())

    def test_direct_student_api_rejects_non_array_and_unknown_types(self):
        for value in ['正式答辩', ['未知环节'], [1]]:
            response = self.client.post('/api/students/', {
                'name': '合成学生', 'studentNo': 'DIRECT', 'campus': '兴庆', 'defenseTypes': value,
            }, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Student.objects.exists())


class FormalSingleGroupDeliveryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('delivery-formal-admin', is_staff=True))
        people = [Teacher.objects.create(name=f'合成教师{index}', title='教授', college='软件学院',
            is_software_teacher=True, roles=['主席', '组长', '普通专家', '秘书'],
            available_types=['正式答辩']) for index in range(1, 17)]
        self.mentor = people[0]
        for index in range(6):
            Student.objects.create(name=f'合成学生{index}', student_no=f'FORMAL-{index}',
                mentor=self.mentor, mentor_name=self.mentor.name, campus='创新港', defense_types=['正式答辩'])
        Room.objects.create(name='合成教室', campus='创新港', capacity=30,
                            available_times='2026-10-12 09:00-12:00')

    def generate(self, seed, avoid=False):
        return self.client.post('/api/schedule/generate/', {'rules': {
            'defense_type': 'formal', 'policy_version': 2, 'start_date': '2026-10-12',
            'end_date': '2026-10-12', 'preserve_pre_defense_groups': False,
            'random_seed': seed, 'avoid_supervisor': avoid,
        }}, format='json')

    def test_all_reproducing_seeds_keep_required_mentor_and_can_publish(self):
        for seed in [20261023, 101, 1, 2]:
            with self.subTest(seed=seed):
                response = self.generate(seed)
                self.assertEqual(response.status_code, 200, response.data)
                data = response.data.get('data', response.data)
                self.assertEqual(len(data['groups']), 1)
                group = data['groups'][0]
                reviewers = {group['chairId'], *(teacher['id'] for teacher in group['teachers'])}
                self.assertIn(self.mentor.pk, reviewers)
                self.assertEqual(len(reviewers), 5)
                self.assertFalse([item for item in data['conflicts'] if item['level'] == 'error'], data['conflicts'])
                published = self.client.post('/api/schedule/publish/', {
                    'version_id': data['versionId'], 'expected_revision': data['revision'],
                }, format='json')
                self.assertEqual(published.status_code, 200, published.data)

    def test_avoidance_still_rejects_impossible_single_group(self):
        response = self.generate(20261023, avoid=True)
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data.get('data', response.data)
        self.assertTrue([item for item in data['conflicts'] if item['level'] == 'error'])
        published = self.client.post('/api/schedule/publish/', {
            'version_id': data['versionId'], 'expected_revision': data['revision'],
        }, format='json')
        self.assertEqual(published.status_code, 400)


class MentorAssignmentDeliveryTests(SimpleTestCase):
    def test_colliding_mentors_get_distinct_colors_in_actual_group_map(self):
        students = [SimpleNamespace(mentor_name=name) for name in ['导师001', '导师023']]
        groups = [SimpleNamespace(students=SimpleNamespace(all=lambda: students))]
        colors = build_mentor_color_map(groups)
        self.assertEqual(len(set(colors.values())), 2)

    def test_more_than_palette_size_is_unique_and_order_independent(self):
        names = [f'合成导师{index:03}' for index in range(160)] + ['导师😀', '导师𠀀', '导师001', '导师023']
        pairs = build_mentor_color_pairs(names)
        self.assertEqual(pairs, build_mentor_color_pairs(reversed(names)))
        for variant in ['light', 'dark']:
            self.assertEqual(len({pair[variant] for pair in pairs.values()}), len(names))
        self.assertIn({'light': 'DFE5CA', 'dark': '46521C'}, pairs.values())


class MentorExportDeliveryTests(TestCase):
    def test_excel_word_and_frozen_history_share_collision_free_assignment(self):
        from .export_word import export_schedule_word
        from .schedule_integrity import capture_export_groups
        from .services.export_excel import build_schedule_workbook

        version = ScheduleVersion.objects.create(defense_type='mid', rules_snapshot={'include_remarks': True})
        group = Group.objects.create(schedule_version=version, group_id='G1', campus='兴庆', time='2031-07-14 09:00-12:00')
        names = ['导师001', '导师023']
        student_names = ['合成学生甲', '合成学生乙']
        for name, student_name in zip(names, student_names):
            mentor = Teacher.objects.create(name=name, title='教授')
            group.students.add(Student.objects.create(name=student_name, mentor=mentor, mentor_name=name))
        version.export_snapshot = capture_export_groups(version)
        version.save(update_fields=['export_snapshot'])
        expected = {name: pair['dark'] for name, pair in build_mentor_color_pairs(names).items()}
        Teacher.objects.filter(name='导师001').update(name='当前资料已改名')
        workbook = build_schedule_workbook(version, 'mid')
        sheet = workbook['组G1']
        excel_colors = {cell.value: cell.font.color.rgb[-6:] for row in sheet for cell in row
                        if cell.value in names + student_names and cell.font.color and cell.font.color.type == 'rgb'}
        doc = export_schedule_word(version, '中期答辩')
        runs = [run for table in doc.tables for row in table.rows for cell in row.cells for paragraph in cell.paragraphs for run in paragraph.runs]
        word_colors = {run.text: str(run.font.color.rgb) for run in runs if run.font.color.rgb}
        for name, student_name in zip(names, student_names):
            self.assertEqual(excel_colors[name], expected[name])
            self.assertEqual(excel_colors[student_name], expected[name])
            self.assertEqual(word_colors[name], expected[name])
            self.assertEqual(word_colors[student_name], expected[name])
