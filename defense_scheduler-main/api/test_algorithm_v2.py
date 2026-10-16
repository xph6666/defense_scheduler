"""Executable requirements for the V2 domain and linked resource planning."""
from datetime import datetime
from collections import Counter

from django.test import SimpleTestCase, TestCase

from algorithm import GroupDraft, SchedulingError, TimeRange, detect_global_conflicts, generate_schedule, parse_room, parse_student, parse_teacher
from scheduling.policies import committee_violations, is_software_teacher, scenario_policy, teacher_can_role


class CommitteeV2Tests(SimpleTestCase):
    def rules(self, kind='pre', **overrides):
        return {
            'defense_type': kind, 'start_date': '2026-10-12', 'end_date': '2026-10-12',
            'group_size': 1, 'expert_count': 5 if kind in ('formal', 'mid') else 4,
            'need_chair': True, 'chair_title': '教授' if kind == 'formal' else '副教授',
            'secretary_title': '讲师', 'expert_count_includes_chair': True,
            **overrides,
        }

    def teachers(self, count=9):
        return [
            {'id': i, 'name': f'T{i}', 'title': '教授', 'roles': ['组长', '主席', '专家', '秘书'],
             'is_software_teacher': i <= 5}
            for i in range(1, count + 1)
        ]

    def generate(self, rules=None, teachers=None, students=None):
        return generate_schedule(
            teachers or self.teachers(), students or [{'id': 1, 'name': 'S1'}],
            [{'id': 1, 'name': 'R1', 'capacity': 30}], rules or self.rules(),
        )

    def check(self, group, teachers=None, rules=None, students=None):
        return detect_global_conflicts(
            [group], [parse_student(s) for s in (students or [{'id': 1, 'name': 'S1'}])],
            [parse_teacher(t) for t in (teachers or self.teachers())],
            [parse_room({'id': 1, 'capacity': 30})], rules or self.rules(),
        )

    def group(self, chair=1, experts=None, secretary=6):
        return GroupDraft('G1', None, [1], TimeRange(datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 12)),
                          1, chair, experts if experts is not None else [2, 3, 4], secretary)

    def test_pre_chair_is_one_of_four_experts(self):
        result = self.generate()
        self.assertEqual(len(result['groups'][0]['expert_ids']), 3)
        self.assertEqual(result['conflicts'], [])

    def test_formal_has_exactly_five_reviewers_including_chair(self):
        result = self.generate(self.rules('formal'))
        group = result['groups'][0]
        self.assertEqual(len(set([group['chair_id'], *group['expert_ids']])), 5)
        self.assertEqual(result['conflicts'], [])

    def test_legacy_expert_count_keeps_ordinary_expert_semantics(self):
        rules = self.rules(expert_count=2)
        rules.pop('expert_count_includes_chair')
        self.assertEqual(len(self.generate(rules)['groups'][0]['expert_ids']), 2)

    def test_formal_manual_edit_cannot_exceed_five_reviewers(self):
        conflicts = self.check(self.group(experts=[2, 3, 4, 5, 7]), rules=self.rules('formal'))
        self.assertIn('expert_count_out_of_range', {c['type'] for c in conflicts})

    def test_formal_requires_software_college_majority(self):
        teachers = self.teachers()
        for teacher in teachers:
            teacher['is_software_teacher'] = teacher['id'] == 1
        conflicts = self.check(self.group(experts=[2, 3, 4, 5]), teachers, self.rules('formal'))
        self.assertIn('software_majority', {c['type'] for c in conflicts})

    def test_generation_prefers_software_college_reviewers(self):
        teachers = self.teachers()
        for teacher in teachers:
            teacher['is_software_teacher'] = teacher['id'] >= 6
        result = self.generate(self.rules('formal'), teachers)
        group = result['groups'][0]
        self.assertGreaterEqual(len(set([group['chair_id'], *group['expert_ids']]) & {6, 7, 8, 9}), 3)

    def test_inactive_teacher_is_never_automatically_assigned(self):
        teachers = self.teachers()
        teachers[0]['is_active'] = False
        group = self.generate(teachers=teachers)['groups'][0]
        self.assertNotIn(1, [group['chair_id'], *group['expert_ids'], group['secretary_id']])

    def test_chair_only_teacher_is_not_ordinary_member(self):
        teachers = self.teachers()
        teachers[0]['roles'] = ['组长']
        teachers[0]['member_eligible'] = False
        group = self.generate(teachers=teachers)['groups'][0]
        self.assertEqual(group['chair_id'], 1)
        self.assertNotIn(1, group['expert_ids'])

    def test_member_exclusion_is_detected_after_manual_edit(self):
        teachers = self.teachers()
        teachers[1]['member_eligible'] = False
        conflicts = self.check(self.group(), teachers)
        self.assertIn('member_ineligible', {c['type'] for c in conflicts})

    def test_role_qualification_is_detected_after_manual_edit(self):
        teachers = self.teachers()
        teachers[1]['roles'] = ['秘书']
        conflicts = self.check(self.group(), teachers)
        self.assertIn('role_qualification', {c['type'] for c in conflicts})

    def test_bound_secretary_is_reserved_before_member_selection(self):
        students = [{'id': 1, 'name': 'S1', 'secretary_id': 2}]
        group = self.generate(students=students)['groups'][0]
        self.assertEqual(group['secretary_id'], 2)

    def test_formal_preserves_previous_group_label(self):
        students = [{'id': 1, 'name': 'S1', 'previous_group_id': 'G8'},
                    {'id': 2, 'name': 'S2', 'previous_group_id': 'G2'}]
        result = self.generate(self.rules('formal', grouping='secretary'), students=students)
        self.assertEqual({g['student_ids'][0]: g['group_id'] for g in result['groups']}, {1: 'G8', 2: 'G2'})

    def test_shortage_remains_an_explicit_draft_conflict(self):
        result = self.generate(self.rules('formal'), self.teachers(4))
        self.assertIn('expert_count_out_of_range', {c['type'] for c in result['conflicts']})

    def test_mid_student_count_is_checked_with_v2_bounds(self):
        conflicts = self.check(self.group(experts=[2, 3, 4, 5]), rules=self.rules('mid', group_min=10, group_max=13))
        self.assertIn('group_size_out_of_range', {c['type'] for c in conflicts})

    def test_additional_required_mentors_choose_a_large_enough_room(self):
        teachers = self.teachers(9)
        students = [{'id': i, 'name': f'S{i}', 'supervisor_id': i} for i in range(1, 9)]
        rooms = [{'id': 1, 'name': 'Small', 'capacity': 13},
                 {'id': 2, 'name': 'Large', 'capacity': 17}]
        rules = self.rules(group_size=8, group_min=8, group_max=8,
                           grouping='supervisor', supervisor_policy='same_group')
        result = generate_schedule(teachers, students, rooms, rules)
        # Eight required mentors plus a separate secretary use nine staff seats,
        # even though the ordinary committee target is only four reviewers.
        self.assertEqual(result['groups'][0]['room_id'], 2)
        self.assertEqual(result['conflicts'], [])

    def test_minority_secretary_binding_is_not_hidden_by_majority(self):
        students = [{'id': i, 'name': f'S{i}', 'secretary_id': 6 if i < 3 else 7}
                    for i in range(1, 4)]
        group = self.group()
        group.student_ids = [1, 2, 3]
        conflicts = self.check(group, students=students)
        continuity = [c for c in conflicts if c['type'] == 'secretary_continuity_broken']
        self.assertEqual(len(continuity), 1)
        self.assertEqual(continuity[0]['teacher_name'], 'T7')
        self.assertIn(3, continuity[0]['related_ids'])

    def test_each_distinct_lost_secretary_binding_is_reported(self):
        students = [{'id': i, 'name': f'S{i}', 'secretary_id': i + 6}
                    for i in range(1, 4)]
        group = self.group()
        group.student_ids = [1, 2, 3]
        conflicts = self.check(group, students=students)
        self.assertEqual({c['teacher_name'] for c in conflicts if c['type'] == 'secretary_continuity_broken'},
                         {'T7', 'T8', 'T9'})


