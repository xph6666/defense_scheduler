"""Policy 3 regression coverage; no browser or application database required."""
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from algorithm import generate_schedule, GroupDraft, parse_student, parse_teacher, parse_time_range, detect_global_conflicts
from api.models import Teacher, Student
from api.services.rules import normalize_schedule_rules
from api.services.scheduling_input import build_algorithm_input


def rules(stage='pre', count=3):
    config = normalize_schedule_rules({'policy_version': 3, 'defense_type': stage,
        'start_date': '2026-11-02' if stage == 'pre' else '2026-11-03',
        'end_date': '2026-11-02' if stage == 'pre' else '2026-11-03',
        'expert_count': count, 'expert_min': count})
    return {**config, 'group_min': 1, 'group_max': 6, 'external_expert_max': 1}


def teachers():
    return [{'id': i, 'name': f'教师{i}', 'title': '教授', 'roles': ['组长', '普通专家'],
             'availability_confirmed': True, 'is_external': i == 3, 'available_time': []}
            for i in range(1, 7)] + [{'id': 7, 'name': '秘书', 'roles': ['秘书'],
                'title': '讲师', 'availability_confirmed': True, 'available_time': []}]


def students(count=5):
    # 同一导师在同一组最多占 3 个名额：夹具按 3 人一组分给轮换的导师，
    # 大样本（如 25 人）也能保持每组不超过 3 位导师。
    return [{'id': i, 'name': f'学生{i}', 'supervisor_id': ((i - 1) // 3) % 6 + 1,
             'campus': '创新港'} for i in range(1, count + 1)]


class CurrentEngineTests(SimpleTestCase):
    def test_resource_cache_is_invalidated_when_reservations_change(self):
        from scheduling.personnel_first import PersonnelPlanner
        planner = PersonnelPlanner([parse_teacher(t) for t in teachers()],
                                   [parse_student(s) for s in students(2)], rules())
        slot = planner.slots[0]
        initial = planner.rank(1, slot)
        self.assertFalse(planner.occupied(1, slot))
        planner.reserve('temporary', slot, {1}, 2)
        self.assertTrue(planner.occupied(1, slot))
        self.assertGreater(planner.rank(1, slot)[1], initial[1])
        planner.release('temporary')
        self.assertFalse(planner.occupied(1, slot))
        self.assertEqual(planner.rank(1, slot), initial)

    def test_input_order_does_not_change_the_deterministic_plan(self):
        first = generate_schedule(teachers(), students(4), [], rules())
        reversed_input = generate_schedule(list(reversed(teachers())), list(reversed(students(4))), [], rules())
        self.assertEqual(first['groups'], reversed_input['groups'])
        self.assertEqual(first['unassigned_students'], reversed_input['unassigned_students'])

    def backtracking_fixture(self):
        staff = [{'id': i, 'name': f'T{i}', 'title': '教授', 'availability_confirmed': True,
                  'available_time': ['2026-11-02 14:00-18:00'],
                  'roles': ['组长'] if i <= 3 else ['专家'] if i <= 9 else ['秘书']}
                 for i in range(1, 13)]
        staff[0]['forbidden_with'] = [7, 8, 9]
        staff[1]['forbidden_with'] = [6, 8, 9]
        staff[2]['forbidden_with'] = [4, 5, 7]
        cohort = students(3)
        for index, student in enumerate(cohort, start=1):
            student['supervisor_id'] = index
        return staff, cohort

    def test_staff_search_backtracks_without_moving_chairs_or_assigning_students_early(self):
        staff, cohort = self.backtracking_fixture()
        result = generate_schedule(staff, cohort, [], {**rules(), 'group_size': 1, 'group_max': 1})
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len(result['groups']), 3)
        self.assertGreater(result['diagnostics']['staff_search_nodes'], 3)
        self.assertTrue(all(not c['type'].endswith('conflict') for c in result['conflicts']))

    def test_search_budget_keeps_valid_partial_results_and_explains_limit(self):
        from unittest.mock import patch
        from scheduling.personnel_first import PersonnelPlanner
        staff, cohort = self.backtracking_fixture()
        with patch.object(PersonnelPlanner, 'MAX_SEARCH_NODES', 1):
            result = generate_schedule(staff, cohort, [], {**rules(), 'group_size': 1, 'group_max': 1})
        self.assertTrue(result['unassigned_students'])
        self.assertTrue(result['groups'])
        self.assertTrue(result['diagnostics']['search_limited'])
        self.assertTrue(any(c['type'] == 'search_limit' for c in result['conflicts']))
        covered = [sid for g in result['groups'] for sid in g['student_ids']]
        self.assertEqual(sorted(covered + [s['id'] for s in result['unassigned_students']]), [1, 2, 3])
        self.assertFalse(any(c['type'] == 'teacher_time_conflict' for c in result['conflicts']))

    def test_scarce_group_is_staffed_before_flexible_group(self):
        staff = [
            {'id': i, 'name': f'T{i}', 'title': '教授', 'availability_confirmed': True,
             'available_time': ['2026-11-02 14:00-18:00'],
             'roles': ['组长'] if i <= 2 else ['专家'] if i <= 6 else ['秘书']}
            for i in range(1, 9)]
        staff[1]['forbidden_with'] = [5, 6]
        cohort = students(2)
        cohort[1]['supervisor_id'] = 2
        result = generate_schedule(staff, cohort, [], {**rules(), 'group_size': 1, 'group_max': 1})
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len(result['groups']), 2)
        scarce = next(g for g in result['groups'] if 2 in g['student_ids'])
        self.assertEqual(set(scarce['expert_ids']), {3, 4})

    def test_all_chairs_then_all_staff_then_student_assignment(self):
        from unittest.mock import patch
        from scheduling.personnel_first import PersonnelPlanner
        events = []
        originals = {name: getattr(PersonnelPlanner, name) for name in (
            'assign_chairs', 'assign_staff', 'assign_students')}

        def wrap(name):
            def run(planner):
                events.append(name)
                if name == 'assign_staff':
                    self.assertGreaterEqual(len(planner.plans), 2)
                    self.assertTrue(all(plan.group.chair_id for plan in planner.plans))
                    self.assertTrue(all(not plan.group.expert_ids and not plan.group.student_ids for plan in planner.plans))
                if name == 'assign_students':
                    self.assertTrue(all(not plan.group.student_ids for plan in planner.plans))
                    self.assertTrue(all(len(plan.group.expert_ids) == 2 and plan.group.secretary_id for plan in planner.plans))
                return originals[name](planner)
            return run

        with patch.object(PersonnelPlanner, 'assign_chairs', wrap('assign_chairs')), \
                patch.object(PersonnelPlanner, 'assign_staff', wrap('assign_staff')), \
                patch.object(PersonnelPlanner, 'assign_students', wrap('assign_students')):
            result = generate_schedule(teachers(), students(10), [], rules())
        self.assertEqual(events, ['assign_chairs', 'assign_staff', 'assign_students'])
        self.assertEqual(result['unassigned_students'], [])

    def test_other_groups_chairs_are_reserved_before_filling_expert_seats(self):
        staff = teachers() + [
            {'id': 8, 'name': '备用专家', 'title': '教授', 'roles': ['专家'], 'availability_confirmed': True},
            {'id': 9, 'name': '备用秘书', 'title': '讲师', 'roles': ['秘书'], 'availability_confirmed': True}]
        for teacher in staff:
            teacher['available_time'] = ['2026-11-02 14:00-18:00']
        cohort = students(2)
        cohort[1]['supervisor_id'] = 2
        result = generate_schedule(staff, cohort, [], {**rules(), 'group_size': 1, 'group_max': 1})
        self.assertEqual(result['unassigned_students'], [])
        left, right = result['groups']
        self.assertEqual(left['time'], right['time'])
        self.assertNotIn(right['chair_id'], left['expert_ids'])
        self.assertNotIn(left['chair_id'], right['expert_ids'])

    def test_secretary_selection_keeps_internal_supplemental_seats_available(self):
        staff = [{'id': i, 'name': f'T{i}', 'title': '教授', 'roles': ['组长', '专家', '秘书'],
                  'availability_confirmed': True, 'is_external': i > 10,
                  'available_time': ['2026-11-03 14:00-18:00']} for i in range(1, 15)]
        cohort = students(4)
        for student in cohort[2:]:
            student['supervisor_id'] = 2
        result = generate_schedule(staff, cohort, [], rules('formal', 5))
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len(result['groups']), 2)
        self.assertTrue(all(group['secretary_id'] > 10 for group in result['groups']))
        self.assertFalse(any(c['type'] == 'teacher_time_conflict' for c in result['conflicts']))

    def test_default_three_exact_no_rooms_and_explicit_leftovers(self):
        result = generate_schedule(teachers(), students(7), [], rules())
        assigned = [sid for group in result['groups'] for sid in group['student_ids']]
        pending = [s['id'] for s in result['unassigned_students']]
        self.assertEqual(sorted(assigned + pending), list(range(1, 8)))
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(len(assigned), 7)
        self.assertEqual(sorted(len(g['student_ids']) for g in result['groups']), [3, 4])
        for group in result['groups']:
            self.assertEqual(len(group['expert_ids']), 2)
            self.assertNotIn(group['chair_id'], group['expert_ids'])
            self.assertIsNone(group['room_id'])
        self.assertEqual(result['unassigned_students'], [])

    def test_five_uses_four_internal_and_one_external(self):
        result = generate_schedule(teachers(), students(2), [], rules(count=5))
        self.assertEqual(len(result['groups']), 1)
        group = result['groups'][0]
        ids = {group['chair_id'], *group['expert_ids']}
        self.assertEqual(len(ids), 5)
        self.assertEqual(sum(t['is_external'] for t in teachers() if t['id'] in ids and 'is_external' in t), 1)

    def test_unconfirmed_mentor_never_assigned(self):
        staff = teachers()
        staff[0]['availability_confirmed'] = False
        result = generate_schedule(staff, students(2), [], rules())
        self.assertEqual(result['groups'], [])
        self.assertEqual(len(result['unassigned_students']), 2)
        self.assertIn('待确认', result['unassigned_students'][0]['reason'])

    def test_positive_availability_and_negative_time_both_apply(self):
        staff = teachers()
        staff[0].update(available_windows=['2026-11-02 08:00-18:00'], availability_restricted=True,
                        available_time=['2026-11-02 08:00-12:00'])
        result = generate_schedule(staff, students(2), [], rules())
        self.assertEqual(len(result['groups']), 1)
        self.assertIn('14:00', result['groups'][0]['time'])

    def test_no_external_falls_back_to_internal(self):
        staff = teachers()
        staff[2]['availability_confirmed'] = False
        result = generate_schedule(staff, students(2), [], rules())
        self.assertEqual(len(result['groups']), 1)
        self.assertTrue(any(c['type'] == 'external_distribution' for c in result['conflicts']))

    def test_formal_supervisor_avoidance(self):
        result = generate_schedule(teachers(), students(2), [], rules('formal'))
        self.assertEqual(len(result['groups']), 1)
        group = result['groups'][0]
        self.assertNotIn(1, {group['chair_id'], *group['expert_ids']})

    def test_partial_repair_splits_incompatible_mentor_windows(self):
        staff = teachers()
        staff[0].update(available_time=['2026-11-02 14:00-18:00'])
        staff[1].update(available_time=['2026-11-02 08:00-12:00'])
        cohort = students(2)
        cohort[1].update(supervisor_id=2)
        for student in cohort:
            student['previous_group_id'] = 'old'
        config = rules()
        result = generate_schedule(staff, cohort, [], config)
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len(result['groups']), 2)

    def test_manual_validation_detects_overlap_and_excess_experts(self):
        slot = parse_time_range('2026-11-02 09:00-12:00')
        groups = [GroupDraft('A', '创新港', [1], slot, None, 1, [2, 3, 4], 7),
                  GroupDraft('B', '创新港', [2], slot, None, 2, [3, 4], 7)]
        conflicts = detect_global_conflicts(groups, [parse_student(s) for s in students(2)], [parse_teacher(t) for t in teachers()], [], rules())
        self.assertTrue(any(c['type'] == 'teacher_time_conflict' for c in conflicts))
        self.assertTrue(any(c['type'] == 'expert_count_out_of_range' for c in conflicts))
        self.assertFalse(any('room' in c['type'] for c in conflicts))

    def test_rules_remain_identical_when_normalized_again(self):
        config = normalize_schedule_rules(rules('formal', 5))
        self.assertEqual(normalize_schedule_rules(config), config)

    def test_multiple_mentor_students_no_longer_require_special_remark(self):
        config = {**rules(), 'group_size': 4, 'group_max': 4}
        ordinary = generate_schedule(teachers(), students(4), [], config)
        self.assertEqual([len(g['student_ids']) for g in ordinary['groups']], [4])
        staff = teachers()
        staff[0]['allow_multiple_students'] = True
        combined = generate_schedule(staff, students(4), [], config)
        self.assertEqual([len(g['student_ids']) for g in combined['groups']], [4])

    def test_inactive_reviewer_is_never_selected(self):
        staff = teachers()
        staff[2]['is_active'] = False
        result = generate_schedule(staff, students(2), [], rules())
        self.assertEqual(len(result['groups']), 1)
        self.assertNotIn(3, {result['groups'][0]['chair_id'], *result['groups'][0]['expert_ids']})

    def test_five_does_not_fill_internal_supplemental_seats_with_externals(self):
        staff = teachers()
        for teacher in staff:
            if teacher['id'] in (4, 5, 6):
                teacher['is_external'] = True
        result = generate_schedule(staff, students(2), [], rules('formal', 5))
        self.assertEqual(result['groups'], [])
        self.assertEqual(len(result['unassigned_students']), 2)

    def test_conflicting_student_pair_is_locally_repaired(self):
        staff = teachers()
        staff[2]['is_external'] = True
        staff[3]['is_external'] = True
        cohort = students(2)
        cohort[0].update(supervisor_id=3, previous_group_id='old')
        cohort[1].update(supervisor_id=4, previous_group_id='old')
        result = generate_schedule(staff, cohort, [], rules(count=5))
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len(result['groups']), 2)
        self.assertFalse(any(c['type'] == 'expert_count_out_of_range' for c in result['conflicts']))


