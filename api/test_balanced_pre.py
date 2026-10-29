"""Confirmed pre-first policy: fair work, balanced seats, stable translation."""
from collections import Counter

from django.test import SimpleTestCase, TestCase

from algorithm import generate_schedule, parse_teacher, parse_student
from scheduling.personnel_first import PersonnelPlanner
from . import test_current_scheduling as fixtures
from .test_current_scheduling import teachers, students
from .services.rules import normalize_schedule_rules


def rules(stage='pre', count=3):
    return normalize_schedule_rules(fixtures.rules(stage, count))


class BalancedPreTests(SimpleTestCase):
    def test_only_five_six_seven_are_allowed(self):
        for count in (5, 6, 7):
            result = generate_schedule(teachers(), students(count), [], rules())
            self.assertEqual(result['unassigned_students'], [])
            self.assertEqual([len(g['student_ids']) for g in result['groups']], [count])
        for count in (3, 4):
            short = generate_schedule(teachers(), students(count), [], rules())
            self.assertEqual(short['groups'], [])
            self.assertEqual(len(short['unassigned_students']), count)

    def test_second_external_mentor_is_used_only_after_strict_floor_fails(self):
        staff = teachers()
        staff[1]['is_external'] = True
        cohort = students(6)
        for index, student in enumerate(cohort):
            student['supervisor_id'] = index // 2 + 1
        config = {**rules(), 'external_expert_max': 2}
        result = generate_schedule(staff, cohort, [], config)
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual([len(g['student_ids']) for g in result['groups']], [6])
        self.assertTrue(result['diagnostics']['external_relaxation_tried'])
        self.assertTrue(any(c['type'] == 'external_distribution' and '2 位' in c['description']
                            for c in result['conflicts']))

    def test_external_rule_is_not_relaxed_when_original_composition_works(self):
        result = generate_schedule(teachers(), students(12), [], {**rules(), 'external_expert_max': 2})
        self.assertEqual(result['unassigned_students'], [])
        self.assertNotIn('external_relaxation_tried', result['diagnostics'])
        self.assertTrue(all(len({g['chair_id'], *g['expert_ids']} & {3}) <= 1 for g in result['groups']))

    def test_generation_cannot_lower_the_five_student_floor(self):
        config = normalize_schedule_rules({**rules(), 'group_min': 1, 'group_max': 6})
        self.assertEqual((config['group_min'], config['group_size'], config['group_max']), (5, 6, 7))

    def test_remainders_use_few_non_six_panels(self):
        expected = {16: [5, 5, 6], 17: [5, 6, 6], 18: [6, 6, 6],
                    19: [6, 6, 7], 20: [6, 7, 7], 23: [5, 6, 6, 6],
                    24: [6, 6, 6, 6], 25: [6, 6, 6, 7]}
        for count, sizes in expected.items():
            with self.subTest(count=count):
                result = generate_schedule(teachers(), students(count), [],
                                           {**rules(), 'end_date': '2026-11-06'})
                self.assertEqual(result['unassigned_students'], [])
                self.assertEqual(sorted(len(g['student_ids']) for g in result['groups']), sizes)
                self.assertEqual(len({sid for g in result['groups'] for sid in g['student_ids']}), count)

    def test_joint_quality_includes_mentor_shares_and_zero_student_reviewers(self):
        from scheduling.fairness import mentor_share_excess, panel_cost
        self.assertEqual(mentor_share_excess(Counter({1: 2, 2: 2, 3: 2}), 3), 0)
        self.assertEqual(mentor_share_excess(Counter({1: 4, 2: 1, 3: 1}), 3), 3)
        self.assertEqual(mentor_share_excess(Counter({1: 6}), 3), 12)
        self.assertLess(panel_cost(Counter({1: 2, 2: 2, 3: 1}), 6, 3),
                        panel_cost(Counter({1: 4, 2: 1, 3: 1}), 6, 3))

    def test_five_experts_consider_five_mentors_with_even_student_shares(self):
        staff = teachers()
        cohort = students(6)
        for index, student in enumerate(cohort):
            student['supervisor_id'] = min(index + 1, 5)
        result = generate_schedule(staff, cohort, [], rules(count=5))
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len(result['groups']), 1)
        shares = result['diagnostics']['fairness']['panels'][0]['mentor_students'].values()
        self.assertEqual(sorted(shares), [1, 1, 1, 1, 2])

    def test_legacy_four_person_snapshot_still_validates(self):
        from scheduling.current import validate
        from algorithm import GroupDraft, parse_time_range
        config = {**rules(), 'group_min': 4}
        result = generate_schedule(teachers(), students(4), [], config)
        group = result['groups'][0]
        draft = GroupDraft(group['group_id'], group['campus'], group['student_ids'],
                           parse_time_range(group['time']), None, group['chair_id'],
                           group['expert_ids'], group['secretary_id'])
        conflicts = validate([draft], [parse_student(s) for s in students(4)],
                             [parse_teacher(t) for t in teachers()], config)
        self.assertFalse(any(c['type'] == 'group_size_out_of_range' for c in conflicts))

    def test_five_experts_can_merge_mentor_groups_that_lack_a_qualified_chair(self):
        staff = teachers()
        for teacher in staff:
            if teacher['id'] in (2, 3, 4):
                teacher['roles'] = ['普通专家']
                teacher['title'] = '讲师'
        cohort = students(6)
        for index, student in enumerate(cohort):
            student['supervisor_id'] = 2 + index // 2
        strict = generate_schedule(staff, cohort, [], rules())
        self.assertTrue(strict['unassigned_students'])
        expanded = generate_schedule(staff, cohort, [], rules(count=5))
        self.assertEqual(expanded['unassigned_students'], [])
        self.assertEqual([len(g['student_ids']) for g in expanded['groups']], [6])
        self.assertEqual(len({expanded['groups'][0]['chair_id'], *expanded['groups'][0]['expert_ids']}), 5)

    def test_saved_new_rule_config_rejects_four_person_minimum(self):
        from api.serializers import RuleConfigSerializer
        config = RuleConfigSerializer(data={'defense_type': 'pre', 'policyVersion': 3,
                                            'studentCount': {'target': 6, 'min': 4, 'max': 7}})
        self.assertFalse(config.is_valid())
        self.assertIn('studentCount', config.errors)

    def test_ten_students_balance_to_five_and_five(self):
        result = generate_schedule(teachers(), students(10), [], rules())
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(sorted(len(g['student_ids']) for g in result['groups']), [5, 5])
        self.assertFalse(any(c['type'] == 'student_group_exception' for c in result['conflicts']))

    def test_eleven_students_use_six_and_five_with_exactly_three_experts(self):
        result = generate_schedule(teachers(), students(11), [], rules())
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(sorted(len(g['student_ids']) for g in result['groups']), [5, 6])
        for group in result['groups']:
            self.assertEqual(len({group['chair_id'], *group['expert_ids']}), 3)

    def test_thirteen_students_balance_remainder_without_silent_loss(self):
        result = generate_schedule(teachers(), students(13), [], {**rules(), 'end_date': '2026-11-04'})
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(sorted(len(g['student_ids']) for g in result['groups']), [6, 7])
        self.assertEqual(sorted(s for g in result['groups'] for s in g['student_ids']), list(range(1, 14)))
        self.assertFalse(any(c['type'] == 'student_group_exception' for c in result['conflicts']))

    def test_external_mentors_seed_separate_full_panels(self):
        staff = teachers()
        staff[1]['is_external'] = True
        cohort = students(12)
        for index, student in enumerate(cohort):
            student['supervisor_id'] = 2 if index < 2 else 3 if index < 4 else 1
        result = generate_schedule(staff, cohort, [], rules())
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual([len(g['student_ids']) for g in result['groups']], [6, 6])
        for group in result['groups']:
            self.assertEqual(len({2, 3} & {group['chair_id'], *group['expert_ids']}), 1)

    def test_fair_appearances_outrank_paired_half_day_preference(self):
        planner = PersonnelPlanner([parse_teacher(t) for t in teachers()],
                                   [parse_student(s) for s in students(6)], rules())
        morning, afternoon = planner.slots[:2]
        planner.reserve('one', morning, {1}, 6)
        self.assertLess(planner.rank(2, afternoon), planner.rank(1, afternoon))

    def test_equal_appearances_prefer_fewer_reviewed_students(self):
        planner = PersonnelPlanner([parse_teacher(t) for t in teachers()],
                                   [parse_student(s) for s in students(6)], rules())
        morning, afternoon = planner.slots[:2]
        planner.reserve('one', morning, {1}, 6)
        planner.reserve('two', morning, {2}, 5)
        self.assertLess(planner.rank(2, afternoon), planner.rank(1, afternoon))
        before = planner.attendance_score()
        planner.reserve('one', morning, {1}, 5)
        self.assertLess(planner.attendance_score(), before)

    def test_optional_reviewers_have_balanced_appearances(self):
        result = generate_schedule(teachers(), students(36), [], {**rules(), 'end_date': '2026-11-06'})
        self.assertEqual(result['unassigned_students'], [])
        loads = Counter(tid for g in result['groups'] for tid in g['expert_ids'] if tid != 3)
        counts = [loads[tid] for tid in (2, 4, 5, 6)]
        self.assertLessEqual(max(counts) - min(counts), 1)
        self.assertFalse(any(c['type'] == 'teacher_time_conflict' for c in result['conflicts']))