class FormalMentorSessionV2Tests(SimpleTestCase):
    def check(self, second_hour=9):
        rules = {'defense_type': 'formal', 'expert_count': 0, 'need_chair': False,
                 'supervisor_policy': 'avoid', 'formal_mentor_same_session': True}
        students = [parse_student({'id': 1, 'name': 'S1', 'supervisor_id': 1}),
                    parse_student({'id': 2, 'name': 'S2', 'supervisor_id': 2})]
        teachers = [parse_teacher({'id': i, 'name': f'T{i}'}) for i in (1, 2, 3, 4)]
        groups = [
            GroupDraft('G1', None, [1], TimeRange(datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 12)),
                       1, None, [2], 3),
            GroupDraft('G2', None, [2], TimeRange(datetime(2026, 10, 12, second_hour), datetime(2026, 10, 12, second_hour + 3)),
                       2, None, [1], 4),
        ]
        return detect_global_conflicts(groups, students, teachers, [parse_room({'id': 1}), parse_room({'id': 2})], rules)

    def test_mentor_reviews_another_group_while_own_student_attends(self):
        self.assertNotIn('formal_mentor_session_missing', {c['type'] for c in self.check()})

    def test_mentor_and_student_at_different_sessions_is_a_hard_conflict(self):
        self.assertIn('formal_mentor_session_missing', {c['type'] for c in self.check(14)})

    def test_generation_aligns_two_groups_and_rotates_their_mentors(self):
        teachers = [{'id': i, 'name': f'T{i}', 'title': '教授', 'is_software_teacher': True}
                    for i in range(1, 13)]
        students = [{'id': 1, 'name': 'S1', 'supervisor_id': 1},
                    {'id': 2, 'name': 'S2', 'supervisor_id': 2}]
        rules = {'defense_type': 'formal', 'start_date': '2026-10-12', 'end_date': '2026-10-12',
                 'group_size': 1, 'expert_count': 5, 'expert_count_includes_chair': True,
                 'need_chair': True, 'chair_title': '教授', 'secretary_title': '讲师',
                 'supervisor_policy': 'avoid', 'formal_mentor_same_session': True}
        result = generate_schedule(teachers, students, [{'id': 1}, {'id': 2}], rules)
        self.assertEqual(result['conflicts'], [])
        self.assertEqual(result['groups'][0]['time'], result['groups'][1]['time'])
        self.assertIn(2, [result['groups'][0]['chair_id'], *result['groups'][0]['expert_ids']])
        self.assertIn(1, [result['groups'][1]['chair_id'], *result['groups'][1]['expert_ids']])


