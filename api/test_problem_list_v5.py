"""Regressions for cohort coverage, cross-stage reservations and panel balance."""
from collections import Counter
from types import SimpleNamespace

from django.test import TestCase, SimpleTestCase

from api.models import Group, ScheduleVersion, Student, Teacher
from api.schedule_views import ScheduleViewSet
from api.services.campus_batches import cross_batch_conflicts
from api.services.rules import normalize_schedule_rules
from api.services.scheduling_input import build_algorithm_input


def rules(stage='formal', **changes):
    return normalize_schedule_rules(dict(policy_version=4, defense_type=stage,
        start_date='2026-11-16', end_date='2026-11-20', **changes))


class CoverageAndReservationTests(TestCase):
    def test_formal_rotation_keeps_mentor_identity_without_requiring_attendance(self):
        mentor = Teacher.objects.create(name='仅预答辩导师', title='教授', available_types=['预答辩'])
        Student.objects.create(name='回避学生', mentor=mentor, mentor_name=mentor.name,
            defense_types=['正式答辩'])
        config = {**rules(), 'formal_rotation': True}
        payload, notices = build_algorithm_input('formal', rules=config)
        self.assertEqual(payload['students'][0]['supervisor_id'], mentor.pk)
        self.assertNotIn(mentor.pk, {t['id'] for t in payload['teachers']})
        self.assertFalse(any(n['type'] == 'mentor_unavailable_for_defense' for n in notices))

    def test_confirmed_pre_roster_also_includes_explicit_formal_students(self):
        pre = ScheduleVersion.objects.create(defense_type='pre', status='published')
        inherited = Student.objects.create(name='来源学生', defense_types=['预答辩'])
        extra = Student.objects.create(name='正式新增学生', defense_types=['正式答辩'])
        group = Group.objects.create(schedule_version=pre, group_id='G001', campus='创新港', time='')
        group.students.add(inherited)
        payload, _ = build_algorithm_input('formal', rules=rules(use_confirmed_pre_students=True))
        self.assertEqual({s['id'] for s in payload['students']}, {inherited.pk, extra.pk})

    def test_summary_includes_students_added_after_generation(self):
        original = Student.objects.create(name='原学生', defense_types=['正式答辩'])
        extra = Student.objects.create(name='新增学生', defense_types=['正式答辩'])
        version = ScheduleVersion.objects.create(defense_type='formal', rules_snapshot=rules(),
            input_snapshot={'students': [{'id': original.pk, 'name': original.name}]})
        groups = [dict(students=[{'id': original.pk}], teachers=[], date='2026-11-16', timeRange='09:00-12:00')]
        result = ScheduleViewSet()._allocation_summary(version, groups, [])
        self.assertEqual(result['allocationStatus'], 'partial')
        self.assertEqual(result['totalStudents'], 2)
        self.assertEqual([s['id'] for s in result['unassignedStudents']], [extra.pk])

    def test_summary_does_not_count_students_without_a_valid_time(self):
        student = Student.objects.create(name='未定时间学生', defense_types=['正式答辩'])
        version = ScheduleVersion.objects.create(defense_type='formal', rules_snapshot=rules(),
            input_snapshot={'students': [{'id': student.pk, 'name': student.name}]})
        for date, text in [('', ''), ('2026-11-16', '待定'), ('2026-11-16', '12:00-09:00')]:
            with self.subTest(date=date, time=text):
                groups = [dict(students=[{'id': student.pk}], teachers=[], date=date, timeRange=text)]
                result = ScheduleViewSet()._allocation_summary(version, groups, [])
                self.assertEqual(result['allocationStatus'], 'partial')
                self.assertEqual([s['id'] for s in result['unassignedStudents']], [student.pk])

    def test_summary_does_not_report_duplicate_assignments_as_complete(self):
        student = Student.objects.create(name='重复学生', defense_types=['正式答辩'])
        version = ScheduleVersion.objects.create(defense_type='formal', rules_snapshot=rules(),
            input_snapshot={'students': [{'id': student.pk, 'name': student.name}]})
        group = dict(students=[{'id': student.pk}], teachers=[], date='2026-11-16', timeRange='09:00-12:00')
        result = ScheduleViewSet()._allocation_summary(version, [group, group], [])
        self.assertEqual(result['allocationStatus'], 'partial')

    def test_all_campus_batches_reserve_staff_from_other_stages(self):
        teacher = Teacher.objects.create(name='跨阶段专家', title='教授', availability_confirmed=True)
        pre = ScheduleVersion.objects.create(defense_type='pre', rules_snapshot=rules('pre'))
        Group.objects.create(schedule_version=pre, group_id='P001', campus='创新港',
            chair=teacher, time='2026-11-16 09:00-12:00')
        payload, _ = build_algorithm_input('formal', rules=rules())
        self.assertIn('2026-11-16 09:00-12:00', payload['teachers'][0]['available_time'])
        formal = ScheduleVersion.objects.create(defense_type='formal', rules_snapshot=rules())
        group = Group.objects.create(schedule_version=formal, group_id='F001', campus='兴庆',
            chair=teacher, time='2026-11-16 10:00-12:00')
        conflicts = cross_batch_conflicts(formal, [group])
        self.assertTrue(any(c['type'] == 'teacher_time_conflict' for c in conflicts))

    def test_frozen_pre_export_reserves_its_saved_staff(self):
        teacher = Teacher.objects.create(name='仅参加预答辩的导师', title='教授',
            available_types=['预答辩'], availability_confirmed=True)
        other = Teacher.objects.create(name='正式专家', title='教授', availability_confirmed=True)
        student = Student.objects.create(name='正式学生', mentor=teacher,
            mentor_name=teacher.name, defense_types=['正式答辩'])
        pre = ScheduleVersion.objects.create(defense_type='pre', rules_snapshot=rules('pre'),
            export_snapshot=[dict(id=99, group_id='P001', time='2026-11-16 09:00-12:00',
                campus='创新港', room=None, chair={'id': other.pk}, secretary=None, experts=[], students=[])])
        payload, notices = build_algorithm_input('formal', rules=rules())
        self.assertNotIn(teacher.pk, {t['id'] for t in payload['teachers']})
        self.assertEqual([s['id'] for s in payload['students']], [student.pk])
        self.assertIn('2026-11-16 09:00-12:00',
            next(t['available_time'] for t in payload['teachers'] if t['id'] == other.pk))
        self.assertTrue(any(n['type'] == 'mentor_unavailable_for_defense' for n in notices))


