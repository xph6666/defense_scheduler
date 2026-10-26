"""Match a complete formal session before committing any staff reservations.

One matching covers all required mentors, review seats and secretaries. This
avoids consuming a scarce teacher in an optional seat in an earlier group.
No input object is changed when the session cannot be completed.
"""
from .policies import is_software_teacher, secretary_is_qualified, teacher_can_role
import logging

_logger = logging.getLogger(__name__)


def match_formal_session(groups, students, teachers, rules, slot, busy=None, rng=None, *, available=None,
                         reserve_chairs=False):
    # Import lazily: algorithm uses this planner after parsing its domain types.
    from algorithm import (GroupDraft, committee_violations, conflicts_with_selected_teachers,
                           meets_chair_requirement, teacher_is_eligible)
    busy = busy or {}
    student_map = {s.id: s for s in students}
    own = [{student_map[sid].supervisor_id for sid in g.student_ids} - {None} for g in groups]
    required = set().union(*own)
    if available is None:
        available = {t.id: t for t in teachers if teacher_is_eligible(t, slot, busy.get(t.id, []), (), rules)}
    if not required <= available.keys():
        return None
    software_min = max(3, int(rules.get('formal_software_min', 3)))
    reviewer_count = int(rules.get('expert_count', 5))
    if not 3 <= software_min <= reviewer_count:
        return None
    ordinary = {tid for tid, t in available.items() if is_software_teacher(t) and teacher_can_role(t, 'expert')}
    mentors = {s.supervisor_id for s in students} - {None}
    software = {tid for tid,t in available.items() if is_software_teacher(t)}
    experts = {tid for tid,t in available.items() if teacher_can_role(t,'expert')}
    chairs = {tid for tid,t in available.items() if tid in software and teacher_can_role(t,'chair')
              and meets_chair_requirement(t,rules)}
    if reserve_chairs:
        # A first search can preserve scarce chair resources. This is a search
        # preference only; the caller retries with their full expert eligibility.
        ordinary-=chairs
        experts-=chairs
        if len(required&chairs)>len(groups):return None
    qualified_secretaries = {tid for tid,t in available.items()
                            if secretary_is_qualified(t,rules.get('secretary_title','讲师'))}
    if (len(required) > reviewer_count * len(groups)
            or len(required - software) > (reviewer_count-software_min)*len(groups)
            or len(ordinary & (required | (available.keys()-mentors))) < (software_min-1)*len(groups)):
        return None
    seats = []
    bindings = []
    for index, g in enumerate(groups):
        secretaries = {student_map[sid].secretary_id for sid in g.student_ids} - {None}
        if len(secretaries) > 1:
            return None
        bindings.append(next(iter(secretaries), None))
        seats.extend([(index, 'chair'), (index, 'secretary')]
                     + [(index, 'software')] * (software_min - 1)
                     + [(index, 'expert')] * (reviewer_count - software_min))
    adjacency = {}
    for tid, teacher in available.items():
        choices = []
        for seat, (index, role) in enumerate(seats):
            if role == 'secretary':
                if (tid in required or tid in own[index]
                        or (bindings[index] is not None and tid != bindings[index])
                        or tid not in qualified_secretaries):
                    continue
            else:
                if tid not in required and tid in mentors:
                    continue  # A reviewing mentor must have their own student here.
                if rules.get('avoid_supervisor', True) and tid in own[index]:
                    continue
                if role == 'chair':
                    # Prefer a software-college chair, reserving its majority seat.
                    # Unsupported alternatives retain the existing draft fallback.
                    if tid not in chairs:
                        continue
                elif tid not in experts:
                    continue
                elif role == 'software' and tid not in software:
                    continue
            choices.append(seat)
        adjacency[tid] = choices
    # Match mandatory vertices first, then fill optional seats with augmenting
    # paths. Augmentation can relocate a mentor but never drops a matched one.
    matching = {}
    def augment(tid, visited):
        for seat in adjacency[tid]:
            if seat in visited:
                continue
            visited.add(seat)
            if seat not in matching or augment(matching[seat], visited):
                matching[seat] = tid
                return True
        return False
    for tid in sorted(required, key=lambda tid: (len(adjacency[tid]), tid)):
        if not augment(tid, set()):
            return None
    optional = sorted(available.keys() - required)
    if rng is not None:
        rng.shuffle(optional)
    for tid in sorted(optional, key=lambda tid: len(adjacency[tid])):
        augment(tid, set())
    if len(matching) != len(seats):
        return None
    result = []
    for index, group in enumerate(groups):
        draft = GroupDraft(group.group_id, group.campus, list(group.student_ids), slot, group.room_id)
        for seat, (owner, role) in enumerate(seats):
            if owner != index:
                continue
            tid = matching[seat]
            if role == 'chair':
                draft.chair_id = tid
            elif role == 'secretary':
                draft.secretary_id = tid
            else:
                draft.expert_ids.append(tid)
        people = {draft.chair_id, draft.secretary_id, *draft.expert_ids}
        if (committee_violations(draft, teachers, rules) or any(
                conflicts_with_selected_teachers(tid, list(people - {tid}), teachers) for tid in people)):
            return None
        result.append(draft)
    return result


