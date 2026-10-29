"""Personnel-first scheduling (policy 3), independent of classroom resources."""
from collections import Counter

from .policies import teacher_can_role, secretary_is_qualified, pre_chair_is_qualified


def enabled(rules):
    return rules.get('policy_version') == 3 and rules.get('defense_type') in ('pre', 'formal')


def available(teacher, slot):
    from algorithm import parse_time_range
    raw = teacher.raw
    if (not raw.get('is_active', True) or raw.get('availability_invalid')
            or not (raw.get('availability_confirmed') or raw.get('availability_assumed'))):
        return False
    if any(parse_time_range(value).overlaps(slot) for value in teacher.available_time):
        return False
    windows = [parse_time_range(value) for value in raw.get('available_windows', [])]
    return not raw.get('availability_restricted') or any(
        window.start <= slot.start and slot.end <= window.end for window in windows)


def participants(group, students):
    """Mentors attend their students even when formal supervisor avoidance applies."""
    return ({group.chair_id, group.secretary_id, *group.expert_ids}
            | {s.supervisor_id for s in students if s.id in group.student_ids}) - {None}


def validate(groups, students, teachers, rules):
    from algorithm import make_conflict, meets_chair_requirement, conflicts_with_selected_teachers
    teacher_map = {t.id: t for t in teachers}
    student_map = {s.id: s for s in students}
    counts = Counter(sid for group in groups for sid in group.student_ids)
    conflicts = []
    def report(kind, text, group=None, **extra):
        conflicts.append(make_conflict(kind, text, [group.group_id] if group else [], **extra))
    for student in students:
        if counts[student.id] != 1:
            report('missing_student' if not counts[student.id] else 'duplicate_student',
                   f'学生 {student.name} ' + ('未安排：请补全导师可用时间、资格或扩大日期范围' if not counts[student.id] else '被重复安排'),
                   student_id=student.id)
    for group in groups:
        reviewers = {group.chair_id, *group.expert_ids} - {None}
        if len(reviewers) != rules['expert_count'] or len(group.expert_ids) != len(set(group.expert_ids)) or group.chair_id in group.expert_ids:
            report('expert_count_out_of_range', f'{group.group_id} 专家人数必须为 {rules["expert_count"]}，组长只计一次', group)
        chair = teacher_map.get(group.chair_id)
        chair_rules = ({**rules, 'defense_type': 'pre', 'chair_title': rules.get('source_chair_title', '副教授')}
                       if rules.get('linked_translation') else rules)
        qualified_chair = bool(chair) and (
            pre_chair_is_qualified(chair, chair_rules) if rules['defense_type'] == 'pre'
            else teacher_can_role(chair, 'chair') and meets_chair_requirement(chair, chair_rules))
        if not qualified_chair:
            report('chair_unavailable', f'{group.group_id} 缺少合格组长', group)
        secretary = teacher_map.get(group.secretary_id)
        if not secretary or not secretary_is_qualified(secretary, rules.get('secretary_title', '讲师')):
            report('secretary_unavailable', f'{group.group_id} 缺少合格秘书', group)
        if group.secretary_id in reviewers:
            report('role_conflict', f'{group.group_id} 秘书不能兼任评审', group)
        mentors = {student_map[sid].supervisor_id for sid in group.student_ids if sid in student_map}
        if rules['defense_type'] == 'pre' and reviewers:
            shares = Counter(student_map[sid].supervisor_id for sid in group.student_ids if sid in student_map)
            ordered = sorted(reviewers)
            sizes = [shares[tid] for tid in ordered]
            if max(sizes) - min(sizes) > 1:
                pattern = '＋'.join(map(str, sizes))
                detail = '、'.join(f'{teacher_map[tid].name if tid in teacher_map else tid} {shares[tid]} 人' for tid in ordered)
                report('mentor_student_imbalance',
                       f'{group.group_id} 各评审导师带入学生数为 {pattern}（{detail}），组内差距超过 1 人，需继续调整或核对限制原因', group)
        if rules['defense_type'] == 'pre' and not mentors <= reviewers:
            report('supervisor_missing', f'{group.group_id} 预答辩导师必须参加本组评审', group)
        if rules.get('avoid_supervisor') and mentors & reviewers:
            report('supervisor_avoidance', f'{group.group_id} 导师不能评审自己的学生', group)
        if group.secretary_id in mentors:
            report('secretary_is_supervisor', f'{group.group_id} 导师不能担任自己学生的秘书', group)
        if not rules.get('group_min', 1) <= len(group.student_ids) <= rules['group_max']:
            report('group_size_out_of_range', f'{group.group_id} 学生人数须为 {rules.get("group_min", 1)}～{rules["group_max"]} 人', group)
        if any(sid not in student_map for sid in group.student_ids):
            report('missing_student', f'{group.group_id} 存在不属于本次参排名单的学生', group)
        external = sum(teacher_map[tid].is_external for tid in reviewers if tid in teacher_map)
        if external > rules.get('external_expert_max', 1):
            kind = 'expert_count_out_of_range'
            report(kind, f'{group.group_id} 受人员资格和时间限制安排了 {external} 名外院专家', group)
        elif not external:
            report('external_distribution', f'{group.group_id} 无合适且可用的外院专家，已用本院教师补足', group)
        elif external > 1:
            report('external_distribution', f'{group.group_id} 为满足学生人数下限并保留导师评审，安排了 {external} 位外院专家', group)
        if len(group.student_ids) not in {rules['group_size'], max(1, rules['group_size'] - 1), rules['group_size'] + 1}:
            report('student_group_exception', f'{group.group_id} 实际安排 {len(group.student_ids)} 名学生（目标 {rules["group_size"]} 名）', group)
        people = participants(group, students)
        if not group.time_slot:
            report('teacher_unavailable', f'{group.group_id} 尚未确定答辩时间', group)
        for tid in people:
            teacher = teacher_map.get(tid)
            if not teacher or not teacher.raw.get('is_active', True):
                report('teacher_unavailable', f'{group.group_id} 教师 {tid} 不在可参加名单中', group)
            elif group.time_slot and not available(teacher, group.time_slot):
                report('teacher_unavailable', f'{group.group_id} 教师 {teacher.name} 在该时段不可用或可用时间待确认', group, teacher_name=teacher.name)
        for tid in group.expert_ids:
            if tid not in teacher_map or not teacher_can_role(teacher_map[tid], 'expert'):
                report('role_qualification', f'{group.group_id} 专家 {tid} 不具备资格', group)
        for tid in people:
            if conflicts_with_selected_teachers(tid, list(people - {tid}), teachers):
                report('role_conflict', f'{group.group_id} 存在不宜同组的教师', group)
        if group.time_slot:
            from algorithm import build_candidate_slots
            if group.time_slot not in build_candidate_slots(rules, []):
                report('teacher_unavailable', f'{group.group_id} 时间不在允许的排期时段内', group)
    for index, left in enumerate(groups):
        for right in groups[index + 1:]:
            if left.time_slot and right.time_slot and left.time_slot.overlaps(right.time_slot):
                for tid in participants(left, students) & participants(right, students):
                    report('teacher_time_conflict', f'教师 {teacher_map[tid].name if tid in teacher_map else tid} 在 {left.group_id} 和 {right.group_id} 时间冲突', left)
    conflicts.extend(coverage_notices(groups, students, teachers, rules))
    return conflicts


