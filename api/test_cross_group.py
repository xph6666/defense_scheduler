"""Cross-group repair preserves coverage and commits only valid improvements."""
from collections import Counter
from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase

from algorithm import GroupDraft, parse_student, parse_teacher
from scheduling.cross_group import CrossGroupRepair
from scheduling.current import validate, participants
from scheduling.personnel_first import Demand, PanelPlan, PersonnelPlanner
from .test_balanced_pre import rules
from .test_current_scheduling import teachers, students


class CrossGroupTests(SimpleTestCase):
    def planner(self, *, distinct=False):
        cohort = students(12)
        mentors = ([1] * 4 + [2] * 2 + [4] * 2 + [5] * 4 if distinct
                   else [1] * 4 + [2] * 2 + [1] * 2 + [2] * 4)
        for student, mentor in zip(cohort, mentors):
            student['supervisor_id'] = mentor
        p = PersonnelPlanner([parse_teacher(t) for t in teachers()],
                             [parse_student(s) for s in cohort], rules())
        p.plans = []
        for i, ids in enumerate((list(range(1, 7)), list(range(7, 13)))):
            counts = Counter(p.student_map[sid].supervisor_id for sid in ids)
            chair, experts = ((1, [2, 3]) if i == 0 or not distinct else (5, [4, 6]))
            group = GroupDraft(f'G00{i + 1}', '创新港', ids, p.slots[i], None, chair, experts, 7)
            p.plans.append(PanelPlan(Demand(group.campus, counts), group))
            p.reserve(group.group_id, group.time_slot, participants(group, p.students), 6)
        return p

    def assert_valid(self, p):
        groups = [plan.group for plan in p.plans]
        covered = [sid for group in groups for sid in group.student_ids]
        self.assertEqual(sorted(covered), list(range(1, 13)))
        self.assertEqual(len(covered), len(set(covered)))
        self.assertTrue(all(5 <= len(group.student_ids) <= 7 for group in groups))
        soft = {'external_distribution', 'half_day_coverage', 'student_group_exception', 'mentor_student_imbalance', 'mentor_share_exception'}
        self.assertFalse([c for c in validate(groups, p.students, p.teachers, p.rules) if c['type'] not in soft])
        self.assertEqual({g.group_id for g in groups}, {'G001', 'G002'})
        for group in groups:
            self.assertEqual(p.reservations[group.group_id],
                             (group.time_slot, participants(group, p.students), len(group.student_ids)))

    def test_student_swap_improves_joint_score_without_losing_coverage(self):
        p = self.planner()
        before = CrossGroupRepair(p).quality()
        result = CrossGroupRepair(p).run()
        self.assertGreater(result['accepted_pairs'], 0)
        self.assertLess(result['after_quality'], before)
        self.assertLess(result['after_share_excess'], result['before_share_excess'])
        self.assert_valid(p)

    def test_repartition_can_change_required_reviewers(self):
        p = self.planner(distinct=True)
        old = [{plan.group.chair_id, *plan.group.expert_ids} for plan in p.plans]
        result = CrossGroupRepair(p).run()
        self.assertGreater(result['accepted_pairs'], 0)
        self.assertTrue(any({plan.group.chair_id, *plan.group.expert_ids} != before
                            for plan, before in zip(p.plans, old)))
        self.assert_valid(p)

    def test_staffing_failure_restores_groups_and_reservations(self):
        p = self.planner(distinct=True)
        before_groups, before_reservations = deepcopy(p.plans), deepcopy(p.reservations)
        p.secretary_ids.clear()
        result = CrossGroupRepair(p).run()
        self.assertEqual(result['accepted_pairs'], 0)

        self.assertEqual(p.plans, before_groups)
        self.assertEqual(p.reservations, before_reservations)

    def test_probe_exception_restores_reservations(self):
        p = self.planner(distinct=True)
        before = deepcopy(p.reservations)
        with patch.object(p, 'panel_options', side_effect=RuntimeError('probe failed')):
            with self.assertRaisesRegex(RuntimeError, 'probe failed'):
                CrossGroupRepair(p).try_pair(*p.plans)
        self.assertEqual(p.reservations, before)

    def test_global_validation_failure_rejects_a_locally_better_pair(self):
        p = self.planner(distinct=True)
        before_groups, before_reservations = deepcopy(p.plans), deepcopy(p.reservations)
        with patch('scheduling.cross_group.validate', return_value=[{'type': 'teacher_time_conflict'}]):
            result = CrossGroupRepair(p).run()
        self.assertEqual(result['accepted_pairs'], 0)
        self.assertEqual(p.plans, before_groups)
        self.assertEqual(p.reservations, before_reservations)

    def test_search_budget_and_determinism(self):
        p, q = self.planner(distinct=True), self.planner(distinct=True)
        first, second = CrossGroupRepair(p).run(), CrossGroupRepair(q).run()
        self.assertEqual(first, second)
        self.assertEqual(p.plans, q.plans)
        limited = CrossGroupRepair(self.planner())
        limited.MAX_PAIRS = 0
        result = limited.run()
        self.assertTrue(result['search_limited'])
        self.assertEqual(result['accepted_pairs'], 0)

        single = CrossGroupRepair(self.planner(distinct=True))
        single.MAX_PAIRS = 1
        result = single.run()
        self.assertEqual(result['checked_pairs'], 1)
        self.assertEqual(result['accepted_pairs'], 1)

    def test_cross_campus_groups_are_never_combined(self):
        p = self.planner(distinct=True)
        p.plans[1].group.campus = '兴庆'
        result = CrossGroupRepair(p).run()
        self.assertEqual(result['checked_pairs'], 0)

    def test_repair_can_find_another_day_when_new_mentor_cannot_attend_old_slot(self):
        from algorithm import build_candidate_slots
        from scheduling.current import available
        p = self.planner(distinct=True)
        p.rules['end_date'] = '2026-11-03'
        p.teacher_map[5].available_time = ['2026-11-02 09:00-12:00']
        p.slots = build_candidate_slots(p.rules, [])
        p.available_ids = {slot: {t.id for t in p.teachers if available(t, slot)} for slot in p.slots}
        result = CrossGroupRepair(p).run()
        self.assertGreater(result['accepted_pairs'], 0)
        self.assertLess(result['after_quality'], result['before_quality'])
        self.assert_valid(p)
        self.assertTrue(any(plan.group.time_slot.start.day == 3 for plan in p.plans))
