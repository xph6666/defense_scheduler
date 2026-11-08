"""Necessary mentor-seat bounds, independent of available dates."""
from collections import Counter, defaultdict
from math import ceil

from .policies import pre_chair_is_qualified, committee_size


def pre_capacity_notices(students, teachers, rules):
    if rules.get('defense_type') != 'pre' or rules.get('policy_version', 1) < 3:
        return []
    from algorithm import make_conflict
    teacher_map = {t.id: t for t in teachers}
    chairs = {t.id for t in teachers if pre_chair_is_qualified(t, rules)}
    cohorts = defaultdict(Counter)
    for student in students:
        cohorts[student.campus][student.supervisor_id] += 1
    notices = []
    for campus, counts in cohorts.items():
        if any(t not in teacher_map for t in counts):
            continue
        total = sum(counts.values())
        experts = committee_size(rules, campus)
        maximum_groups = total // rules.get('group_min', 1)
        visits = {tid: ceil(n / rules['group_max']) for tid, n in counts.items()}
        nonchairs = sum(n for tid, n in visits.items() if tid not in chairs)
        external = sum(n for tid, n in visits.items() if teacher_map[tid].is_external)
        minimum_groups = max(ceil(nonchairs / max(1, experts - 1)),
                             ceil(external / max(1, rules.get('external_expert_max', 1))),
                             ceil(total / rules['group_max']))
        if minimum_groups <= maximum_groups:
            continue
        description = (
            f'{campus or "未填校区"}现有 {total} 名学生；{nonchairs} 个必需导师评审席位不能由合格组长兼任。'
            f'每组 {experts} 位评审扣除组长后有 {experts - 1} 个席位，结合外院上限至少需要 {minimum_groups} 组；'
            f'每组至少 {rules["group_min"]} 名学生，最多只能开 {maximum_groups} 组。'
            '这是导师席位与学生人数下限冲突，延长日期不能消除该人数矛盾。'
            + ('可尝试将本校区改为 5 位评审，并重新校验时间和资格。' if experts == 3 else '请核对参排名单、职称及人数要求。'))
        affected = [tid for tid in counts if tid not in chairs]
        # When external mentors already occupy every allowed external seat,
        # highlight the internal non-chair mentors that cannot fit the last seat.
        internal = [tid for tid in affected if not teacher_map[tid].is_external]
        if internal and external == maximum_groups * rules.get('external_expert_max', 1) and not any(
                teacher_map[tid].is_external for tid in chairs):
            affected = internal
        notices.append(make_conflict('pre_group_capacity', description, [], campus=campus,
            teacher_ids=affected,
            minimum_groups=minimum_groups, maximum_groups=maximum_groups, expert_count=experts))
    return notices