class ScenarioPolicyV2Tests(SimpleTestCase):
    def test_catalog_scenarios_do_not_share_mutable_configuration(self):
        first = scenario_policy('mid')
        first['studentCount']['target'] = 99
        self.assertEqual(scenario_policy('中期答辩')['studentCount'], {'target': 12, 'min': 10, 'max': 13})

    def test_chair_in_member_list_counts_once_and_uses_chair_qualification(self):
        teachers = [{'id': 1, 'roles': ['组长'], 'member_eligible': False, 'title': '教授'},
                    *[{'id': i, 'title': '副教授'} for i in (2, 3, 4)],
                    {'id': 5, 'title': '讲师'}]
        conflicts = committee_violations(
            {'group_id': 'G1', 'chair_id': 1, 'expert_ids': [1, 2, 3, 4], 'secretary_id': 5},
            teachers, {'defense_type': 'pre', 'expert_count_includes_chair': True},
        )
        self.assertEqual(conflicts, [])

    def test_software_flag_adds_to_internal_college_inference(self):
        self.assertTrue(is_software_teacher({'college': '软件学院', 'is_software_teacher': False}))
        self.assertFalse(is_software_teacher({'college': '软件学院', 'is_external': True}))
        self.assertTrue(is_software_teacher({'college': '计算机学院', 'is_software_teacher': True}))

    def test_inactive_camel_case_teacher_and_member_flag_are_respected(self):
        self.assertFalse(teacher_can_role({'isActive': False, 'roles': ['主席']}, 'chair'))
        self.assertFalse(teacher_can_role({'memberEligible': False, 'roles': ['专家']}, 'expert'))


