"""Keep a pre-defense panel intact and add internal reviewers for its next stage."""
from collections import Counter

from .current import available, participants, validate
from .policies import teacher_can_role, secretary_is_qualified


def translate_panels(source, teachers, students, rules):
    from algorithm import GroupDraft, build_candidate_slots, serialize_group
    teacher_map = {t.id: t for t in teachers}
    student_map = {s.id: s for s in students}
    slots = build_candidate_slots(rules, [])
    groups, reasons = [], {}
    workload = Counter()
    student_workload = Counter()
    source_ids = set()

    def incompatible(people):
        return any(set(teacher_map[tid].forbidden_with) & (people - {tid}) for tid in people)

    for previous in sorted(source, key=lambda g: (g.time_slot.start, g.group_id)):
        ids = [sid for sid in previous.student_ids if sid in student_map]
        source_ids.update(ids)
        if not ids:
            continue
        if not rules.get('group_min', 1) <= len(ids) <= rules['group_max']:
            for sid in ids:
                reasons[sid] = f'预答辩 {previous.group_id} 在本阶段的学生人数不满足 {rules.get("group_min", 1)}～{rules["group_max"]} 人，请先调整预答辩或核对参与名单'
            continue
        core = {previous.chair_id, *previous.expert_ids}
        fixed = core | {previous.secretary_id} | {student_map[sid].supervisor_id for sid in ids}
        valid_core = (None not in fixed and fixed <= teacher_map.keys()
            and teacher_can_role(teacher_map[previous.chair_id], 'chair')
            and all(teacher_can_role(teacher_map[tid], 'expert') for tid in core - {previous.chair_id})
            and secretary_is_qualified(teacher_map[previous.secretary_id], rules['secretary_title'])
            and len(core) <= rules['expert_count']
            and sum(teacher_map[tid].is_external for tid in core) <= rules.get('external_expert_max', 1))
        best = None
        if valid_core:
            for slot in slots:
                busy = set().union(*(participants(g, students) for g in groups if g.time_slot.overlaps(slot)))
                if fixed & busy or not all(available(teacher_map[tid], slot) for tid in fixed) or incompatible(fixed):
                    continue
                candidates = sorted((tid for tid, t in teacher_map.items() if tid not in fixed | busy
                    and not t.is_external and teacher_can_role(t, 'expert') and available(t, slot)),
                    key=lambda tid: (workload[tid], student_workload[tid], tid))
                from itertools import combinations
                for extra in combinations(candidates, rules['expert_count'] - len(core)):
                    people = fixed | set(extra)
                    if incompatible(people):
                        continue
                    # Prefer a counterpart on the same day, then fewer arrival
                    # days; keep the original morning/afternoon where possible.
                    paired = sum(any(tid in participants(g, students) and g.time_slot.start.date() == slot.start.date()
                        and (g.time_slot.start.hour >= 12) != (slot.start.hour >= 12) for g in groups) for tid in people)
                    score = (sum(workload[tid] for tid in extra),
                        sum(student_workload[tid] for tid in extra), -paired, slot.start.date(),
                        (slot.start.hour >= 12) != (previous.time_slot.start.hour >= 12),
                        sum(workload[tid] for tid in extra), slot.start, extra)
                    if best is None or score < best[0]:
                        best = (score, slot, extra)
                    break
        if best is None:
            for sid in ids:
                reasons[sid] = f'沿用预答辩 {previous.group_id} 的组长、专家、秘书及学生；正式日期内无共同可用时段或缺少本院补充专家，请人工调整'
            continue
        _, slot, extra = best
        group = GroupDraft(previous.group_id, previous.campus, ids, slot, None,
            previous.chair_id, [*previous.expert_ids, *extra], previous.secretary_id)
        groups.append(group)
        workload.update(participants(group, students))
        student_workload.update({tid: len(ids) for tid in participants(group, students)})
    for sid in student_map.keys() - source_ids:
        reasons[sid] = '本轮预答辩未生成该学生的分组，无法平移；请先完成预答辩安排'
    conflicts = validate(groups, students, teachers, rules)
    for conflict in conflicts:
        if conflict['type'] == 'missing_student' and conflict.get('student_id') in reasons:
            conflict['description'] = reasons[conflict['student_id']]
    from .fairness import distribution_metrics
    return {'groups': [serialize_group(g) for g in groups], 'conflicts': conflicts,
        'diagnostics': {'fairness': distribution_metrics(groups, students, teachers)},
        'unassigned_students': [{'id': sid, 'name': student_map[sid].name, 'reason': reason} for sid, reason in sorted(reasons.items())]}