def coverage_notices(groups, students, teachers, rules):
    from algorithm import build_candidate_slots, make_conflict
    slots = build_candidate_slots(rules, [])
    from .pre_capacity import pre_capacity_notices
    notices = pre_capacity_notices(students, teachers, rules)
    for teacher in teachers:
        days = {g.time_slot.start.date() for g in groups if g.time_slot and teacher.id in participants(g, students)}
        for day in sorted(days):
            used = {g.time_slot.start.hour >= 12 for g in groups if g.time_slot and g.time_slot.start.date() == day and teacher.id in participants(g, students)}
            possible = {slot.start.hour >= 12 for slot in slots if slot.start.date() == day and available(teacher, slot)}
            if len(used) < 2 and len(possible) == 2:
                notices.append(make_conflict('half_day_coverage', f'教师 {teacher.name} 在 {day} 上午下午均有可用时段，但仅安排了一个时段；受学生任务数量、其他教师时间和专家组成限制，未能覆盖两个时段', [teacher.id], teacher_name=teacher.name))
    return notices


def generate(teachers, students, rules):
    from .personnel_first import PersonnelPlanner
    if rules['defense_type'] != 'pre' or rules.get('group_min', 1) < 4:
        return PersonnelPlanner(teachers, students, rules).run()
    from collections import defaultdict
    from math import ceil
    external_ids = {t.id for t in teachers if t.is_external}
    campus_students, external_tasks = Counter(), defaultdict(Counter)
    for student in students:
        campus_students[student.campus] += 1
        if student.supervisor_id in external_ids:
            external_tasks[student.campus][student.supervisor_id] += 1
    shortage = any(sum(ceil(n / rules['group_max']) for n in tasks.values())
                   * rules['group_min'] > campus_students[campus]
                   for campus, tasks in external_tasks.items())
    if shortage and rules.get('external_expert_max', 1) > 1:
        relaxed = PersonnelPlanner(teachers, students, rules).run()
        relaxed['diagnostics'].update(external_relaxation_tried=True,
            external_relaxation_reason=f'每组一位外院导师时，最低组数乘以 {rules["group_min"]} 人大于本校区学生总数')
        return relaxed
    strict = PersonnelPlanner(teachers, students, {**rules, 'external_expert_max': 1}).run()
    if not strict['unassigned_students'] or rules.get('external_expert_max', 1) == 1:
        return strict
    relaxed = PersonnelPlanner(teachers, students, rules).run()
    def quality(result):
        sizes = [len(g['student_ids']) for g in result['groups']]
        fairness = result.get('diagnostics', {}).get('fairness', {})
        joint = (sum((n - rules['group_size']) ** 2 for n in sizes)
                 + fairness.get('share_excess', 0) + fairness.get('appearance_square_sum', 0))
        return (len(result['unassigned_students']), joint)
    result = min((strict, relaxed), key=quality)
    result['diagnostics']['external_relaxation_tried'] = True
    return result