class SchedulingPreferencesV2Tests(SimpleTestCase):
    def external_schedule(self, weight=100, same_day_staff_busy=False):
        teachers = [{'id': i, 'name': f'T{i}', 'title': '教授', 'is_external': i == 1,
                     'available_time': ['2026-10-12 14:00-17:00'] if same_day_staff_busy and i > 1 else []}
                    for i in range(1, 6)]
        students = [{'id': i, 'name': f'S{i}', 'supervisor_id': 1} for i in (1, 2)]
        rooms = [{'id': 1, 'capacity': 30, 'available_time': [
            '2026-10-12 09:00-12:00', '2026-10-13 09:00-12:00', '2026-10-12 14:00-17:00']}]
        rules = {'defense_type': 'pre', 'start_date': '2026-10-12', 'end_date': '2026-10-13',
                 'group_size': 1, 'group_max': 1, 'expert_count': 4, 'expert_count_includes_chair': True,
                 'need_chair': True, 'chair_title': '教授', 'secretary_title': '讲师',
                 'supervisor_policy': 'same_group',
                 'soft_weights': {'external_mentor_concentration': weight}}
        return generate_schedule(teachers, students, rooms, rules)

    def test_external_mentor_prefers_two_feasible_sessions_on_one_day(self):
        result = self.external_schedule()
        self.assertEqual({g['time'].split(' ')[0] for g in result['groups']}, {'2026-10-12'})
        self.assertEqual(result['conflicts'], [])

    def test_disabled_external_preference_keeps_first_feasible_room_slot(self):
        result = self.external_schedule(0)
        self.assertEqual(result['groups'][1]['time'], '2026-10-13 09:00-12:00')

    def test_external_preference_never_overrides_staff_availability(self):
        result = self.external_schedule(same_day_staff_busy=True)
        self.assertEqual(result['groups'][1]['time'], '2026-10-13 09:00-12:00')
        self.assertEqual({c['type'] for c in result['conflicts']}, {'external_mentor_concentration'})

    def software_schedule(self, balance):
        teachers = [{'id': i, 'name': f'T{i}', 'title': '教授', 'is_software_teacher': True,
                     'roles': ['主席', '专家']} for i in range(1, 9)]
        teachers.append({'id': 9, 'name': 'Secretary', 'title': '讲师', 'roles': ['秘书']})
        students = [{'id': i, 'name': f'S{i}'} for i in range(1, 4)]
        rules = {'defense_type': 'formal', 'start_date': '2026-10-12', 'end_date': '2026-10-13',
                 'group_size': 1, 'expert_count': 5, 'expert_count_includes_chair': True,
                 'need_chair': True, 'chair_title': '教授', 'secretary_title': '讲师',
                 'soft_weights': {'balance_software_participation': balance}}
        return generate_schedule(teachers, students, [{'id': 1}], rules)

    def test_software_reviewers_rotate_with_at_most_one_count_difference(self):
        result = self.software_schedule(100)
        loads = Counter(tid for group in result['groups'] for tid in [group['chair_id'], *group['expert_ids']])
        self.assertLessEqual(max(loads[i] for i in range(1, 9)) - min(loads[i] for i in range(1, 9)), 1)
        self.assertEqual(result['conflicts'], [])

    def test_disabled_software_balance_keeps_stable_candidate_order(self):
        result = self.software_schedule(0)
        self.assertEqual([group['chair_id'] for group in result['groups']], [1, 1, 1])


