"""The user's three-reviewer pre-defense quality contract."""
from django.test import SimpleTestCase
from algorithm import GroupDraft, parse_student, parse_teacher, parse_time_range
from scheduling.current import validate
from .test_current_scheduling import teachers, students


class PreDefenseQualityTests(SimpleTestCase):
    def check_shares(self, counts):
        cohort = students(sum(counts))
        start = 0
        for tid, count in enumerate(counts, 1):
            for student in cohort[start:start + count]:
                student['supervisor_id'] = tid
            start += count
        group = GroupDraft('G001', '创新港', [s['id'] for s in cohort],
                           parse_time_range('2026-11-02 09:00-12:00'), None, 1, [2, 3], 7)
        rules = {'defense_type': 'pre', 'policy_version': 3, 'expert_count': 3,
                 'group_min': 5, 'group_size': 6, 'group_max': 7, 'chair_title': '副教授',
                 'start_date': '2026-11-02', 'end_date': '2026-11-02', 'external_expert_max': 2}
        return validate([group], [parse_student(s) for s in cohort],
                        [parse_teacher(t) for t in teachers()], rules)

    def test_screenshot_skew_is_explicitly_flagged_for_its_group(self):
        for counts in ((4, 2, 0), (5, 1, 0)):
            with self.subTest(counts=counts):
                notices = [c for c in self.check_shares(counts) if c['type'] == 'mentor_student_imbalance']
                self.assertEqual(len(notices), 1)
                self.assertEqual(notices[0]['related_ids'], ['G001'])
                self.assertIn('＋'.join(map(str, counts)), notices[0]['description'])

    def test_balanced_three_reviewer_panel_has_no_share_warning(self):
        for counts in ((2, 2, 2), (2, 2, 1), (3, 2, 2)):
            self.assertFalse(any(c['type'] == 'mentor_student_imbalance' for c in self.check_shares(counts)))

    def test_share_warning_is_a_warning_not_a_hidden_normal_or_hard_conflict(self):
        from api.schedule_views import ScheduleViewSet
        self.assertEqual(ScheduleViewSet.CONFLICT_TYPE_LABELS['mentor_student_imbalance'][1], 'warning')

    def test_exact_capacity_conflict_is_reported_without_silently_changing_roles(self):
        from scheduling.pre_capacity import pre_capacity_notices
        staff = [{'id': tid, 'name': str(tid), 'title': '职称待确认' if tid >= 10 else '讲师' if tid in (2, 3) else '教授', 'roles': ['组长', '专家'] if tid in (1, 4) else ['专家'],
                  'is_external': tid >= 10} for tid in [1, 2, 3, 4, *range(10, 28)]]
        counts = {1: 7, 2: 7, 3: 1, 4: 8, **{tid: 2 if tid < 17 else 1 for tid in range(10, 28)}}
        cohort = []
        for tid, count in counts.items():
            for _ in range(count):
                cohort.append({'id': len(cohort) + 1, 'name': '学生', 'supervisor_id': tid, 'campus': '兴庆'})
        rules = {'policy_version': 3, 'defense_type': 'pre', 'expert_count': 3,
                 'group_min': 5, 'group_max': 7, 'external_expert_max': 2, 'chair_title': '副教授'}
        parsed = [parse_teacher(t) for t in staff]
        notices = pre_capacity_notices([parse_student(s) for s in cohort], parsed, rules)
        self.assertEqual(len(notices), 1)
        self.assertIn('48 名学生', notices[0]['description'])
        self.assertEqual(set(notices[0]['teacher_ids']), {2, 3})
        parsed[1].title = '副教授'
        parsed[2].title = '副教授'
        self.assertEqual(pre_capacity_notices([parse_student(s) for s in cohort], parsed, rules), [])

    def test_associate_professor_without_chair_checkbox_can_chair_pre_defense(self):
        from scheduling.policies import pre_chair_is_qualified
        teacher = parse_teacher({'id': 1, 'name': '导师', 'title': '副教授', 'roles': ['普通专家']})
        self.assertTrue(pre_chair_is_qualified(teacher, {'chair_title': '副教授'}))
        teacher.title = '讲师'
        self.assertFalse(pre_chair_is_qualified(teacher, {'chair_title': '副教授'}))

    def test_pre_generation_uses_three_experts_and_title_qualified_ordinary_mentor(self):
        from algorithm import generate_schedule
        from .test_balanced_pre import rules
        staff, cohort = teachers(), students(6)
        for teacher in staff[:6]:
            teacher.update(title='副教授', roles=['普通专家'])
        for index, student in enumerate(cohort):
            student['supervisor_id'] = index // 2 + 1
        result = generate_schedule(staff, cohort, [], rules())
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(len(result['groups']), 1)
        group = result['groups'][0]
        self.assertEqual(len({group['chair_id'], *group['expert_ids']}), 3)
        self.assertEqual(staff[group['chair_id'] - 1]['roles'], ['普通专家'])
        self.assertFalse(any(c['type'] in {'chair_unavailable', 'mentor_student_imbalance'} for c in result['conflicts']))

    def test_packing_searches_for_a_complete_incumbent_before_quality(self):
        from collections import Counter
        from scheduling.balanced_counts import pack_counts
        teacher = parse_teacher(teachers()[0])
        packed, diagnostics = pack_counts(Counter({1: 11}), 6, 5, 7, 3, 2,
                                          {1: teacher}, {1}, lambda counts: True)
        self.assertEqual(sum(packed, Counter()), Counter({1: 11}))
        self.assertEqual(diagnostics['uncovered'], 0)
        self.assertEqual(diagnostics['coverage_seed'], 'full_cover_search')
        self.assertEqual(diagnostics['preferred_groups'], 2)
        self.assertTrue(diagnostics['group_count_protected'])

    def test_validated_complete_pre_groups_can_seed_a_new_joint_search(self):
        from scheduling.personnel_first import PersonnelPlanner
        from .test_balanced_pre import rules
        cohort = students(13)
        config = {**rules(), 'end_date': '2026-11-03'}
        seed = [GroupDraft('G001', '创新港', list(range(1, 7))),
                GroupDraft('G002', '创新港', list(range(7, 14)))]
        planner = PersonnelPlanner([parse_teacher(t) for t in teachers()],
                                   [parse_student(s) for s in cohort], config, seed_groups=seed)
        result = planner.run()
        self.assertEqual(result['unassigned_students'], [])
        self.assertEqual(sorted(sid for group in result['groups'] for sid in group['student_ids']), list(range(1, 14)))

    def test_six_seven_seat_groups_can_be_jointly_repacked_into_seven_sixes(self):
        from collections import Counter
        from scheduling.compact_counts import repack_sixes
        staff = {t.id: t for t in map(parse_teacher, teachers())}
        original = [Counter({tid: 7}) for tid in range(1, 7)]
        repacked, blocks = repack_sixes(original, 3, 2, staff, set(range(1, 7)), lambda counts: True)
        self.assertEqual(blocks, 1)
        self.assertEqual(len(repacked), 7)
        self.assertTrue(all(sum(c.values()) == 6 and len(c) <= 3 for c in repacked))
        self.assertEqual(sum(repacked, Counter()), sum(original, Counter()))
        rejected, blocks = repack_sixes(original, 3, 2, staff, set(range(1, 7)), lambda counts: False)
        self.assertEqual(blocks, 0)
        self.assertEqual(rejected, original)