class CurrentSchedulingAPITests(TestCase):
    def test_search_limit_warning_survives_response_and_conflict_recheck(self):
        from unittest.mock import patch
        from scheduling.personnel_first import PersonnelPlanner
        with patch.object(PersonnelPlanner, 'MAX_SEARCH_NODES', 0):
            response = self.client.post('/api/schedule/generate-linked/',
                {'pre_rules': rules(), 'formal_rules': rules('formal')}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['pre']['unassignedStudents'])
        self.assertTrue(any(c['type'] == '排期搜索范围提示' and c['level'] == 'warning'
                            for c in response.data['pre']['conflicts']))
        refreshed = self.client.get('/api/schedule/current/', {'defense_type': 'pre'})
        self.assertTrue(any(c['type'] == '排期搜索范围提示' for c in refreshed.data['conflicts']))

    def setUp(self):
        user = get_user_model().objects.create_user('current-admin', is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(user)
        for raw in teachers():
            Teacher.objects.create(id=raw['id'], name=raw['name'], title=raw['title'],
                roles=raw['roles'], is_external=raw.get('is_external', False), availability_confirmed=True)
        # Rotation requires a disjoint pool beyond the original reviewers.
        for i in range(8, 14):
            Teacher.objects.create(id=i, name=f'轮换教师{i}', title='教授', roles=['普通专家'], availability_confirmed=True)
        for raw in students(6):
            Student.objects.create(id=raw['id'], name=raw['name'], mentor_id=raw['supervisor_id'],
                mentor_name=f"教师{raw['supervisor_id']}",
                defense_types=['预答辩', '正式答辩'])

    def test_linked_generation_without_classrooms(self):
        response = self.client.post('/api/schedule/generate-linked/', {'pre_rules': rules(), 'formal_rules': rules('formal'), 'request_key': 'policy-three'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        for stage in ('pre', 'formal'):
            self.assertEqual(response.data[stage]['allocationStatus'], 'scheduled')
            self.assertEqual(response.data[stage]['unassignedStudents'], [])
            self.assertEqual(len(response.data[stage]['groups']), 1)
            self.assertEqual(response.data[stage]['rules']['expert_count'], 5 if stage == 'formal' else 3)
        retry = self.client.post('/api/schedule/generate-linked/', {'pre_rules': rules(), 'formal_rules': rules('formal'), 'request_key': 'policy-three'}, format='json')
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data['pre']['versionId'], response.data['pre']['versionId'])

    def test_missing_mentor_does_not_block_other_students(self):
        Student.objects.create(name='缺失导师学生', defense_types=['预答辩', '正式答辩'])
        response = self.client.post('/api/schedule/generate-linked/', {'pre_rules': rules(), 'formal_rules': rules('formal')}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['pre']['unassignedStudents']), 1)
        self.assertEqual(len(response.data['pre']['groups'][0]['students']), 6)

    def test_adapter_executes_remark_and_structured_time(self):
        Teacher.objects.filter(pk=1).update(remark='允许同组安排多名该教师负责的学生', available_times='周一下午', availability_confirmed=False)
        from datetime import date
        payload, _ = build_algorithm_input('pre', (date(2026, 11, 2), date(2026, 11, 2)), rules())
        teacher = next(t for t in payload['teachers'] if t['id'] == 1)
        self.assertTrue(teacher['allow_multiple_students'])
        self.assertTrue(teacher['available_windows'])
        self.assertTrue(teacher['availability_restricted'])

    def test_new_rule_configuration_saves_both_supported_counts(self):
        for count in (3, 5):
            response = self.client.post('/api/rule-config/', {'defense_type': 'pre', 'policyVersion': 3,
                'expertCount': {'target': count, 'min': count}}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['expertCount']['max'], count)
        rejected = self.client.post('/api/rule-config/', {'defense_type': 'pre', 'policyVersion': 3,
            'expertCount': {'target': 4, 'min': 4}}, format='json')
        self.assertEqual(rejected.status_code, 400)

    def test_affiliation_migration_and_import_use_confirmed_fields(self):
        from django.apps import apps
        from importlib import import_module
        from .services.reference_data import correct_imported_affiliation
        software = Teacher.objects.create(name='王飞（软）', title='教授', is_external=True)
        external = Teacher.objects.create(name='王飞', title='教授', is_external=False)
        migration = import_module('api.migrations.0012_current_scheduling')
        migration.correct_affiliations(apps, None)
        software.refresh_from_db()
        external.refresh_from_db()
        self.assertFalse(software.is_external)
        self.assertTrue(external.is_external)
        self.assertFalse(correct_imported_affiliation({'name': software.name, 'isExternal': True})['isExternal'])
        self.assertTrue(correct_imported_affiliation({'name': external.name, 'isExternal': False})['isExternal'])

    def test_negated_or_mixed_remark_is_not_silently_executed(self):
        Teacher.objects.filter(pk=1).update(remark='不允许同组安排多名；下午不能到场')
        payload, notices = build_algorithm_input('pre', rules=rules())
        teacher = next(t for t in payload['teachers'] if t['id'] == 1)
        self.assertFalse(teacher['allow_multiple_students'])
        self.assertTrue(any(c['type'] == 'remark_confirmation' for c in notices))

    def test_no_staff_still_reports_every_student_as_unassigned(self):
        Teacher.objects.all().update(is_active=False)
        response = self.client.post('/api/schedule/generate-linked/', {'pre_rules': rules(), 'formal_rules': rules('formal')}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['pre']['unassignedStudents']), 6)
        self.assertEqual(response.data['pre']['groups'], [])

    def test_new_personnel_only_version_can_publish_and_export(self):
        generated = self.client.post('/api/schedule/generate-linked/', {'pre_rules': rules(), 'formal_rules': rules('formal')}, format='json')
        self.assertEqual(generated.status_code, 200, generated.data)
        pre = generated.data['pre']
        published = self.client.post('/api/schedule/publish/', {'version_id': pre['versionId'], 'expected_revision': pre['revision']}, format='json')
        self.assertEqual(published.status_code, 200, published.data)
        exported = self.client.get('/api/schedule/export/', {'version_id': pre['versionId'], 'defense_type': 'pre'})
        self.assertEqual(exported.status_code, 200)

    def test_adjusting_personnel_only_group_does_not_require_a_room(self):
        generated = self.client.post('/api/schedule/generate-linked/', {'pre_rules': rules(), 'formal_rules': rules('formal')}, format='json')
        pre = generated.data['pre']
        group = pre['groups'][0]
        adjusted = self.client.post('/api/schedule/adjust-group/', {'group_id': group['id'],
            'expected_revision': pre['revision'], 'group_data': group}, format='json')
        self.assertEqual(adjusted.status_code, 200, adjusted.data)