class CampusStartDatesV2Tests(SimpleTestCase):
    def generate(self, dates):
        teachers = [{'id': i, 'name': f'T{i}', 'title': '教授'} for i in range(1, 7)]
        students = [{'id': i, 'name': f'S{i}', 'campus': '兴庆' if i <= 10 else '创新港'}
                    for i in range(1, 21)]
        rooms = [{'id': 1, 'campus': '创新港', 'capacity': 30},
                 {'id': 2, 'campus': '兴庆', 'capacity': 30}]
        rules = {'defense_type': 'mid', 'start_date': '2026-10-12', 'end_date': '2026-10-13',
                 'group_size': 12, 'group_min': 10, 'group_max': 13, 'grouping': 'supervisor',
                 'expert_count': 5, 'expert_count_includes_chair': True,
                 'need_chair': True, 'chair_title': '副教授', 'secretary_title': '讲师',
                 'campus_start_dates': dates}
        return generate_schedule(teachers, students, rooms, rules)

    def test_two_campuses_can_start_on_different_dates(self):
        result = self.generate({'创新港': '2026-10-13', '兴庆': '2026-10-12'})
        self.assertEqual({group['campus']: group['time'].split(' ')[0] for group in result['groups']},
                         {'创新港': '2026-10-13', '兴庆': '2026-10-12'})
        self.assertEqual(result['conflicts'], [])

    def test_unspecified_campus_keeps_global_start_date(self):
        result = self.generate({'创新港': '2026-10-13'})
        self.assertEqual({group['campus']: group['time'].split(' ')[0] for group in result['groups']},
                         {'创新港': '2026-10-13', '兴庆': '2026-10-12'})

    def test_invalid_campus_dates_are_rejected_before_scheduling(self):
        for dates in ({'未知校区': '2026-10-12'}, {'兴庆': '2026-02-31'},
                      {'兴庆': '2026-10-11'}, {'兴庆': '2026-10-14'}, ['2026-10-12']):
            with self.subTest(dates=dates), self.assertRaises(SchedulingError):
                self.generate(dates)

    def test_manual_time_before_campus_start_is_reported(self):
        group = GroupDraft('G1', '创新港', [1],
                           TimeRange(datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 12)),
                           1, 1, [2, 3, 4, 5], 6)
        rules = {'defense_type': 'mid', 'start_date': '2026-10-12', 'end_date': '2026-10-13',
                 'expert_count': 5, 'expert_count_includes_chair': True,
                 'need_chair': True, 'chair_title': '副教授', 'secretary_title': '讲师',
                 'campus_start_dates': {'创新港': '2026-10-13'}}
        conflicts = detect_global_conflicts([group], [parse_student({'id': 1, 'campus': '创新港'})],
                    [parse_teacher({'id': i, 'title': '教授'}) for i in range(1, 7)],
                    [parse_room({'id': 1, 'campus': '创新港'})], rules)
        self.assertTrue(any(c['type'] == 'room_or_time_unavailable' and '校区' in c['description'] for c in conflicts))


class LinkedResourcePlanningV2Tests(SimpleTestCase):
    def generate_linked(self, old_secretary=None, external_mentor=False):
        teachers = [{'id': i, 'name': f'T{i:02}', 'title': '教授', 'college': '软件学院',
                     'is_software_teacher': True, 'roles': ['主席', '组长', '普通专家', '秘书']}
                    for i in range(1, 15)]
        if external_mentor:
            teachers[1].update(title='讲师', college='外院', is_external=True, is_software_teacher=False)
        students = [{'id': i, 'name': f'S{i:02}', 'campus': '创新港',
                     'supervisor_id': 1 if i <= 6 else 2, 'secretary_id': old_secretary}
                    for i in range(1, 13)]
        rooms = [{'id': i, 'campus': '创新港', 'capacity': 30} for i in (1, 2)]
        rules = {'defense_type': 'pre', 'start_date': '2026-10-12', 'end_date': '2026-10-12',
                 'group_size': 6, 'group_min': 4, 'group_max': 8, 'expert_count': 4,
                 'expert_count_includes_chair': True, 'need_chair': True, 'chair_title': '副教授',
                 'secretary_title': '讲师', 'supervisor_policy': 'same_group', 'grouping': 'supervisor',
                 'prefer_senior': True, 'policy_version': 2,
                 'reserve_formal_resources': True, 'refresh_secretary_bindings': True}
        pre = generate_schedule(teachers, students, rooms, rules)
        formal_students = []
        for group in pre['groups']:
            formal_students.extend({**student, 'secretary_id': group['secretary_id'],
                                    'previous_group_id': group['group_id']}
                                   for student in students if student['id'] in group['student_ids'])
        formal = generate_schedule(teachers, formal_students, rooms, {
            **rules, 'defense_type': 'formal', 'start_date': '2026-10-13', 'end_date': '2026-10-13',
            'expert_count': 5, 'chair_title': '教授', 'supervisor_policy': 'avoid',
            'grouping': 'secretary', 'formal_mentor_same_session': True})
        return pre, formal

    def assert_valid_linked(self, pre, formal):
        self.assertEqual(pre['conflicts'], [])
        self.assertEqual(formal['conflicts'], [])
        self.assertEqual(len({g['secretary_id'] for g in pre['groups']}), 2)
        self.assertFalse({1, 2} & {g['secretary_id'] for g in pre['groups']})
        self.assertEqual(len({g['time'] for g in formal['groups']}), 1)
        self.assertEqual(len({g['room_id'] for g in formal['groups']}), 2)
        self.assertEqual({g['group_id']: g['student_ids'] for g in pre['groups']},
                         {g['group_id']: g['student_ids'] for g in formal['groups']})

    def test_twelve_students_keep_secretaries_and_mentors_in_one_formal_session(self):
        self.assert_valid_linked(*self.generate_linked())

    def test_explicit_replanning_refreshes_a_shared_old_secretary(self):
        self.assert_valid_linked(*self.generate_linked(old_secretary=14))

    def test_less_senior_external_mentor_still_gets_a_formal_review_seat(self):
        self.assert_valid_linked(*self.generate_linked(external_mentor=True))


