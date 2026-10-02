"""V2 reference identities, migration preservation and documented rule bounds."""
from datetime import date, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.db import connection
from django.test import TestCase

from .admin import StudentReferenceForm
from .models import RuleConfig, ScheduleVersion, Student, Teacher
from .serializers import RuleConfigSerializer, StudentSerializer, TeacherSerializer, default_rule_config
from .services.reference_data import ReferenceDataError, rename_teacher


class ReferenceIdentityV2Tests(TestCase):
    def setUp(self):
        self.mentor = Teacher.objects.create(name='导师甲', college='软件学院', title='教授')
        self.secretary = Teacher.objects.create(name='秘书乙', title='讲师')

    def save_student(self, payload, instance=None):
        serializer = StudentSerializer(instance, data=payload, partial=instance is not None)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer.save()

    def test_teacher_flags_keep_existing_records_enabled(self):
        data = TeacherSerializer(self.mentor).data
        self.assertTrue(data['isActive'])
        self.assertTrue(data['memberEligible'])
        self.assertTrue(data['isSoftwareTeacher'])
        serializer = TeacherSerializer(self.mentor, data={'isActive': False, 'memberEligible': False}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        teacher = serializer.save()
        self.assertFalse(teacher.is_active)
        self.assertFalse(teacher.member_eligible)

    def test_external_college_name_does_not_imply_software_teacher_without_flag(self):
        self.mentor.is_external = True
        self.assertFalse(TeacherSerializer(self.mentor).data['isSoftwareTeacher'])
        self.mentor.is_software_teacher = True
        self.assertTrue(TeacherSerializer(self.mentor).data['isSoftwareTeacher'])

    def test_id_write_populates_name_fields(self):
        student = self.save_student({'name': '学生一', 'mentorId': self.mentor.pk, 'secretaryId': self.secretary.pk})
        self.assertEqual(student.mentor_name, self.mentor.name)
        self.assertEqual(student.secretary_name, self.secretary.name)
        self.assertEqual(StudentSerializer(student).data['secretaryId'], self.secretary.pk)

    def test_legacy_name_import_binds_existing_teacher(self):
        student = self.save_student({'name': '学生一', 'mentorName': ' 导师甲 ', 'secretaryName': '秘书乙'})
        self.assertEqual(student.mentor_id, self.mentor.pk)
        self.assertEqual(student.bound_secretary_id, self.secretary.pk)

    def test_unresolved_name_remains_compatible_and_new_teacher_links_it(self):
        student = self.save_student({'name': '学生一', 'mentorName': '待录入导师'})
        self.assertIsNone(student.mentor_id)
        self.assertEqual(student.mentor_name, '待录入导师')
        serializer = TeacherSerializer(data={'name': '待录入导师', 'title': '教授'})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        teacher = serializer.save()
        student.refresh_from_db()
        self.assertEqual(student.mentor_id, teacher.pk)

    def test_id_name_conflict_is_rejected_before_save(self):
        serializer = StudentSerializer(data={'name': '学生一', 'mentorId': self.mentor.pk, 'mentorName': '其他导师'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('mentorName', serializer.errors)
        self.assertFalse(Student.objects.exists())

    def test_name_only_update_rebinds_and_explicit_null_clears(self):
        student = self.save_student({'name': '学生一', 'mentorId': self.mentor.pk})
        self.save_student({'mentorName': self.secretary.name}, student)
        self.assertEqual(student.mentor_id, self.secretary.pk)
        self.save_student({'mentorId': None}, student)
        self.assertIsNone(student.mentor_id)
        self.assertEqual(student.mentor_name, '')

    def test_unrelated_partial_update_preserves_relationship(self):
        student = self.save_student({'name': '学生一', 'mentorId': self.mentor.pk})
        self.save_student({'remark': '保留关系'}, student)
        self.assertEqual(student.mentor_id, self.mentor.pk)

    def test_read_uses_current_fk_name_when_legacy_text_is_stale(self):
        student = Student.objects.create(name='学生一', mentor=self.mentor, mentor_name='旧名字',
                                         bound_secretary=self.secretary, secretary_name='旧秘书')
        data = StudentSerializer(student).data
        self.assertEqual(data['mentorName'], self.mentor.name)
        self.assertEqual(data['secretaryName'], self.secretary.name)

    def test_teacher_rename_updates_links_and_exact_exclusion_tokens(self):
        student = Student.objects.create(name='学生一', mentor=self.mentor, mentor_name=self.mentor.name,
                                         bound_secretary=self.mentor, secretary_name=self.mentor.name)
        legacy = Student.objects.create(name='学生二', mentor_name=self.mentor.name)
        other = Teacher.objects.create(name='评委', title='教授', avoid_teacher_names='导师甲，导师甲乙; 导师甲')
        snapshot = {'students': [{'mentor_name': '导师甲'}]}
        version = ScheduleVersion.objects.create(defense_type='pre', result_snapshot=snapshot)
        serializer = TeacherSerializer(self.mentor, data={'name': '导师丙'}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        student.refresh_from_db()
        legacy.refresh_from_db()
        other.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(student.mentor_name, '导师丙')
        self.assertEqual(student.secretary_name, '导师丙')
        self.assertEqual(legacy.mentor_id, self.mentor.pk)
        self.assertEqual(other.avoid_teacher_names, '导师丙，导师甲乙; 导师丙')
        self.assertEqual(version.result_snapshot, snapshot)

    def test_failed_safe_rename_keeps_existing_references(self):
        student = Student.objects.create(name='学生一', mentor=self.mentor, mentor_name=self.mentor.name)
        with self.assertRaises(ReferenceDataError):
            rename_teacher(self.mentor, self.secretary.name)
        student.refresh_from_db()
        self.mentor.refresh_from_db()
        self.assertEqual(student.mentor_name, '导师甲')
        self.assertEqual(self.mentor.name, '导师甲')

    def test_teacher_delete_keeps_legacy_names_and_nulls_ids(self):
        student = self.save_student({'name': '学生一', 'mentorId': self.mentor.pk, 'secretaryId': self.mentor.pk})
        self.mentor.delete()
        student.refresh_from_db()
        self.assertIsNone(student.mentor_id)
        self.assertIsNone(student.bound_secretary_id)
        self.assertEqual(StudentSerializer(student).data['mentorName'], '导师甲')

    def test_admin_fk_choice_populates_legacy_name(self):
        form = StudentReferenceForm(data={'name': '学生一', 'student_type': '学硕', 'campus': '创新港',
                                         'mentor': self.mentor.pk, 'mentor_name': '',
                                         'defense_types': '["预答辩"]', 'secretary_name': ''})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().mentor_name, self.mentor.name)

    def test_source_pre_version_uses_stable_identity(self):
        pre = ScheduleVersion.objects.create(defense_type='pre')
        formal = ScheduleVersion.objects.create(defense_type='formal', source_pre_version=pre)
        pre.delete()
        formal.refresh_from_db()
        self.assertIsNone(formal.source_pre_version_id)


class RuleDefaultsV2Tests(TestCase):
    def test_each_scenario_matches_documented_counts_and_today(self):
        today = date(2026, 10, 2)
        with patch('api.serializers.timezone.localdate', return_value=today):
            for kind, target, minimum, maximum, expert in (('pre', 6, 4, 8, 4), ('formal', 6, 4, 8, 5), ('mid', 12, 10, 13, 5)):
                config = default_rule_config(kind)
                self.assertEqual(config['studentCount'], {'target': target, 'min': minimum, 'max': maximum})
                self.assertEqual(config['expertCount']['target'], expert)
                self.assertEqual(config['startDate'], today.isoformat())
                self.assertEqual(config['endDate'], (today + timedelta(days=10)).isoformat())
                self.assertEqual(config['mentorAvoidance'], kind == 'formal')
                serializer = RuleConfigSerializer(data={'defense_type': kind})
                self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_defaults_do_not_share_mutable_nested_sections(self):
        first = default_rule_config('pre')
        first['studentCount']['target'] = 1
        self.assertEqual(default_rule_config('pre')['studentCount']['target'], 6)

    def test_partial_rule_update_preserves_custom_dates_and_bounds(self):
        rules = RuleConfig.objects.create(defense_type='pre', config={**default_rule_config('pre'), 'endDate': '2030-01-01'})
        serializer = RuleConfigSerializer(rules, data={'studentCount': {'target': 7}}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()
        self.assertEqual(updated.config['studentCount'], {'target': 7, 'min': 4, 'max': 8})
        self.assertEqual(updated.config['endDate'], '2030-01-01')

    def test_expert_bounds_cannot_bypass_documented_headcounts(self):
        for kind, count in (('pre', {'target': 3, 'min': 3}), ('mid', {'target': 4, 'min': 4}),
                            ('formal', {'target': 6, 'min': 5}), ('formal', {'target': 5, 'min': 4})):
            serializer = RuleConfigSerializer(data={'defense_type': kind, 'expertCount': count})
            self.assertFalse(serializer.is_valid())
            self.assertIn('expertCount', serializer.errors)

    def test_invalid_types_and_role_floor_return_validation_errors(self):
        for payload in ({'studentCount': {'target': 6.5}}, {'expertCount': 'bad'},
                        {'roleQualification': {'chairmanMinTitle': '副教授'}},
                        {'secretaryCount': 0}, {'mentorAvoidance': True}, {'courseHalfDayBlocking': False}):
            serializer = RuleConfigSerializer(data={'defense_type': 'pre', **payload})
            self.assertFalse(serializer.is_valid())

    def test_rule_payload_must_be_an_object(self):
        serializer = RuleConfigSerializer(data=['pre'])
        self.assertFalse(serializer.is_valid())
        self.assertIn('config', serializer.errors)


class DataMigrationV2Tests(TestCase):
    def test_migration_matches_exact_names_and_leaves_ambiguous_normalization_unresolved(self):
        teacher = Teacher.objects.create(name='导师甲', title='教授')
        Teacher.objects.create(name=' 导师甲', title='教授')
        exact = Student.objects.create(name='学生一', mentor_name='导师甲')
        ambiguous = Student.objects.create(name='学生二', mentor_name=' 导师甲 ')
        migration = import_module('api.migrations.0009_reference_data_v2')
        migration.upgrade_reference_data(apps, SimpleNamespace(connection=connection))
        exact.refresh_from_db()
        ambiguous.refresh_from_db()
        self.assertEqual(exact.mentor_id, teacher.pk)
        self.assertIsNone(ambiguous.mentor_id)

    def test_migration_resolves_names_and_preserves_unknown_names_and_custom_configuration(self):
        teacher = Teacher.objects.create(name='导师甲', title='教授')
        linked = Student.objects.create(name='学生一', mentor_name=' 导师甲 ', secretary_name='导师甲')
        unresolved = Student.objects.create(name='学生二', mentor_name='未知教师')
        legacy = RuleConfig.objects.create(defense_type='mid', config={
            'startDate': '2025-05-10', 'endDate': '2025-05-20',
            'studentCount': {'target': 5, 'min': 3, 'max': 8}, 'expertCount': {'target': 2, 'min': 1}})
        custom = RuleConfig.objects.create(defense_type='formal', config={
            'startDate': '2030-05-01', 'endDate': '2030-05-20', 'mentorAvoidance': False,
            'studentCount': {'target': 7, 'min': 4, 'max': 9}, 'expertCount': {'target': 8, 'min': 3}})
        migration = import_module('api.migrations.0009_reference_data_v2')
        migration.upgrade_reference_data(apps, SimpleNamespace(connection=connection))
        linked.refresh_from_db()
        unresolved.refresh_from_db()
        legacy.refresh_from_db()
        custom.refresh_from_db()
        self.assertEqual(linked.mentor_id, teacher.pk)
        self.assertEqual(linked.bound_secretary_id, teacher.pk)
        self.assertEqual(linked.mentor_name, teacher.name)
        self.assertIsNone(unresolved.mentor_id)
        self.assertEqual(unresolved.mentor_name, '未知教师')
        self.assertEqual(legacy.config['studentCount'], {'target': 12, 'min': 10, 'max': 13})
        self.assertEqual(legacy.config['expertCount']['min'], 5)
        self.assertEqual(custom.config['studentCount']['target'], 7)
        self.assertEqual(custom.config['startDate'], '2030-05-01')
        self.assertFalse(custom.config['mentorAvoidance'])
        self.assertEqual(custom.config['expertCount']['target'], 5)
