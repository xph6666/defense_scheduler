"""Mixed pre-defense panels and ordered fairness goals."""
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from algorithm import generate_schedule, parse_teacher, parse_student, GroupDraft, parse_time_range
from api.services.rules import normalize_schedule_rules
from scheduling.current import validate
from scheduling.pre_capacity import pre_capacity_notices


def rules(**changes):
    return normalize_schedule_rules(dict(policy_version=4, defense_type='pre',
        start_date='2026-11-02', end_date='2026-11-05', expert_count=3, expert_min=3,
        campus_expert_counts={'创新港': 3, '兴庆': 5}, **changes))


def teachers():
    return [dict(id=i, name=f'T{i}', title='教授', roles=['普通专家'], availability_confirmed=True)
            for i in range(1, 12)] + [dict(id=12, name='秘书', title='讲师', roles=['秘书'], availability_confirmed=True)]


class CampusExpertTests(SimpleTestCase):
    def test_map_is_validated_and_never_applied_to_formal_or_legacy(self):
        for mapping in ({'兴庆': 4}, {'兴庆': True}, {'兴庆': '5'}, {'其他': 5}, [], None):
            with self.subTest(mapping=mapping), self.assertRaises(ValidationError):
                normalize_schedule_rules(dict(policy_version=4, campus_expert_counts=mapping))
        for stage, version in [('formal', 4), ('mid', 4), ('pre', 3)]:
            with self.subTest(stage=stage, version=version), self.assertRaises(ValidationError):
                normalize_schedule_rules(dict(policy_version=version, defense_type=stage,
                    campus_expert_counts={'兴庆': 5}))

    def test_mixed_panels_share_one_teacher_calendar(self):
        students = [dict(id=i, name=f'S{i}', supervisor_id=1, campus='创新港' if i <= 6 else '兴庆')
                    for i in range(1, 13)]
        result = generate_schedule(teachers(), students, [], rules())
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len(result['groups']), 2)
        for group in result['groups']:
            self.assertEqual(len({group['chair_id'], *group['expert_ids']}), 3 if group['campus'] == '创新港' else 5)
        self.assertNotEqual(result['groups'][0]['time'], result['groups'][1]['time'])
        self.assertFalse(any(c['type'] in ('teacher_time_conflict', 'expert_count_out_of_range') for c in result['conflicts']))

    def test_saved_mixed_panel_is_checked_by_its_campus(self):
        students = [parse_student(dict(id=i, name=f'S{i}', supervisor_id=1, campus='兴庆')) for i in range(1, 7)]
        group = GroupDraft('G001', '兴庆', list(range(1, 7)), parse_time_range('2026-11-02 09:00-12:00'),
                           None, 1, [2, 3], 12)
        issues = validate([group], students, [parse_teacher(t) for t in teachers()], rules())
        self.assertTrue(any(c['type'] == 'expert_count_out_of_range' and '5' in c['description'] for c in issues))

    def test_general_nonchair_bound_explains_conflict_and_suggests_five(self):
        staff = [parse_teacher(dict(id=i, name=f'T{i}', title='副教授', roles=['普通专家'])) for i in range(1, 6)]
        staff.append(parse_teacher(dict(id=10, name='组长', title='教授', roles=['普通专家'])))
        students = [parse_student(dict(id=i, name=f'S{i}', supervisor_id=(i - 1) % 5 + 1, campus='兴庆')) for i in range(1, 13)]
        config = rules()
        config['campus_expert_counts']['兴庆'] = 3
        issues = pre_capacity_notices(students, staff, config)
        self.assertEqual(len(issues), 1)
        self.assertIn('至少需要 3 组', issues[0]['description'])
        self.assertIn('最多只能开 2 组', issues[0]['description'])
        self.assertIn('5 位', issues[0]['description'])
        self.assertFalse(pre_capacity_notices(students, staff, rules()))

    def test_share_priority_does_not_trade_even_shares_for_fewer_appearances(self):
        from scheduling.balanced_counts import pack_counts
        counts = Counter({1: 4, 2: 4, 3: 4})
        staff = {tid: SimpleNamespace(is_external=False) for tid in counts}
        packed, diagnostics = pack_counts(counts, 6, 5, 7, 3, 1, staff, {1, 2, 3},
            lambda demand: True, [Counter({1: 4, 2: 2}), Counter({2: 2, 3: 4})], prioritize_shares=True)
        self.assertEqual(sum(packed, Counter()), counts)
        self.assertEqual([sorted(c.values()) for c in packed], [[2, 2, 2], [2, 2, 2]])
        self.assertEqual(diagnostics['objective_order'], ['coverage', 'mentor_shares', 'group_sizes', 'appearances'])