class PreFirstAPITests(TestCase):
    setUp = fixtures.CurrentSchedulingAPITests.setUp

    def test_separate_translation_preserves_pre_version_and_fixed_group(self):
        from api.models import Teacher
        Teacher.objects.filter(pk=1).update(title='副教授')
        pre = self.client.post('/api/schedule/generate/', {'rules': rules()}, format='json')
        self.assertEqual(pre.status_code, 200, pre.data)
        request = {'rules': {**rules('formal', 5), 'avoid_supervisor': False}, 'request_key': 'separate-formal'}
        formal = self.client.post('/api/schedule/generate/', request, format='json')
        self.assertEqual(formal.status_code, 200, formal.data)
        self.assertEqual(formal.data['sourcePreVersionId'], pre.data['versionId'])
        left, right = pre.data['groups'][0], formal.data['groups'][0]
        for key in ('groupName', 'chairId', 'secretaryId'):
            self.assertEqual(left[key], right[key])
        self.assertEqual({s['id'] for s in left['students']}, {s['id'] for s in right['students']})
        self.assertTrue({t['id'] for t in left['teachers']} <= {t['id'] for t in right['teachers']})
        self.assertEqual(len({right['chairId'], *[t['id'] for t in right['teachers']]}), 5)
        current = self.client.get('/api/schedule/current/', {'defense_type': 'pre'})
        self.assertEqual(current.data['versionId'], pre.data['versionId'])
        retry = self.client.post('/api/schedule/generate/', request, format='json')
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data['versionId'], formal.data['versionId'])
        checked = self.client.get('/api/schedule/current/', {'defense_type': 'formal'})
        self.assertFalse(any(c['level'] == 'error' for c in checked.data['conflicts']))

    def test_translation_requires_source_pre(self):
        response = self.client.post('/api/schedule/generate/', {'rules': rules('formal')}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('预答辩', response.data['error'])

    def test_fixed_group_number_cannot_be_renamed(self):
        generated = self.client.post('/api/schedule/generate/', {'rules': rules()}, format='json').data
        group = generated['groups'][0]
        response = self.client.post('/api/schedule/adjust-group/', {'group_id': group['id'],
            'expected_revision': generated['revision'], 'group_data': {**group, 'groupName': 'G999'}}, format='json')
        self.assertEqual(response.status_code, 400)
        current = self.client.get('/api/schedule/current/', {'defense_type': 'pre'}).data
        self.assertEqual(current['groups'][0]['groupName'], group['groupName'])

    def test_translation_keeps_unavailable_original_teacher_as_unassigned(self):
        from api.models import Teacher
        self.client.post('/api/schedule/generate/', {'rules': rules()}, format='json')
        Teacher.objects.filter(pk=1).update(unavailable_times='2026-11-03 00:00-23:59')
        response = self.client.post('/api/schedule/generate/', {'rules': rules('formal', 5)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['groups'], [])
        self.assertEqual(len(response.data['unassignedStudents']), 6)
