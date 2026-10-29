"""Synthetic coverage for a joint student/mentor batch import."""
import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, SimpleTestCase
from rest_framework.test import APIClient

from scheduling.policies import teacher_can_role, secretary_is_qualified
from .models import Teacher, Student, OperationLog, ScheduleVersion, ScheduleWriteLock
from .tests import make_xlsx_upload


class CohortImportTests(TestCase):
    def test_confirmed_wang_fei_affiliations_match_preview_and_students(self):
        self.teachers[1][0] = '王飞'
        self.students[1][2] = '王飞'
        self.students[2][2] = '王飞（软）'
        self.students[3][2] = '王飞（软）'
        preview = self.post(preview=True)
        self.assertEqual(preview.status_code, 200, preview.data)
        staff = {t['name']: t for t in preview.data['teachers']}
        self.assertTrue(staff['王飞']['isExternal'])
        self.assertFalse(staff['王飞（软）']['isExternal'])
        self.assertEqual(preview.data['stats']['externalMentors'], 1)
        for student in preview.data['students']:
            self.assertEqual(student['externalMentor'], student['mentorName'] == '王飞')

    def test_legacy_chair_read_exposes_eligibility_without_rewriting_roles(self):
        teacher=Teacher.objects.create(name='旧名单组长',title='教授',roles=['主席'])
        response=self.client.get(f'/api/teachers/{teacher.pk}/')
        self.assertEqual(response.status_code,200,response.data)
        self.assertIn('普通专家',response.data['roles'])
        teacher.refresh_from_db()
        self.assertEqual(teacher.roles,['主席'])
        teacher.member_eligible=False
        teacher.save(update_fields=['member_eligible'])
        response=self.client.get(f'/api/teachers/{teacher.pk}/')
        self.assertNotIn('普通专家',response.data['roles'])

    def test_designated_chair_import_also_declares_expert_eligibility(self):
        self.teachers[1][-1]='组长'
        preview=self.post(preview=True)
        self.assertEqual(preview.status_code,200,preview.data)
        chair=next(t for t in preview.data['teachers'] if t['name']=='校内导师')
        self.assertIn('普通专家',chair['roles'])
        self.assertEqual(self.post().status_code,200)
        teacher=Teacher.objects.get(name='校内导师')
        self.assertIn('普通专家',teacher.roles)
        self.assertTrue(teacher_can_role(teacher,'expert'))

    def test_designated_chair_import_preserves_member_exclusion(self):
        self.teachers[1][-1]='组长'
        Teacher.objects.create(name='校内导师',title='教授',roles=['组长','主席'],member_eligible=False)
        self.assertEqual(self.post().status_code,200)
        teacher=Teacher.objects.get(name='校内导师')
        self.assertFalse(teacher.member_eligible)
        self.assertFalse(teacher_can_role(teacher,'expert'))
        self.assertNotIn('普通专家',teacher.roles)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(username='cohort-admin', is_staff=True))
        self.teachers = [['姓名', '所在学院', '职称', ''],
                         ['校内导师', '软件学院', '教授', '组长、组员'],
                         ['指定秘书', '软件学院', '助理教授', '秘书']]
        self.students = [['学号', '姓名', '导师', '答辩地点'],
                         ['S001', '学生甲', '校内导师', '创新港'],
                         ['S002', '学生乙', '外院导师甲', '兴庆'],
                         ['S003', '学生丙', '外院导师甲', '兴庆']]

    def post(self, preview=False, sheets=None, **options):
        # Preview/confirm upload the same file. Regenerating XLSX changes ZIP
        # timestamps across two-second boundaries and invalidates its hash.
        if not hasattr(self,'_file_bytes'):self._file_bytes={}
        def upload(name,rows):
            key=(name,json.dumps(rows,ensure_ascii=False))
            if key not in self._file_bytes:self._file_bytes[key]=make_xlsx_upload(name,rows).read()
            return SimpleUploadedFile(name,self._file_bytes[key])
        uploads = [upload(f'students-{index}.xlsx', rows)
                   for index, rows in enumerate(sheets or [self.students])]
        return self.client.post('/api/students/import-cohort/', {
            'teacherFile': upload('software.xlsx', self.teachers),
            'studentFiles': uploads, 'defenseTypes': json.dumps(['预答辩', '正式答辩']),
            'preview': str(preview).lower(), **options,
        }, format='multipart')

    def test_preview_shows_deduplicated_external_mentors_without_any_writes(self):
        version = ScheduleVersion.objects.create(defense_type='pre', is_current=True)
        revision = ScheduleWriteLock.objects.get(pk=1).revision
        response = self.post(preview=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['canImport'], response.data)
        self.assertEqual(response.data['stats']['externalMentors'], 1)
        self.assertEqual(response.data['stats']['students'], 3)
        external = next(item for item in response.data['teachers'] if item['name'] == '外院导师甲')
        self.assertEqual(external['title'], '外院导师（职称待确认）')
        self.assertEqual(external['roles'], ['普通专家'])
        self.assertTrue(external['expertOnly'])
        self.assertEqual(external['studentCount'], 2)
        self.assertEqual(Teacher.objects.count(), 0)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(OperationLog.objects.count(), 0)
        version.refresh_from_db()
        self.assertEqual(version.revision, 0)
        self.assertEqual(ScheduleWriteLock.objects.get(pk=1).revision, revision)

    def test_confirm_links_students_and_repeat_import_does_not_duplicate_people(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Teacher.objects.count(), 3)
        self.assertEqual(Student.objects.count(), 3)
        external = Teacher.objects.get(name='外院导师甲')
        self.assertTrue(external.is_external)
        self.assertTrue(external.expert_only)
        self.assertFalse(external.is_software_teacher)
        self.assertEqual(external.roles, ['普通专家'])
        self.assertEqual(Student.objects.get(student_no='S002').mentor_id, external.pk)
        self.assertEqual(Teacher.objects.get(name='指定秘书').roles, ['秘书'])
        ids = list(Student.objects.order_by('student_no').values_list('pk', flat=True))
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(Teacher.objects.count(), 3)
        self.assertEqual(list(Student.objects.order_by('student_no').values_list('pk', flat=True)), ids)
        self.assertEqual(OperationLog.objects.count(), 2)

    def test_existing_known_title_busy_times_and_inactive_state_are_preserved(self):
        existing = Teacher.objects.create(name='外院导师甲', title='教授', is_active=False,
                                         unavailable_times='2031-07-14 09:00-12:00', roles=['主席'])
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        existing.refresh_from_db()
        self.assertEqual(existing.title, '教授')
        self.assertFalse(existing.is_active)
        self.assertEqual(existing.unavailable_times, '2031-07-14 09:00-12:00')
        self.assertEqual(existing.roles, ['普通专家'])
        self.assertTrue(existing.expert_only)

    def test_multiple_student_files_merge_identical_students_but_reject_conflicting_ids(self):
        extra = [self.students[0], self.students[2], ['S004', '学生丁', '另一外院导师', '创新港']]
        response = self.post(sheets=[self.students, extra])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Student.objects.count(), 4)
        self.assertEqual(Teacher.objects.count(), 4)
        conflicting = [self.students[0], ['S005', '学生戊', '校内导师', '兴庆'],
                       ['S001', '不是学生甲', '校内导师', '创新港']]
        response = self.post(sheets=[self.students, conflicting])
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Student.objects.filter(student_no='S005').exists())
        self.assertEqual(Student.objects.get(student_no='S001').name, '学生甲')

    def test_missing_campus_blocks_whole_batch_and_can_be_corrected_in_preview(self):
        self.students[2][-1] = ''
        response = self.post(preview=True)
        self.assertFalse(response.data['canImport'])
        self.assertEqual(len(response.data['errors']), 1, response.data['errors'])
        row = next(item for item in response.data['students'] if item['studentNo'] == 'S002')
        self.assertTrue(row['key'])
        failed = self.post()
        self.assertEqual(failed.status_code, 400)
        self.assertFalse(Teacher.objects.exists())
        self.assertFalse(Student.objects.exists())
        fixed = self.post(corrections=json.dumps({row['key']: {'campus': '兴庆'}}))
        self.assertEqual(fixed.status_code, 200, fixed.data)
        self.assertEqual(Student.objects.get(student_no='S002').campus, '兴庆')

    def test_nonparticipants_keep_remarks_without_campus_or_mentor_requirements(self):
        self.students[0].append('备注')
        self.students[1].append('')
        self.students[2] = ['S002', '学生乙', '不参排导师', '', '在外院答辩-电子学院']
        self.students[3] = ['S003', '学生丙', '', '', '已转博']
        existing = Student.objects.create(student_no='S002', name='学生乙', campus='兴庆',
                                          defense_types=['预答辩', '正式答辩'])
        preview = self.post(preview=True, campus='创新港')
        self.assertTrue(preview.data['canImport'], preview.data)
        self.assertEqual(preview.data['stats']['students'], 1)
        self.assertEqual(preview.data['stats']['excludedStudents'], 2)
        self.assertEqual(len(preview.data['excludedStudents']), 2)
        self.assertFalse(any(t['name'] == '不参排导师' for t in preview.data['teachers']))
        existing.refresh_from_db()
        self.assertEqual(existing.defense_types, ['预答辩', '正式答辩'])
        self.assertEqual(self.post(campus='创新港').status_code, 200)
        self.assertEqual(Student.objects.count(), 3)
        for number in ['S002', 'S003']:
            student = Student.objects.get(student_no=number)
            self.assertEqual(student.defense_types, [])
            self.assertEqual(student.campus, '')
            self.assertTrue(student.remark)
        from .services.scheduling_input import build_algorithm_input
        payload, notices = build_algorithm_input('pre')
        self.assertEqual(len(payload['students']), 1)
        self.assertFalse(any(n['type'] == 'student_defense_type_missing' for n in notices))

    def test_ambiguous_remarks_do_not_exclude_students_or_fill_campus(self):
        self.students[0].append('备注')
        for row, remark in zip(self.students[1:], ['未转博', '申请休学待审批', '正常答辩']):
            row[-1] = ''
            row.append(remark)
        preview = self.post(preview=True)
        self.assertFalse(preview.data['canImport'])
        self.assertEqual(preview.data['stats'].get('excludedStudents', 0), 0)

    def test_participation_conflict_between_files_blocks_entire_import(self):
        self.students[0].append('备注')
        for row in self.students[1:]:
            row.append('')
        extra = [self.students[0], ['S001', '学生甲', '校内导师', '', '休学']]
        response = self.post(sheets=[self.students, extra])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Student.objects.exists())

    def test_missing_mentor_or_wrong_campus_are_not_guessed(self):
        self.students[1][2] = ''
        self.students[2][-1] = '创新港/线上'
        response = self.post(preview=True)
        self.assertFalse(response.data['canImport'])
        self.assertTrue(any('mentorName' in item['errors'] for item in response.data['errors']))
        self.assertTrue(any('campus' in item['errors'] for item in response.data['errors']))

    def test_non_admin_cannot_import_and_cannot_promote_expert_only_teacher(self):
        imported = self.post()
        self.assertEqual(imported.status_code, 200, imported.data)
        external = Teacher.objects.get(name='外院导师甲')
        promoted = self.client.patch(f'/api/teachers/{external.pk}/', {'roles': ['主席']}, format='json')
        self.assertEqual(promoted.status_code, 400, promoted.data)
        promoted = self.client.put(f'/api/teachers/{external.pk}/', {
            'name': external.name, 'title': '教授', 'roles': ['主席'],
        }, format='json')
        self.assertEqual(promoted.status_code, 400, promoted.data)
        self.client.force_authenticate(User.objects.create_user(username='cohort-reader'))
        self.assertEqual(self.post(preview=True).status_code, 403)

    def test_preview_corrections_are_bound_to_the_original_file_and_rows(self):
        first = self.post(preview=True)
        key = first.data['students'][0]['key']
        self.students[1][1] = '已更改的学生名'
        response = self.post(corrections=json.dumps({key: {'campus': '兴庆'}}))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Teacher.objects.exists())

    def test_software_roster_preserves_explicit_inactive_and_recurring_busy_fields(self):
        self.teachers[0].extend(['是否启用', '不可用时间'])
        self.teachers[1].extend(['否', '周一上午'])
        self.teachers[2].extend(['是', ''])
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        teacher = Teacher.objects.get(name='校内导师')
        self.assertFalse(teacher.is_active)
        self.assertEqual(teacher.unavailable_times, '周一上午')


class ExpertOnlyPolicyTests(SimpleTestCase):
    def test_chair_can_review_as_expert_unless_explicitly_excluded(self):
        for roles in (['组长'],['主席'],['chair'],['组长','主席']):
            with self.subTest(roles=roles):
                self.assertTrue(teacher_can_role({'roles':roles},'expert'))
                self.assertFalse(teacher_can_role({'roles':roles,'memberEligible':False},'expert'))
                self.assertFalse(teacher_can_role({'roles':roles,'is_active':False},'expert'))

    def test_expert_only_flag_overrides_empty_or_forged_roles_and_known_title(self):
        for roles in ([], ['主席', '秘书', '普通专家']):
            raw = {'name': '外院合成导师', 'title': '教授', 'roles': roles, 'expert_only': True}
            self.assertTrue(teacher_can_role(raw, 'expert'))
            self.assertFalse(teacher_can_role(raw, 'chair'))
            self.assertFalse(secretary_is_qualified(raw, '讲师'))
        self.assertTrue(teacher_can_role({'title': '教授', 'roles': ['主席']}, 'chair'))