class PanelAffiliationTests(SimpleTestCase):
    def test_local_repair_ranks_affiliation_before_shares(self):
        from algorithm import GroupDraft
        from scheduling.cross_group import CrossGroupRepair
        staff = {i: SimpleNamespace(is_external=i in (1, 2)) for i in range(1, 5)}
        student_map = {i: SimpleNamespace(supervisor_id=(i - 1) // 4 + 1) for i in range(1, 13)}
        planner = SimpleNamespace(rules=rules('pre'), teacher_map=staff, student_map=student_map,
            combination_nodes=0, calendar=lambda: {}, panel_size=lambda campus: 3)
        planner.plans = [SimpleNamespace(group=GroupDraft('G1', '创新港', [1, 2, 3, 4, 9, 10],
                            chair_id=3, expert_ids=[1, 4])),
                         SimpleNamespace(group=GroupDraft('G2', '创新港', [5, 6, 7, 8, 11, 12],
                            chair_id=3, expert_ids=[2, 4]))]
        repair = CrossGroupRepair(planner)
        preferred = repair.quality()
        planner.plans[0].group.student_ids = [1, 2, 5, 6, 9, 10]
        planner.plans[1].group.student_ids = [3, 4, 7, 8, 11, 12]
        for plan in planner.plans:
            plan.group.expert_ids = [1, 2]
        self.assertLess(preferred, repair.quality())

    def test_personnel_and_local_repair_preserve_affiliation_priority(self):
        from algorithm import generate_schedule
        staff = [dict(id=i, name=f'T{i}', title='教授', roles=['普通专家'],
            is_external=i in (1, 2), availability_confirmed=True) for i in range(1, 6)]
        staff.append(dict(id=6, name='秘书', title='讲师', roles=['秘书'], availability_confirmed=True))
        students = [dict(id=i, name=f'S{i}', supervisor_id=(i - 1) // 4 + 1, campus='创新港')
                    for i in range(1, 13)]
        result = generate_schedule(staff, students, [], rules('pre'))
        self.assertEqual(result['unassigned_students'], [])
        external = {1, 2}
        self.assertTrue(all(len(external & {g['chair_id'], *g['expert_ids']}) <= 1
                            for g in result['groups']), result['groups'])

    def test_minimizes_second_external_before_equal_mentor_shares(self):
        from scheduling.balanced_counts import pack_counts
        counts = Counter({1: 4, 2: 4, 3: 4})
        staff = {tid: SimpleNamespace(is_external=tid != 3) for tid in counts}
        seed = [Counter({1: 2, 2: 2, 3: 2})] * 2
        packed, diagnostics = pack_counts(counts, 6, 5, 7, 3, 2, staff, {3},
            lambda demand: True, seed, prioritize_shares=True, prioritize_external=True)
        self.assertEqual(sum(packed, Counter()), counts)
        self.assertTrue(all(sum(staff[t].is_external for t in panel) <= 1 for panel in packed), packed)
        self.assertEqual(diagnostics['objective_order'],
            ['coverage', 'external_exceptions', 'mentor_shares', 'group_sizes', 'appearances'])

    def test_external_exception_remains_available_when_needed_for_coverage(self):
        from scheduling.balanced_counts import pack_counts
        counts = Counter({1: 2, 2: 2, 3: 2})
        staff = {tid: SimpleNamespace(is_external=tid != 3) for tid in counts}
        packed, _ = pack_counts(counts, 6, 5, 7, 3, 2, staff, {3},
            lambda demand: True, [counts], prioritize_shares=True, prioritize_external=True)
        self.assertEqual(sum(packed, Counter()), counts)
        self.assertEqual(len(packed), 1)

    def test_confirmed_affiliation_correction_keeps_other_teachers_unchanged(self):
        from api.services.reference_data import correct_imported_affiliation
        for name in ('王飞（软）', '王飞(软)'):
            payload = correct_imported_affiliation(dict(name=name, isExternal=True, college='外院'))
            self.assertFalse(payload['isExternal'])
            self.assertTrue(payload['isSoftwareTeacher'])
            self.assertEqual(payload['college'], '软件学院')
        unrelated = dict(name='其他教师', isExternal=True, college='其他学院')
        self.assertEqual(correct_imported_affiliation(dict(unrelated)), unrelated)


class MidPolicy4ContinuityAndExternalTests(TestCase):
    def test_mid_policy4_ignores_pre_secretary_binding_and_external_group_count(self):
        import algorithm
        from api.models import Room
        from api.services.schedules import ScheduleApplication

        pre_sec = Teacher.objects.create(name='预答辩秘书', title='讲师', roles=['秘书'],
            available_types=['预答辩', '中期答辩'])
        ext_mentor = Teacher.objects.create(name='外院导师', title='教授', is_external=True, is_software_teacher=False,
            college='外院', roles=['组长', '评审'], available_types=['中期答辩'])
        chairs = [
            Teacher.objects.create(name=f'正高{i}', title='教授', roles=['组长', '评审'], available_types=['中期答辩'])
            for i in range(1, 3)
        ]
        reviewers = [
            Teacher.objects.create(name=f'评审{i}', title='副教授', roles=['评审'], available_types=['中期答辩'])
            for i in range(1, 5)
        ]
        mid_secs = [
            Teacher.objects.create(name=f'中秘{i}', title='讲师', roles=['秘书'], available_types=['中期答辩'])
            for i in range(1, 3)
        ]
        # 20 名创新港学生：前 3 名绑定同一个外院导师（按 10 人切片会落在第 1 组），
        # 全部学生带有预答辩写入的 bound_secretary，验证 mid 生成、局部检测、全局校验均不误报
        for idx in range(1, 21):
            Student.objects.create(
                name=f'中期生{idx}',
                campus='创新港',
                mentor=ext_mentor if idx <= 3 else chairs[0],
                mentor_name=ext_mentor.name if idx <= 3 else chairs[0].name,
                bound_secretary=pre_sec,
                secretary_name=pre_sec.name,
                defense_types=['中期答辩'],
            )
        Room.objects.create(name='港-101', campus='创新港')
        Room.objects.create(name='港-102', campus='创新港')

        mid_rules = rules('mid')
        payload, notices = build_algorithm_input('mid', rules=mid_rules)
        self.assertTrue(all(s['secretary_id'] is None for s in payload['students']))
        self.assertEqual(notices, [])

        version = ScheduleApplication().generate_version(mid_rules)
        self.assertEqual(version.groups.count(), 2)
        conflict_types = {c['type'] for c in version.conflicts_snapshot}
        self.assertNotIn('secretary_continuity_broken', conflict_types)
        self.assertNotIn('external_mentor_group_count', conflict_types)

        checked_types = {c['type'] for c in ScheduleViewSet()._check_conflicts(version)}
        self.assertNotIn('secretary_continuity_broken', checked_types)
        self.assertNotIn('external_mentor_group_count', checked_types)

        # 直接调用 algorithm 时，即使入参仍带有 secretary_id 且外院 3 名学生放在同一组（未拆 2 组），也不得误报
        direct_students = [
            algorithm.Student(id=s['id'], name=s['name'], supervisor_id=ext_mentor.pk if i < 3 else chairs[0].pk,
                              campus='创新港', secretary_id=pre_sec.pk)
            for i, s in enumerate(payload['students'])
        ]
        direct_drafts = [
            algorithm.GroupDraft('G001', '创新港', [s.id for s in direct_students[0:10]], secretary_id=mid_secs[0].pk),
            algorithm.GroupDraft('G002', '创新港', [s.id for s in direct_students[10:20]], secretary_id=mid_secs[1].pk),
        ]
        direct_teachers = [
            algorithm.Teacher(id=t.pk, name=t.name, college=t.college, is_external=t.is_external, title=t.title)
            for t in [pre_sec, ext_mentor, *chairs, *reviewers, *mid_secs]
        ]
        direct_conflicts = algorithm.detect_global_conflicts(direct_drafts, direct_students, direct_teachers, [], mid_rules)
        direct_types = {c['type'] for c in direct_conflicts}
        self.assertNotIn('secretary_continuity_broken', direct_types)
        self.assertNotIn('external_mentor_group_count', direct_types)

    def test_mid_move_student_does_not_overwrite_pre_bound_secretary(self):
        from api.services.adjustments import move_student_bundle

        pre_sec = Teacher.objects.create(name='预答辩原秘书', title='讲师', roles=['秘书'])
        mid_sec_a = Teacher.objects.create(name='中期秘书A', title='讲师', roles=['秘书'])
        mid_sec_b = Teacher.objects.create(name='中期秘书B', title='讲师', roles=['秘书'])
        student = Student.objects.create(
            name='跨阶段学生',
            campus='创新港',
            bound_secretary=pre_sec,
            secretary_name=pre_sec.name,
            defense_types=['预答辩', '中期答辩'],
        )
        mid_version = ScheduleVersion.objects.create(defense_type='mid', status='draft', is_current=True)
        source = Group.objects.create(schedule_version=mid_version, group_id='M001', campus='创新港', secretary=mid_sec_a)
        target = Group.objects.create(schedule_version=mid_version, group_id='M002', campus='创新港', secretary=mid_sec_b)
        source.students.add(student)

        move_student_bundle(student, source, target, preserve_secretary=False, replacement_secretary=mid_sec_b)
        student.refresh_from_db()
        self.assertEqual(student.bound_secretary_id, pre_sec.pk)
        self.assertEqual(student.secretary_name, pre_sec.name)