class ClarifiedRequirementsTests(SimpleTestCase):
    def test_each_mentor_gets_two_students_in_one_six_student_panel(self):
        cohort = []
        for mentor in (1, 2, 3):
            for _ in range(2):
                cohort.append(dict(id=len(cohort)+1, name='S', supervisor_id=mentor, campus='创新港'))
        result = generate_schedule(teachers(), cohort, [], rules())
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual([len(g['student_ids']) for g in result['groups']], [6])
        self.assertEqual({result['groups'][0]['chair_id'], *result['groups'][0]['expert_ids']}, {1, 2, 3})

    def test_five_students_share_one_panel_without_an_exception(self):
        result = generate_schedule(teachers(), students(5), [], rules())
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual([len(g['student_ids']) for g in result['groups']], [5])
        self.assertFalse(any(c['type'] == 'student_group_exception' for c in result['conflicts']))

    def test_two_external_mentors_are_always_in_separate_panels(self):
        staff = teachers()
        staff[1]['is_external'] = True
        cohort = students(4)
        for index, s in enumerate(cohort):
            s['supervisor_id'] = 2 if index < 2 else 3
            s['previous_group_id'] = 'old'
        result = generate_schedule(staff, cohort, [], rules())
        self.assertEqual(result['unassigned_students'], [])
        for group in result['groups']:
            self.assertLessEqual(sum(t.get('is_external', False) for t in staff
                if t['id'] in {group['chair_id'], *group['expert_ids']}), 1)

    def test_complete_panels_move_to_opposite_half_days_without_losing_people(self):
        from scheduling.personnel_first import PersonnelPlanner, PanelPlan, Demand
        from collections import Counter
        cohort = students(4)
        config = {**rules(), 'end_date': '2026-11-04'}
        planner = PersonnelPlanner([parse_teacher(t) for t in teachers()], [parse_student(s) for s in cohort], config)
        groups = [GroupDraft('A', '创新港', [1, 2], parse_time_range('2026-11-02 09:00-12:00'), None, 1, [2, 3], 7),
                  GroupDraft('B', '创新港', [3, 4], parse_time_range('2026-11-03 09:00-12:00'), None, 1, [2, 3], 7)]
        planner.plans = [PanelPlan(Demand('创新港', Counter({1: 2})), g) for g in groups]
        for group in groups:
            planner.reserve(group.group_id, group.time_slot, {1, 2, 3, 7}, 2)
        planner.compact_attendance()
        self.assertEqual(groups[0].time_slot.start.date(), groups[1].time_slot.start.date())
        self.assertEqual({g.time_slot.start.hour for g in groups}, {9, 14})
        self.assertEqual([g.student_ids for g in groups], [[1, 2], [3, 4]])
        self.assertFalse(any(c['type'] == 'teacher_time_conflict' for c in detect_global_conflicts(
            groups, planner.students, planner.teachers, [], config)))

    def test_afternoon_unavailability_is_respected_during_compaction(self):
        staff = teachers()
        staff[0]['available_time'] = ['2026-11-02 12:00-18:00', '2026-11-03 12:00-18:00']
        result = generate_schedule(staff, students(4), [], {**rules(), 'end_date': '2026-11-03'})
        self.assertEqual(result['unassigned_students'], [])
        self.assertTrue(all('09:00' in g['time'] for g in result['groups']))

    def test_optional_internal_reviewers_rotate_in_paired_visits(self):
        from collections import Counter
        config = {**rules(), 'end_date': '2026-11-06', 'group_size': 2, 'group_max': 2}
        result = generate_schedule(teachers(), students(12), [], config)
        self.assertEqual(result['unassigned_students'], [])
        loads = Counter(tid for group in result['groups'] for tid in group['expert_ids'] if tid != 3)
        counts = [loads[tid] for tid in (2, 4, 5, 6)]
        self.assertLessEqual(max(counts)-min(counts), 2)
        self.assertFalse(any(c['type'] == 'teacher_time_conflict' for c in result['conflicts']))


