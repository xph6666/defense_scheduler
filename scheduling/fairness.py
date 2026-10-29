"""Comparable units for headcounts, mentor shares and repeated attendance."""
from collections import Counter


def mentor_share_excess(counts, expert_count):
    """Excess concentration above the most even integer distribution.

    Include reviewers with zero students. For six students and three reviewers,
    2+2+2 costs zero, 3+2+1 costs one, and 6+0+0 costs twelve.
    """
    total = sum(counts.values())
    quotient, remainder = divmod(total, expert_count)
    ideal_squares = (expert_count - remainder) * quotient ** 2 + remainder * (quotient + 1) ** 2
    return (sum(n * n for n in counts.values()) - ideal_squares) / 2


def panel_cost(counts, target, experts):
    return (sum(counts.values()) - target) ** 2 + mentor_share_excess(counts, experts)


def distribution_metrics(groups, students, teachers):
    student_map = {s.id: s for s in students}
    visits = Counter()
    panels = []
    for group in groups:
        reviewers = {group.chair_id, *group.expert_ids} - {None}
        counts = Counter(student_map[sid].supervisor_id for sid in group.student_ids)
        shares = {str(tid): counts[tid] for tid in sorted(reviewers)}
        panels.append({'group_id': group.group_id, 'mentor_students': shares,
                       'share_excess': mentor_share_excess(counts, len(reviewers))})
        visits.update(reviewers | {group.secretary_id} | set(counts))
    return {'panels': panels, 'share_excess': sum(p['share_excess'] for p in panels),
            'appearances': {str(t.id): visits[t.id] for t in teachers},
            'appearance_square_sum': sum(n * n for n in visits.values())}
