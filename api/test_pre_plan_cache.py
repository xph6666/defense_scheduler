from copy import deepcopy
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from api.services.pre_plan_cache import read_pre_plan, remember_pre_plan
from .test_balanced_pre import rules
from .test_current_scheduling import teachers, students


class PrePlanCacheTests(SimpleTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='pre-plan-')
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(PRE_PLAN_CACHE_DIR=self.directory.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.payload = {'teachers': teachers(), 'students': students(6), 'rooms': []}
        self.rules = rules()
        self.plan = {'groups': [{'group_id': 'G001', 'campus': '创新港', 'student_ids': list(range(1, 7)),
                                'time': '2026-11-02 09:00-12:00', 'chair_id': 1, 'expert_ids': [2, 3], 'secretary_id': 7}],
                     'conflicts': [], 'unassigned_students': []}

    def test_complete_plan_survives_repeated_reads_and_derived_secretary_changes(self):
        self.assertTrue(remember_pre_plan(self.payload, self.rules, self.plan))
        self.payload['students'][0]['secretary_id'] = 7
        for _ in range(2):
            result = read_pre_plan(self.payload, self.rules)
            self.assertEqual(result['groups'], self.plan['groups'])
            self.assertTrue(result['diagnostics']['retained_complete_pre_plan'])

    def test_partial_or_duplicate_plan_is_not_retained(self):
        for ids in ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 5]):
            plan = deepcopy(self.plan)
            plan['groups'][0]['student_ids'] = ids
            self.assertFalse(remember_pre_plan(self.payload, self.rules, plan))
        self.assertIsNone(read_pre_plan(self.payload, self.rules))

    def test_unavailable_teacher_and_changed_rules_never_reuse_a_plan(self):
        self.assertTrue(remember_pre_plan(self.payload, self.rules, self.plan))
        self.payload['teachers'][0]['available_time'] = ['2026-11-02 09:00-12:00']
        self.assertIsNone(read_pre_plan(self.payload, self.rules))
        changed = {**self.rules, 'group_size': 7}
        self.assertIsNone(read_pre_plan(self.payload, changed))

    def test_every_read_revalidates_the_saved_plan(self):
        import json
        from pathlib import Path
        self.assertTrue(remember_pre_plan(self.payload, self.rules, self.plan))
        path = next(Path(self.directory.name).glob('*.json'))
        plan = deepcopy(self.plan)
        plan['groups'][0]['secretary_id'] = 1
        path.write_text(json.dumps(plan), encoding='utf8')
        self.assertIsNone(read_pre_plan(self.payload, self.rules))

    def test_a_worse_complete_plan_cannot_replace_a_better_one(self):
        self.payload['students'] = students(12)
        first = deepcopy(self.plan)
        other = deepcopy(first['groups'][0])
        other.update(group_id='G002', student_ids=list(range(7, 13)), time='2026-11-02 14:00-17:00')
        first['groups'].append(other)
        better = deepcopy(first)
        better['groups'][1]['expert_ids'] = [4, 5]
        self.assertTrue(remember_pre_plan(self.payload, self.rules, first))
        self.assertTrue(remember_pre_plan(self.payload, self.rules, better))
        self.assertFalse(remember_pre_plan(self.payload, self.rules, first))
        self.assertEqual(read_pre_plan(self.payload, self.rules)['groups'], better['groups'])
