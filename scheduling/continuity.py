"""Cross-stage group identity and the formal-defense mentor session invariant."""
from collections import defaultdict


def inherited_group_labels(batches, rules):
    """Keep V2 group labels; legacy integer database IDs do not become labels."""
    inherited = []
    preserve = rules.get('defense_type') == 'formal' and rules.get('grouping') == 'secretary'
    for batch in batches:
        labels = {s.previous_group_id for s in batch if isinstance(s.previous_group_id, str) and s.previous_group_id.strip()}
        inherited.append(next(iter(labels)) if preserve and len(labels) == 1 else None)
    used = {label for label in inherited if label is not None}
    result, assigned, next_number = [], set(), 1
    for label in inherited:
        if label is None or label in assigned:
            while f'G{next_number}' in used or f'G{next_number}' in assigned:
                next_number += 1
            label = f'G{next_number}'
            next_number += 1
        result.append(label)
        assigned.add(label)
    return result


def formal_mentor_session_violations(drafts, students, teachers, rules):
    """A mentor and their students attend one session while review avoidance holds.

    Presence means a reviewer assignment with the same start and end, not merely
    a partially overlapping interval. A secretary assignment is not a review seat.
    """
    if rules.get('defense_type') != 'formal' or not rules.get('formal_mentor_same_session'):
        return []
    student_map = {s.id: s for s in students}
    teacher_map = {t.id: t for t in teachers}
    mentor_students = defaultdict(set)
    for student in students:
        if student.supervisor_id is not None:
            mentor_students[student.supervisor_id].add(student.id)
    student_groups = defaultdict(list)
    reviewer_groups = defaultdict(list)
    for group in drafts:
        if group.time_slot is None:
            continue
        for sid in group.student_ids:
            student_groups[sid].append(group)
        for tid in {group.chair_id, *group.expert_ids} - {None}:
            reviewer_groups[tid].append(group)
    avoidance = rules.get('supervisor_policy') == 'avoid' or (
        rules.get('supervisor_policy') not in ('same_group', 'none') and rules.get('avoid_supervisor'))

    def same_session(left, right):
        return left.time_slot.start == right.time_slot.start and left.time_slot.end == right.time_slot.end

    def can_attend(review_group, student_group):
        return same_session(review_group, student_group) and (not avoidance or review_group.group_id != student_group.group_id)

    conflicts = []
    for mentor_id, own_students in mentor_students.items():
        mentor = teacher_map.get(mentor_id)
        name = mentor.name if mentor else str(mentor_id)
        for review in reviewer_groups[mentor_id]:
            matching = [g for sid in own_students for g in student_groups[sid] if can_attend(review, g)]
            if not matching:
                conflicts.append({
                    'type': 'formal_mentor_session_missing',
                    'description': f'导师 {name} 在 {review.group_id} 组参与评审，但该场次没有自己的学生到场，请安排其学生在同一时段的其他组答辩',
                    'related_ids': [review.group_id, mentor_id], 'teacher_name': name,
                })
        for sid in own_students:
            for attendance in student_groups[sid]:
                if not any(can_attend(review, attendance) for review in reviewer_groups[mentor_id]):
                    conflicts.append({
                        'type': 'formal_mentor_session_missing',
                        'description': f'{attendance.group_id} 组学生 {student_map[sid].name} 的导师 {name} 未在同一场次参与评审，请同步导师与学生的到场时段',
                        'related_ids': [attendance.group_id, sid, mentor_id], 'teacher_name': name,
                    })
    return conflicts
