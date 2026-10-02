"""Travel and reviewer workload preferences; none is a feasibility constraint."""
from collections import defaultdict

from .policies import is_software_teacher, scenario_policy, teacher_can_role


_WEIGHT_NAMES = {
    'external_mentor_concentration': 'externalMentorConcentration',
    'balance_software_participation': 'balanceSoftwareParticipation',
}


def preference_weight(rules, name, default=0):
    """Use explicit engine weights, then the shared V2 scenario defaults."""
    camel_name = _WEIGHT_NAMES[name]
    weights = rules.get('soft_weights') or rules.get('softWeights') or {}
    value = weights.get(name, weights.get(camel_name))
    if value is None and (rules.get('policy_version', 1) >= 2 or rules.get('expert_count_includes_chair')):
        try:
            value = scenario_policy(rules.get('defense_type', 'pre'))['softWeights'].get(camel_name, default)
        except ValueError:
            value = default
    try:
        return max(0, min(100, int(value if value is not None else default)))
    except (TypeError, ValueError):
        return default


def external_visit_cost(draft, students, teachers, teacher_busy, rules):
    """Penalize another travel day for external teachers already attending.

    A first visit is free. The caller compares this cost only after mandatory
    role, count, availability, continuity and session constraints.
    """
    weight = preference_weight(rules, 'external_mentor_concentration')
    if weight <= 0 or draft.time_slot is None:
        return 0
    teacher_map = {teacher.id: teacher for teacher in teachers}
    people = {draft.chair_id, draft.secretary_id, *draft.expert_ids,
              *[student.supervisor_id for student in students]} - {None}
    extra_days = 0
    for tid in people:
        teacher = teacher_map.get(tid)
        if teacher is None or not teacher.is_external:
            continue
        attended_days = {slot.start.date() for slot in teacher_busy.get(tid, [])}
        if attended_days and draft.time_slot.start.date() not in attended_days:
            extra_days += 1
    return extra_days * weight


def software_reviewer_load(teacher, reviewer_load, rules):
    """Rotate software-college reviewers when balancing has positive weight."""
    if preference_weight(rules, 'balance_software_participation', 50) <= 0:
        return 0
    return reviewer_load.get(teacher.id, 0)


def preference_notices(drafts, teachers, rules):
    """Explain remaining optimization opportunities without blocking publication."""
    teacher_map = {teacher.id: teacher for teacher in teachers}
    visits, reviews, review_groups = defaultdict(list), defaultdict(int), defaultdict(list)
    for group in drafts:
        if group.time_slot is None:
            continue
        for tid in {group.chair_id, group.secretary_id, *group.expert_ids} - {None}:
            visits[tid].append(group)
        for tid in {group.chair_id, *group.expert_ids} - {None}:
            reviews[tid] += 1
            review_groups[tid].append(group.group_id)
    notices = []
    if preference_weight(rules, 'external_mentor_concentration') > 0:
        for tid, groups in visits.items():
            teacher = teacher_map.get(tid)
            days = {group.time_slot.start.date() for group in groups}
            if teacher is not None and teacher.is_external and len(days) > 1:
                notices.append({
                    'type': 'external_mentor_concentration',
                    'description': f'外院教师 {teacher.name} 需在 {len(days)} 天到场，可在人员与教室允许时进一步集中安排',
                    'related_ids': [*[group.group_id for group in groups], tid],
                    'teacher_name': teacher.name,
                })
    balance_default = 50 if rules.get('policy_version', 1) >= 2 or rules.get('expert_count_includes_chair') else 0
    if rules.get('defense_type') == 'formal' and preference_weight(rules, 'balance_software_participation', balance_default) > 0:
        eligible = [teacher for teacher in teachers if is_software_teacher(teacher.raw)
                    and (teacher_can_role(teacher.raw, 'chair') or teacher_can_role(teacher.raw, 'expert'))]
        if eligible:
            minimum, maximum = min(reviews[t.id] for t in eligible), max(reviews[t.id] for t in eligible)
            if maximum - minimum > 1:
                high = [t for t in eligible if reviews[t.id] == maximum]
                low = [t for t in eligible if reviews[t.id] == minimum]
                notices.append({
                    'type': 'software_participation_imbalance',
                    'description': f'软件学院教师评审次数为 {minimum} 至 {maximum} 次，可在资格与时间允许时继续轮换均衡',
                    'related_ids': [*[group_id for t in high for group_id in review_groups[t.id]],
                                    *[t.id for t in [*high[:3], *low[:3]]]],
                })
    return notices
