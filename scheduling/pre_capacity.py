"""Exact necessary bounds for three-reviewer pre-defense coverage."""
from collections import Counter, defaultdict
from math import ceil

from .policies import pre_chair_is_qualified


def pre_capacity_notices(students, teachers, rules):
    if (rules.get('defense_type') != 'pre' or rules.get('policy_version') != 3
            or rules.get('expert_count') != 3 or rules.get('external_expert_max', 1) != 2):
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
        maximum_groups = total // rules.get('group_min', 1)
        external = {tid: n for tid, n in counts.items() if teacher_map[tid].is_external}
        required_external_visits = sum(ceil(n / rules['group_max']) for n in external.values())
        nonchair_internal = {tid: n for tid, n in counts.items()
                             if not teacher_map[tid].is_external and tid not in chairs}
        if (maximum_groups and required_external_visits == 2 * maximum_groups
                and not chairs.intersection(external) and nonchair_internal):
            description = (
                f'{campus or "未填校区"}现有 {total} 名学生，每组至少 {rules["group_min"]} 人，最多只能开 {maximum_groups} 组；'
                f'外院导师至少需占 {required_external_visits} 个评审席位，因此每组都必须有两位外院导师。'
                f'每组仅三位评审，余下席位必须是合格组长；但该校区另有 {sum(nonchair_internal.values())} 名学生的本院导师未达到组长职称要求。'
                '在现有职称资料和人数限制同时成立时不能覆盖全部学生，请核对职称资料及人数要求；系统未自动更改资料或人数规则。')
            notices.append(make_conflict('pre_group_capacity', description, [], campus=campus,
                                         teacher_ids=list(nonchair_internal)))
    return notices