class LinkedResourceServiceV2Tests(TestCase):
    def test_linked_replan_after_published_shared_secretary_is_valid_and_keeps_history(self):
        from django.contrib.auth.models import User
        from rest_framework.test import APIClient
        from .models import Group, Room, ScheduleVersion, Student, Teacher
        from .schedule_integrity import export_groups

        client = APIClient()
        client.force_authenticate(User.objects.create_user('resource-planner', is_staff=True))
        teachers = [Teacher.objects.create(name=f'T{i:02}', title='教授', college='软件学院',
                    roles=['主席', '组长', '普通专家', '秘书']) for i in range(1, 15)]
        students = [Student.objects.create(name=f'S{i:02}', student_no=f'LINKED{i}', campus='创新港',
                    mentor=teachers[0 if i <= 6 else 1], bound_secretary=teachers[-1],
                    defense_types=['预答辩', '正式答辩']) for i in range(1, 13)]
        rooms = [Room.objects.create(name=f'R{i}', campus='创新港', capacity=30) for i in (1, 2)]
        pre_rules = {'defense_type': 'pre', 'policy_version': 2,
                     'start_date': '2026-10-12', 'end_date': '2026-10-12'}
        from .services.rules import normalize_schedule_rules
        old = ScheduleVersion.objects.create(defense_type='pre', rules_snapshot=normalize_schedule_rules(pre_rules))
        for index, time in enumerate(('09:00-12:00', '14:00-17:00')):
            group = Group.objects.create(schedule_version=old, group_id=f'G{index + 1}',
                        time=f'2026-10-12 {time}', campus='创新港', room=rooms[0],
                        chair=teachers[index], secretary=teachers[-1])
            group.experts.set([t for t in teachers[:4] if t.pk != teachers[index].pk])
            group.students.set(students[index * 6:(index + 1) * 6])
        published = client.post('/api/schedule/publish/',
                               {'version_id': old.pk, 'expected_revision': 0}, format='json')
        self.assertEqual(published.status_code, 200, published.data)
        response = client.post('/api/schedule/generate-linked/', {
            'pre_rules': pre_rules,
            'formal_rules': {'defense_type': 'formal', 'policy_version': 2,
                            'start_date': '2026-10-13', 'end_date': '2026-10-13'},
            'request_key': 'shared-secretary-replan'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        for stage in ('pre', 'formal'):
            self.assertFalse([c for c in response.data[stage]['conflicts'] if c['level'] == 'error'], response.data)
        self.assertEqual(len({g['secretaryId'] for g in response.data['pre']['groups']}), 2)
        self.assertEqual(len({(g['date'], g['timeRange']) for g in response.data['formal']['groups']}), 1)
        old.refresh_from_db()
        self.assertEqual(old.status, 'published')
        self.assertFalse(old.is_current)
        self.assertEqual({s.bound_secretary_id for g in export_groups(old) for s in g.students.all()}, {teachers[-1].pk})


class FormalSecretaryExportV2Tests(TestCase):
    def setUp(self):
        from .models import Group, ScheduleVersion, Student, Teacher
        from .schedule_integrity import capture_export_groups

        self.old_secretary = Teacher.objects.create(name='预答辩原秘书', title='讲师', roles=['秘书'])
        self.formal_secretary = Teacher.objects.create(name='正式答辩改选秘书', title='讲师', roles=['秘书'])
        self.later_secretary = Teacher.objects.create(name='下一轮预答辩秘书', title='讲师', roles=['秘书'])
        self.student = Student.objects.create(name='版本秘书学生', student_no='FORMAL-SECRETARY',
            campus='创新港', defense_types=['预答辩', '正式答辩'],
            bound_secretary=self.old_secretary, secretary_name=self.old_secretary.name)
        self.source = ScheduleVersion.objects.create(defense_type='pre', is_current=False)
        source_group = Group.objects.create(schedule_version=self.source, group_id='G1',
            campus='创新港', time='2026-10-12 09:00-12:00', secretary=self.old_secretary)
        source_group.students.add(self.student)
        self.source.export_snapshot = capture_export_groups(self.source)
        self.source.save(update_fields=['export_snapshot'])
        self.version = ScheduleVersion.objects.create(defense_type='formal', source_pre_version=self.source,
            input_snapshot={'students': [{'id': self.student.pk,
                'secretary_id': self.formal_secretary.pk, 'previous_group_id': 'G1'}]})
        self.group = Group.objects.create(schedule_version=self.version, group_id='G1',
            campus='创新港', time='2026-10-13 09:00-12:00', secretary=self.formal_secretary)
        self.group.students.add(self.student)

    def presentation_student(self):
        from unittest.mock import patch
        from .schedule_views import ScheduleViewSet

        view = ScheduleViewSet()
        with patch.object(view, '_check_conflicts', return_value=[]):
            return view._version_result(self.version)['groups'][0]['students'][0]

    def assert_student_binding(self, secretary_id, secretary_name):
        from .schedule_integrity import capture_export_groups, export_groups

        student = export_groups(self.version)[0].students.all()[0]
        self.assertEqual(student.bound_secretary_id, secretary_id)
        self.assertEqual(student.secretary_name, secretary_name)
        captured = capture_export_groups(self.version)[0]['students'][0]
        self.assertEqual(captured['bound_secretary_id'], secretary_id)
        self.assertEqual(captured['secretary_name'], secretary_name)
        displayed = self.presentation_student()
        self.assertEqual(displayed['secretaryId'], secretary_id)
        self.assertEqual(displayed['secretaryName'], secretary_name)

    def test_explicit_formal_binding_is_used_without_writing_global_student(self):
        self.assert_student_binding(self.formal_secretary.pk, self.formal_secretary.name)
        self.student.refresh_from_db()
        self.assertEqual(self.student.bound_secretary_id, self.old_secretary.pk)
        self.assertEqual(self.student.secretary_name, self.old_secretary.name)

    def test_later_pre_rebinding_does_not_change_formal_or_frozen_source_view(self):
        from .models import Student
        from .schedule_integrity import export_groups

        Student.objects.filter(pk=self.student.pk).update(bound_secretary=self.later_secretary,
            secretary_name=self.later_secretary.name)
        self.assert_student_binding(self.formal_secretary.pk, self.formal_secretary.name)
        source_student = export_groups(self.source)[0].students.all()[0]
        self.assertEqual(source_student.bound_secretary_id, self.old_secretary.pk)
        self.assertEqual(source_student.secretary_name, self.old_secretary.name)

    def test_explicit_empty_formal_binding_does_not_fall_back_to_global_secretary(self):
        self.version.input_snapshot['students'][0]['secretary_id'] = None
        self.assert_student_binding(None, '')

    def test_missing_snapshot_teacher_keeps_invalid_id_visible_to_validation(self):
        from .schedule_views import ScheduleViewSet

        missing_id = self.later_secretary.pk + 1000
        self.version.input_snapshot['students'][0]['secretary_id'] = missing_id
        self.assert_student_binding(missing_id, '')
        conflicts = ScheduleViewSet()._check_conflicts(self.version)
        self.assertTrue(any(c['type'] == 'secretary_not_found' for c in conflicts), conflicts)

    def test_frozen_formal_export_does_not_reproject_changed_bindings(self):
        from .models import Student
        from .schedule_integrity import capture_export_groups

        self.version.export_snapshot = capture_export_groups(self.version)
        self.version.status = 'published'
        self.version.save(update_fields=['export_snapshot', 'status'])
        self.version.input_snapshot['students'][0]['secretary_id'] = None
        Student.objects.filter(pk=self.student.pk).update(bound_secretary=self.later_secretary,
            secretary_name=self.later_secretary.name)
        self.assert_student_binding(self.formal_secretary.pk, self.formal_secretary.name)

    def test_legacy_formal_snapshot_without_binding_keeps_existing_student_view(self):
        del self.version.input_snapshot['students'][0]['secretary_id']
        self.assert_student_binding(self.old_secretary.pk, self.old_secretary.name)
