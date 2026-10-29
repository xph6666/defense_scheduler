"""Both stages share the final chronological pre-defense group numbers."""
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from algorithm import GroupDraft, parse_student, parse_teacher, parse_time_range
from scheduling.personnel_first import PersonnelPlanner, PanelPlan, Demand
from collections import Counter
from api.test_current_scheduling import teachers, students, rules
from api import test_current_scheduling as fixtures


class PreGroupNumberTests(SimpleTestCase):
    def test_new_generation_from_old_cached_input_finalizes_numbers_without_mutating_cache(self):
        from copy import deepcopy
        from api.services.pre_plan_cache import validated
        config = {**rules(), 'pre_group_order': True}
        cohort = students(2)
        cached = {'groups': [
            dict(group_id='G001', campus='创新港', student_ids=[1], time='2026-11-02 14:00-17:00',
                 chair_id=1, expert_ids=[2, 3], secretary_id=7),
            dict(group_id='G002', campus='创新港', student_ids=[2], time='2026-11-02 09:00-12:00',
                 chair_id=1, expert_ids=[2, 3], secretary_id=7)], 'conflicts': [], 'unassigned_students': []}
        original = deepcopy(cached)
        result = validated({'teachers': teachers(), 'students': cohort}, config, cached)
        self.assertIsNotNone(result)
        self.assertEqual([g['student_ids'] for g in result['groups']], [[2], [1]])
        self.assertEqual([g['group_id'] for g in result['groups']], ['G001', 'G002'])
        self.assertEqual(cached, original)

    def test_saved_pre_group_time_reversal_is_reported_without_renumbering(self):
        from scheduling.current import validate
        groups = [GroupDraft('G001', '创新港', [1], parse_time_range('2026-11-02 14:00-17:00'), None, 1, [2, 3], 7),
                  GroupDraft('G002', '创新港', [2], parse_time_range('2026-11-02 09:00-12:00'), None, 1, [2, 3], 7)]
        conflicts = validate(groups, [parse_student(s) for s in students(2)],
                             [parse_teacher(t) for t in teachers()], {**rules(), 'pre_group_order': True})
        self.assertTrue(any(c['type'] == 'pre_group_order' for c in conflicts))
        self.assertEqual(groups[0].student_ids, [1])
        self.assertEqual(groups[0].group_id, 'G001')

    def test_final_numbers_follow_time_after_last_optimization(self):
        planner = PersonnelPlanner([parse_teacher(t) for t in teachers()],
                                   [parse_student(s) for s in students(2)], rules())
        # A late optimization has moved provisional G001 behind G002.
        groups = [GroupDraft('G001', '创新港', [1], parse_time_range('2026-11-02 14:00-17:00'), None, 1, [2, 3], 7),
                  GroupDraft('G002', '创新港', [2], parse_time_range('2026-11-02 09:00-12:00'), None, 1, [2, 3], 7)]
        planner.plans = [PanelPlan(Demand('创新港', Counter({1: 1})), g) for g in groups]
        for g in groups:
            planner.reserve(g.group_id, g.time_slot, {1, 2, 3, 7}, 1)
        with patch.object(planner, 'assign_chairs'), patch.object(planner, 'assign_staff'), \
                patch.object(planner, 'assign_students'), patch.object(planner, 'compact_attendance'):
            result = planner.run()
        self.assertEqual([g['group_id'] for g in result['groups']], ['G001', 'G002'])
        self.assertEqual([g['student_ids'] for g in result['groups']], [[2], [1]])
        self.assertEqual([g['time'] for g in result['groups']], sorted(g['time'] for g in result['groups']))
        self.assertEqual(planner.reservations['G001'][0].start.hour, 9)


class LinkedGroupNumberTests(TestCase):
    setUp = fixtures.CurrentSchedulingAPITests.setUp

    def test_both_stages_use_same_groups_and_ascending_dates(self):
        from api.models import Student
        for i in range(7, 13):
            Student.objects.create(id=i, name=f'学生{i}', mentor_id=1, mentor_name='教师1',
                                   defense_types=['预答辩', '正式答辩'])
        response = self.client.post('/api/schedule/generate-linked/',
                                    {'pre_rules': rules(), 'formal_rules': rules('formal')}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        left, right = response.data['pre'], response.data['formal']
        for stage in (left, right):
            self.assertEqual(stage['unassignedStudents'], [])
            groups = sorted(stage['groups'], key=lambda g: g['groupName'])
            self.assertEqual([g['groupName'] for g in groups], ['G001', 'G002'])
            times = [(g['date'], g['timeRange']) for g in groups]
            self.assertEqual(times, sorted(times))
        self.assertTrue(left['rules']['pre_group_order'])
        for a, b in zip(sorted(left['groups'], key=lambda g: g['groupName']),
                        sorted(right['groups'], key=lambda g: g['groupName'])):
            self.assertEqual({s['id'] for s in a['students']}, {s['id'] for s in b['students']})
            self.assertEqual(a['secretaryId'], b['secretaryId'])
