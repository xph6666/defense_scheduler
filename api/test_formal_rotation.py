"""Formal rotation boundaries, independent of application data."""
from django.test import SimpleTestCase

from algorithm import GroupDraft, parse_student, parse_teacher, parse_time_range
from scheduling.formal_rotation import rotate_panels
from scheduling.policies import formal_rotation_rules
from api.test_current_scheduling import rules, students, teachers


class FormalRotationTests(SimpleTestCase):
    def ordered_planner(self):
        from scheduling.formal_rotation import FormalRotation
        staff = teachers() + [dict(id=i, name=f'R{i}', title='教授',
                                  roles=['普通专家'], availability_confirmed=True) for i in range(8, 13)]
        source = [GroupDraft(name, '创新港', [sid], parse_time_range(when), None, 1, [2, 3], 7)
                  for name, sid, when in [('G10', 3, '2026-11-02 09:00-12:00'),
                                          ('G2', 2, '2026-11-02 14:00-17:00'),
                                          ('G1', 1, '2026-11-02 14:00-17:00')]]
        config = {**rules('formal', 5), **formal_rotation_rules('副教授'), 'end_date': '2026-11-04'}
        return FormalRotation(source, [parse_teacher(t) for t in staff],
                              [parse_student(s) for s in students(3)], config)

    def test_original_group_numbers_determine_chronology_in_natural_order(self):
        result = self.ordered_planner().run()
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual([g['group_id'] for g in result['groups']], ['G1', 'G2', 'G10'])
        self.assertEqual([g['time'] for g in result['groups']], sorted(g['time'] for g in result['groups']))

    def test_unplaced_middle_group_does_not_allow_later_group_to_move_back(self):
        from unittest.mock import patch
        planner = self.ordered_planner()
        # G1 is only available in the afternoon, G2 is unavailable, and G10 is
        # only available in the morning. Both surviving groups cannot be kept.
        with patch.object(planner, 'single_ok', side_effect=lambda i, t: (i, t) in {(0, 1), (2, 0)}):
            placement, _ = planner.solve_placement(len(planner.days), set())
            self.assertEqual(len(placement), 1)
            fallback = planner.greedy_placement(len(planner.days), set())
            self.assertEqual(fallback, {0: 1})

    def test_manual_time_reversal_is_detected_only_for_new_ordered_versions(self):
        from scheduling.current import validate
        from algorithm import parse_time_range
        planner = self.ordered_planner()
        result = planner.run()
        groups = [GroupDraft(g['group_id'], g['campus'], g['student_ids'], parse_time_range(g['time']),
                             None, g['chair_id'], g['expert_ids'], g['secretary_id']) for g in result['groups']]
        groups[0].time_slot, groups[-1].time_slot = groups[-1].time_slot, groups[0].time_slot
        conflicts = validate(groups, planner.students, planner.teachers, planner.rules)
        self.assertTrue(any(c['type'] == 'formal_group_order' for c in conflicts))
        legacy = {**planner.rules, 'formal_group_order': False}
        self.assertFalse(any(c['type'] == 'formal_group_order' for c in
                             validate(groups, planner.students, planner.teachers, legacy)))

    def test_solver_timeout_cannot_discard_a_complete_feasible_ordered_plan(self):
        from unittest.mock import patch
        planner = self.ordered_planner()
        with patch.object(planner, 'solve_placement', return_value=({0: 0}, 'milp_status_1')):
            placement = planner.place()
        self.assertEqual(len(placement), 3)
        self.assertEqual(list(sorted(placement.values())), [placement[i] for i in range(3)])

    def test_consecutive_groups_can_share_a_half_day_with_distinct_staff(self):
        from scheduling.formal_rotation import FormalRotation
        staff = teachers() + [dict(id=i, name=f'R{i}', title='教授',
                                  roles=['普通专家'], availability_confirmed=True) for i in range(8, 18)]
        staff.append(dict(id=20, name='秘书2', title='讲师', roles=['秘书'], availability_confirmed=True))
        source = [GroupDraft(f'G{i}', '创新港', [i], parse_time_range('2026-11-02 09:00-12:00'),
                             None, 1, [2, 3], 7 if i == 1 else 20) for i in (1, 2)]
        config = {**rules('formal', 5), **formal_rotation_rules('副教授')}
        result = FormalRotation(source, [parse_teacher(t) for t in staff],
                                [parse_student(s) for s in students(2)], config).run()
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len({g['time'] for g in result['groups']}), 1)

    def test_pre_defense_cannot_add_external_chair_to_external_mentor(self):
        from collections import Counter
        from scheduling.personnel_first import PersonnelPlanner, Demand
        staff = teachers()
        staff[3]['is_external'] = True
        cohort = students(5)
        for s in cohort:
            s['supervisor_id'] = 3
        config = {**rules(count=5), 'external_expert_max': 2}
        planner = PersonnelPlanner([parse_teacher(t) for t in staff],
                                   [parse_student(s) for s in cohort], config)
        options = list(planner.panel_options(Demand('创新港', Counter({3: 5})),
                                             planner.slots[0], 4, set(range(1, 8))))
        self.assertEqual(options, [])

    def plan(self, groups=1, title='教授', secretary_busy=False):
        staff = teachers() + [dict(id=i, name=f'R{i}', title=title,
                                  roles=['普通专家'], availability_confirmed=True)
                              for i in range(8, 13)]
        # Original reviewers and mentor are unavailable on formal day: attendance
        # must be determined only by the new panel and inherited secretary.
        for t in staff[:6]:
            t['available_time'] = ['2026-11-03 00:00-23:59']
        if secretary_busy:
            staff[6]['available_time'] = ['2026-11-03 00:00-23:59']
        cohort = students(groups)
        source = [GroupDraft(f'G{i}', '创新港', [i], parse_time_range('2026-11-02 09:00-12:00'),
                             None, 1, [2, 3], 7) for i in range(1, groups + 1)]
        config = {**rules('formal', 5), **formal_rotation_rules('副教授')}
        return rotate_panels(source, [parse_teacher(t) for t in staff],
                             [parse_student(s) for s in cohort], config)

    def test_mentor_and_original_reviewers_need_not_attend(self):
        result = self.plan()
        self.assertEqual(result['unassigned_students'], [])
        group = result['groups'][0]
        self.assertEqual({group['chair_id'], *group['expert_ids']}, set(range(8, 13)))
        self.assertEqual(group['secretary_id'], 7)
        self.assertFalse(any(c['type'] == 'teacher_unavailable' for c in result['conflicts']))

    def test_associate_chair_is_reported_as_relaxed(self):
        result = self.plan(title='副教授')
        self.assertEqual(result['unassigned_students'], [])
        self.assertTrue(any(c['type'] == 'chair_title_relaxed' for c in result['conflicts']))

    def test_insufficient_half_days_report_every_unplaced_student(self):
        result = self.plan(groups=3)
        self.assertEqual(len(result['groups']), 2)
        self.assertEqual(len(result['unassigned_students']), 1)
        self.assertIn('容量不足', result['unassigned_students'][0]['reason'])
        self.assertIn('延长日期', result['unassigned_students'][0]['reason'])

    def test_unavailable_inherited_secretary_is_not_replaced(self):
        result = self.plan(secretary_busy=True)
        self.assertEqual(result['groups'], [])
        self.assertEqual(len(result['unassigned_students']), 1)
        self.assertIn('秘书', result['unassigned_students'][0]['reason'])