class ClarifiedLinkedTests(TestCase):
    setUp = CurrentSchedulingAPITests.setUp

    def test_formal_rotates_an_unavailable_original_reviewer(self):
        Teacher.objects.filter(pk=1).update(unavailable_times='2026-11-03 00:00-23:59')
        response = self.client.post('/api/schedule/generate-linked/', {
            'pre_rules': rules(), 'formal_rules': rules('formal', 5)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['pre']['groups']), 1)
        self.assertEqual(len(response.data['formal']['groups']), 1)
        self.assertEqual(response.data['formal']['unassignedStudents'], [])

    def test_rotation_passes_fresh_validation_and_publish(self):
        Teacher.objects.filter(pk=1).update(title='副教授')
        response = self.client.post('/api/schedule/generate-linked/', {
            'pre_rules': rules(), 'formal_rules': rules('formal', 5)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        formal = response.data['formal']
        self.assertEqual(formal['unassignedStudents'], [])
        refreshed = self.client.get('/api/schedule/current/', {'defense_type': 'formal'})
        self.assertFalse(any(c['level'] == 'error' for c in refreshed.data['conflicts']), refreshed.data)
        published = self.client.post('/api/schedule/publish/', {'version_id': formal['versionId'],
            'expected_revision': formal['revision']}, format='json')
        self.assertEqual(published.status_code, 200, published.data)

    def test_client_cannot_inject_translation_exceptions(self):
        raw = {**rules('formal'), 'linked_translation': True, 'formal_rotation': True, 'formal_group_order': False, 'source_chair_title': '讲师'}
        normalized = normalize_schedule_rules(raw)
        self.assertNotIn('linked_translation', normalized)
        self.assertNotIn('source_chair_title', normalized)
        self.assertNotIn('formal_rotation', normalized)
        self.assertNotIn('formal_group_order', normalized)

    def test_formal_retains_students_secretary_and_rotates_all_reviewers(self):
        response = self.client.post('/api/schedule/generate-linked/', {
            'pre_rules': rules(), 'formal_rules': rules('formal', 5), 'request_key': 'translate'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        pre, formal = response.data['pre'], response.data['formal']
        self.assertEqual(formal['unassignedStudents'], [])
        self.assertEqual(len(pre['groups']), len(formal['groups']))
        from api.models import ScheduleVersion
        left = ScheduleVersion.objects.get(pk=pre['versionId']).groups.get()
        right = ScheduleVersion.objects.get(pk=formal['versionId']).groups.get()
        self.assertEqual(set(left.students.values_list('id', flat=True)), set(right.students.values_list('id', flat=True)))
        self.assertEqual(left.secretary_id, right.secretary_id)
        core = {left.chair_id, *left.experts.values_list('id', flat=True)}
        expanded = {right.chair_id, *right.experts.values_list('id', flat=True)}
        self.assertFalse(core & expanded)
        self.assertNotIn(1, expanded)
        self.assertEqual(len(expanded), 5)
        self.assertLessEqual(Teacher.objects.filter(pk__in=expanded, is_external=True).count(), 1)
        retry = self.client.post('/api/schedule/generate-linked/', {
            'pre_rules': rules(), 'formal_rules': rules('formal', 5), 'request_key': 'translate'}, format='json')
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data['formal']['versionId'], formal['versionId'])


class RealRosterRegressionTests(TestCase):
    def test_legacy_blank_times_can_plan_without_falsely_confirming_availability(self):
        for raw in teachers():
            Teacher.objects.create(id=raw['id'], name=raw['name'], title=raw['title'],
                roles=raw['roles'], is_external=raw.get('is_external', False))
        Student.objects.create(name='S', mentor_id=1, mentor_name='教师1', campus='创新港', defense_types=['预答辩'])
        from datetime import date
        payload, notices = build_algorithm_input('pre', (date(2026,11,2), date(2026,11,2)), rules())
        result = generate_schedule(**payload, rules=rules())
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len(result['groups']), 1)
        self.assertTrue(any(n['type'] == 'availability_pending' for n in notices))
        self.assertFalse(Teacher.objects.filter(availability_confirmed=True).exists())
        self.assertTrue(all(not t['availability_confirmed'] for t in payload['teachers']))

    def test_chairs_do_not_overbook_the_only_secretary(self):
        staff = teachers() + [dict(id=i, name=f'T{i}', title='教授', roles=['专家'],
                                  availability_confirmed=True) for i in range(8, 20)]
        cohort = students(3)
        cohort[1]['supervisor_id'] = 2
        cohort[2]['supervisor_id'] = 4
        config = {**rules(), 'group_size': 1, 'group_max': 1, 'end_date': '2026-11-03'}
        result = generate_schedule(staff, cohort, [], config)
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len({g['time'] for g in result['groups']}), 3)