def repair_formal_sessions(groups, students, teachers, rooms, rules, slots, seed=0):
    """Bounded, deterministic session search; return only a complete assignment.

    Failure is a search result, not proof that the user's constraints are
    impossible. The caller retains the explicit conflicted draft in that case.
    """
    import random
    from algorithm import (GroupDraft, iter_slot_room_candidates, reserve_teacher_time,
                           teacher_is_eligible)
    student_map = {s.id: s for s in students}
    own = {g.group_id: {student_map[sid].supervisor_id for sid in g.student_ids} - {None} for g in groups}
    mentors = set().union(*own.values())
    teacher_map = {t.id: t for t in teachers}
    ordinary = {t.id for t in teachers if is_software_teacher(t) and teacher_can_role(t, 'expert')}
    # A necessary upper bound catches grouping structures that no rearrangement
    # of dates/rooms can fix. This never excludes a feasible assignment.
    sessions_max = len(groups) // 2 if rules.get('avoid_supervisor') and all(own.values()) else len(groups)
    occurrence_max = sum(len(ids & ordinary) for ids in own.values())
    software_min = max(3, int(rules.get('formal_software_min', 3)))
    if occurrence_max + len(ordinary - mentors) * sessions_max < (software_min - 1) * len(groups):
        _logger.debug('Formal grouping fails software reviewer capacity upper bound')
        return None
    rng = random.Random(seed)
    pending = list(groups)
    finished, teacher_busy, room_busy = [], {}, {}
    for slot in slots:
        candidates, options = [], {}
        available_teachers = {t.id: t for t in teachers if teacher_is_eligible(
            t, slot, teacher_busy.get(t.id, []), (), rules)}
        room_options = {}
        for g in pending:
            if not own[g.group_id] <= available_teachers.keys():
                continue
            room_key = (g.campus, len(g.student_ids))
            if room_key not in room_options:
                room_options[room_key] = [room for when, room in iter_slot_room_candidates(
                    g, rooms, [slot], room_busy, rules) if when == slot]
            available_rooms = room_options[room_key]
            if available_rooms:
                candidates.append(g)
                options[g.group_id] = available_rooms
        if not candidates:
            continue
        capacity = min(len({room.id for values in options.values() for room in values}),
                       len(candidates), len(ordinary) // (software_min-1))
        chosen = None
        # Try larger sessions first. Shuffles change the candidate subset while
        # the seed keeps reruns reproducible. Staff matching is exact for each
        # proposed subset; this outer search is intentionally bounded.
        # With avoidance disabled, a one-group session can review its own
        # mentors. It still needs mandatory-mentor matching, not random filling.
        smallest_session = 2 if rules.get('avoid_supervisor', True) else 1
        for size in range(capacity, smallest_session - 1, -1):
            attempted = set()
            for attempt in range(96):
                ordered = list(candidates)
                if attempt:
                    rng.shuffle(ordered)
                # Keep an awkward group in every proposed batch. Consuming all
                # groups with many software mentors first strands the groups
                # that need those peers later in the plan.
                ordered.sort(key=lambda g: len(own[g.group_id] & ordinary))
                batch, represented, secretaries = [], set(), set()
                while ordered and len(batch) < size:
                    def gain(g):
                        ids = own[g.group_id]
                        return (len((ids & ordinary) - represented) * 5
                                - len((ids - ordinary) - represented))
                    g = max(ordered, key=gain) if attempt and batch else ordered[0]
                    ordered.remove(g)
                    bound = {student_map[sid].secretary_id for sid in g.student_ids} - {None}
                    if bound & secretaries or len(bound)>1:
                        continue
                    batch.append(g)
                    represented.update(own[g.group_id])
                    secretaries.update(bound)
                if len(batch) != size:
                    continue
                key = tuple(sorted(g.group_id for g in batch))
                if key in attempted:
                    continue
                attempted.add(key)
                room_matching = {}
                def assign_room(g, visited):
                    for room in options[g.group_id]:
                        if room.id in visited:
                            continue
                        visited.add(room.id)
                        if room.id not in room_matching or assign_room(room_matching[room.id], visited):
                            room_matching[room.id] = g
                            return True
                    return False
                if not all(assign_room(g, set()) for g in batch):
                    continue
                proposed = match_formal_session(batch, students, teachers, rules, slot, teacher_busy, rng,
                                                available=available_teachers)
                if proposed is None:
                    continue
                assignments = {g.group_id: rid for rid, g in room_matching.items()}
                room_map = {r.id: r for r in rooms}
                for g in proposed:
                    g.room_id = assignments[g.group_id]
                    g.campus = room_map[g.room_id].campus
                chosen = proposed
                break
            if chosen:
                break
        if chosen:
            for g in chosen:
                reserve_teacher_time(teacher_busy, g)
                room_busy.setdefault(g.room_id, []).append(slot)
            finished.extend(chosen)
            completed = {g.group_id for g in chosen}
            pending = [g for g in pending if g.group_id not in completed]
            _logger.debug('Formal session %s: %d groups assigned, %d remain', slot.label, len(chosen), len(pending))
        if not pending:
            by_label = {g.group_id: g for g in finished}
            return [by_label[g.group_id] for g in groups]
    _logger.debug('Formal session search incomplete: %d of %d groups remain', len(pending), len(groups))
    return None
