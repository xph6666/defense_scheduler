"""Plan every chair, then every committee, and only then bind students.

Demand records contain attendance counts, never student identities. Looking at
mentor demand before choosing times prevents a personnel plan that students
cannot attend, without allocating students ahead of either personnel phase.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .policies import teacher_can_role, secretary_is_qualified, pre_chair_is_qualified
from .current import available, participants, validate

if TYPE_CHECKING:
    from algorithm import GroupDraft


@dataclass
class Demand:
    campus: str | None
    mentors: Counter
    previous_group: str | None = None

    @property
    def size(self):
        return sum(self.mentors.values())


@dataclass
class PanelPlan:
    demand: Demand
    group: 'GroupDraft'


class PersonnelPlanner:
    MAX_PANEL_OPTIONS = 32
    MAX_SEARCH_NODES = 4000
    MAX_COMBINATION_NODES = 1000000

    def __init__(self, teachers, students, rules, seed_groups=(), refine_seed_only=False):
        from algorithm import build_candidate_slots, meets_chair_requirement
        self.teachers, self.students, self.rules = teachers, students, dict(rules)
        if rules['defense_type'] == 'pre':
            # Saved snapshots enforce fixed numbers during edits, but fresh
            # generation still optimizes provisional groups before numbering.
            self.rules.pop('pre_group_order', None)
        self.teacher_map = {t.id: t for t in teachers}
        self.slots = build_candidate_slots(rules, [])
        self.available_ids = {slot: {t.id for t in teachers if available(t, slot)} for slot in self.slots}
        self.capacity = {t.id: max(1, sum(t.id in ids for ids in self.available_ids.values())) for t in teachers}
        self.chair_ids = {t.id for t in teachers if (
            pre_chair_is_qualified(t, rules) if rules['defense_type'] == 'pre' and rules.get('policy_version') == 3
            else teacher_can_role(t, 'chair') and meets_chair_requirement(t, rules))}
        self.expert_ids = {t.id for t in teachers if teacher_can_role(t, 'expert')}
        self.secretary_ids = {t.id for t in teachers if secretary_is_qualified(t, rules.get('secretary_title', '讲师'))}
        self.incompatible = {t.id: set(t.forbidden_with) for t in teachers}
        for teacher in teachers:
            for other in teacher.forbidden_with:
                self.incompatible.setdefault(other, set()).add(teacher.id)
        self.mentor_load = Counter(s.supervisor_id for s in students)
        self.student_map = {s.id: s for s in students}
        self.reservations = {}
        self._calendar = None
        self._rank_cache = {}
        self._occupied_cache = {}
        self.search_nodes = 0
        self.combination_nodes = 0
        self.search_limited = False
        self.candidates_limited = False
        self.plans = []
        self.reasons = {}
        self.failed_demands = []
        self.packing_diagnostics = []
        self.seed_groups = tuple(seed_groups)
        self.refine_seed_only = refine_seed_only
        self.demands = self.build_demands()

    def reserve(self, group_id, slot, people, count):
        self.reservations[group_id] = (slot, people, count)
        self.invalidate_calendar()

    def release(self, group_id):
        self.reservations.pop(group_id, None)
        self.invalidate_calendar()

    def invalidate_calendar(self):
        self._calendar = None
        self._rank_cache.clear()
        self._occupied_cache.clear()

    def calendar(self):
        if self._calendar is None:
            self._calendar = defaultdict(list)
            for key, (slot, people, count) in self.reservations.items():
                for tid in people:
                    self._calendar[tid].append((key, slot, count))
        return self._calendar

    def conflicts_with(self, tid, others):
        return bool(self.incompatible.get(tid, set()).intersection(others))

    def required_reviewers(self, demand):
        return set(demand.mentors) if self.rules['defense_type'] == 'pre' else set()

    def build_demands(self):
        """Estimate seats from counts; no concrete student is assigned a group."""
        if self.rules['defense_type'] == 'pre':
            return self.build_balanced_pre_demands()
        cohorts = defaultdict(Counter)
        for student in self.students:
            previous = student.previous_group_id if self.rules.get('preserve_pre_defense_groups') else None
            key = (student.campus, previous, None if previous else student.supervisor_id)
            cohorts[key][student.supervisor_id] += 1
        demands = []
        for (campus, previous, _), counts in cohorts.items():
            seats = Counter()
            for mentor, count in sorted(counts.items(), key=lambda item: str(item[0])):
                teacher = self.teacher_map.get(mentor)
                limit = self.mentor_limit(mentor)
                # Put an odd tail into the last pair (5 -> 2 + 3), rather than
                # making a teacher travel for one remaining student.
                chunks = []
                while count:
                    take = min(limit, count)
                    if limit == 3 and count > 3:
                        take = 2
                    chunks.append(take)
                    count -= take
                for take in chunks:
                    if sum(seats.values()) + take > self.rules['group_size'] or seats[mentor] + take > limit:
                        demands.append(Demand(campus, seats, previous))
                        seats = Counter()
                    seats[mentor] += take
            if seats:
                demands.append(Demand(campus, seats, previous))
        # A mixed inherited unit may have no common mentor time or may require
        # two external reviewers in five-person mode. Split attendance demand
        # before personnel planning, preserving all student counts.
        result = []
        for demand in demands:
            common = any(set(demand.mentors) <= ids for ids in self.available_ids.values())
            too_many_external = (self.rules['defense_type'] == 'pre'
                and sum(self.teacher_map[tid].is_external for tid in demand.mentors if tid in self.teacher_map) > 1)
            if len(demand.mentors) > 1 and (not common or too_many_external):
                result.extend(Demand(demand.campus, Counter({tid: count}), demand.previous_group)
                              for tid, count in demand.mentors.items())
            else:
                result.append(demand)
        result.sort(key=lambda d: (sum(set(d.mentors) <= ids for ids in self.available_ids.values()),
                                   str(d.campus), str(d.previous_group), str(sorted(d.mentors, key=str))))
        if self.rules['defense_type'] != 'pre':
            return result
        # Combine attendance counts, not student identities. Commit a merge only
        # when a real chair, committee and secretary can share a valid slot.
        packed = []
        for demand in result:
            merged = False
            for index, existing in enumerate(packed):
                counts = existing.mentors + demand.mentors
                if existing.campus != demand.campus or existing.previous_group != demand.previous_group:
                    continue
                if sum(counts.values()) > self.rules['group_size'] or any(n > self.mentor_limit(tid) for tid, n in counts.items()):
                    continue
                if len(counts) > 3 or sum(self.teacher_map[tid].is_external for tid in counts if tid in self.teacher_map) > 1:
                    continue
                combined = Demand(demand.campus, counts, demand.previous_group)
                if any(set(counts) <= ids and any(self.panel_for_chair(combined, slot, chair, ids)
                        for chair in sorted(self.chair_ids & ids)) for slot, ids in self.available_ids.items()):
                    packed[index] = combined
                    merged = True
                    break
            if not merged:
                packed.append(demand)
        return packed

    def mentor_limit(self, tid):
        # The confirmed policy prioritizes balanced panels over two seats per
        # mentor. A mentor may bring any number up to the panel capacity.
        return self.rules['group_max']

    def build_balanced_pre_demands(self):
        """Pack counts into near-full feasible panels, then balance their tails."""
        cohorts = defaultdict(Counter)
        for student in self.students:
            cohorts[student.campus][student.supervisor_id] += 1
        target = self.rules['group_size']
        minimum = self.rules.get('group_min', 1)
        external_max = self.rules.get('external_expert_max', 1)
        feasible_cache = {}

        def feasible(campus, counts, external_limit=None):
            external_limit = external_max if external_limit is None else external_limit
            mentors = frozenset(counts)
            key = (mentors, external_limit)
            if key not in feasible_cache:
                if len(mentors) == self.rules['expert_count'] and mentors <= self.teacher_map.keys():
                    chairs = mentors & self.chair_ids
                    valid = (None not in mentors
                        and sum(self.teacher_map[t].is_external for t in mentors) <= external_limit
                        and any((mentors - {c}) <= self.expert_ids for c in chairs)
                        and not any(self.conflicts_with(t, mentors - {t}) for t in mentors))
                    feasible_cache[key] = valid and any(mentors <= ids and any(
                        not self.conflicts_with(s, mentors) for s in (ids & self.secretary_ids) - mentors)
                        for ids in self.available_ids.values())
                    return feasible_cache[key]
                feasible_cache[key] = (bool(mentors) and None not in mentors and mentors <= self.teacher_map.keys()
                    and len(mentors) <= self.rules['expert_count']
                    and sum(self.teacher_map[t].is_external for t in mentors) <= external_limit
                    and any(mentors <= ids and any(self.panel_for_chair(
                        Demand(campus, counts), slot, chair, ids)
                        for chair in sorted(self.chair_ids & ids))
                        for slot, ids in self.available_ids.items()))
            return feasible_cache[key]

        result = []
        caps = self.campus_group_caps(cohorts)
        for campus, remaining in sorted(cohorts.items(), key=lambda item: str(item[0])):
            packed = []
            cap = caps.get(campus)
            # External mentors seed different panels; internal mentors then
            # fill their seats instead of leaving many small external panels.
            order = sorted(remaining, key=lambda tid: (
                not bool(self.teacher_map.get(tid) and self.teacher_map[tid].is_external),
                sum(tid in ids for ids in self.available_ids.values()), -remaining[tid], str(tid)))
            for tid in order:
                count = remaining[tid]
                for demand in packed:
                    take = min(count, target - demand.size)
                    if take and feasible(campus, demand.mentors + Counter({tid: take}), 1):
                        demand.mentors[tid] += take
                        count -= take
                    if not count:
                        break
                while count:
                    take = min(target, count)
                    packed.append(Demand(campus, Counter({tid: take})))
                    count -= take
            # Meet the hard floor before optimizing equal sizes. Relax the
            # external preference only for required mentors of a merged panel.
            for _ in range(len(packed)):
                choices = []
                for index, small in enumerate(packed):
                    if small.size >= minimum:
                        continue
                    for other in packed[index + 1:]:
                        counts = small.mentors + other.mentors
                        if sum(counts.values()) <= self.rules['group_max'] and feasible(campus, counts):
                            choices.append((sum(counts.values()) < minimum,
                                sum(self.teacher_map[t].is_external for t in counts),
                                abs(target - sum(counts.values())), index, packed.index(other), counts))
                if not choices:
                    break
                _, _, _, left, right, counts = min(choices, key=lambda item: item[:-1])
                packed[left].mentors = counts
                packed.pop(right)
            # 6+4 -> 5+5; 6+6+1 -> 5+4+4 where staffing permits. Only
            # counts move here; concrete student identities are bound later.
            for _ in range(max(1, len(packed) * target)):
                changed = False
                for small in sorted(packed, key=lambda d: d.size):
                    for large in sorted(packed, key=lambda d: -d.size):
                        if large.size - small.size < 2:
                            continue
                        for tid in sorted(large.mentors, key=str):
                            left = large.mentors - Counter({tid: 1})
                            right = small.mentors + Counter({tid: 1})
                            if feasible(campus, left) and feasible(campus, right):
                                large.mentors, small.mentors = left, right
                                changed = True
                                break
                        if changed:
                            break
                    if changed:
                        break
                if not changed:
                    break
            if minimum >= 4:
                from .balanced_counts import pack_counts
                seed_counts = [d.mentors for d in packed]
                warm_valid = False
                warm_groups = [g for g in self.seed_groups if g.campus == campus]
                warm_ids = [sid for g in warm_groups for sid in g.student_ids]
                expected_ids = [s.id for s in self.students if s.campus == campus]
                if warm_ids and sorted(warm_ids) == sorted(expected_ids):
                    warm_counts = [Counter(self.student_map[sid].supervisor_id for sid in g.student_ids)
                                   for g in warm_groups]
                    if all(minimum <= sum(c.values()) <= self.rules['group_max'] and feasible(campus, c)
                           for c in warm_counts):
                        seed_counts = warm_counts
                        warm_valid = True
                if warm_valid and self.refine_seed_only:
                    optimized, diagnostics = seed_counts, {'status': 'complete_seed'}
                else:
                    optimized, diagnostics = pack_counts(remaining, target, minimum, self.rules['group_max'],
                        self.rules['expert_count'], external_max, self.teacher_map, self.chair_ids,
                        lambda counts: feasible(campus, counts), seed_counts, max_groups=cap)
                if target == 6 and self.rules['group_max'] == 7:
                    from .compact_counts import repack_sixes
                    # 七人组改六人组会增加组数，容量受限时不得超过本校区可开设的组数
                    optimized, blocks = repack_sixes(optimized, self.rules['expert_count'], external_max,
                        self.teacher_map, self.chair_ids, lambda counts: feasible(campus, counts),
                        limit=None if cap is None else max(0, cap - len(optimized)))
                    diagnostics['six_seat_repack_blocks'] = blocks
                diagnostics['group_cap'] = cap
                self.packing_diagnostics.append({'campus': campus, **diagnostics})
                self.search_limited |= diagnostics['status'] in ('bounded', 'search_limit')
                covered = sum(optimized, Counter())
                if cap is not None and len(optimized) >= cap:
                    reason = (f'排期日期内可同时开设的小组数不足（{campus or "本校区"}最多约 {cap} 组，'
                              f'受 {len(self.secretary_ids)} 位秘书和评审人数限制）；请延长日期范围或补充秘书')
                else:
                    reason = f'在本次搜索范围内，未找到满足每组至少 {minimum} 人、导师评审、时间及专家资格的组合'
                for tid, count in (remaining - covered).items():
                    self.failed_demands.append((Demand(campus, Counter({tid: count})), reason))
                packed = [Demand(campus, counts) for counts in optimized]
            result.extend(packed)
        result.sort(key=lambda d: (sum(set(d.mentors) <= ids for ids in self.available_ids.values()),
                                   -d.size, str(d.campus), str(sorted(d.mentors, key=str))))
        return result

    def slot_group_capacity(self):
        """各半天可同时开设组数的上界之和：秘书、合格组长和到场人数取最小值。"""
        size = self.rules['expert_count'] + 1
        return sum(min(len(ids & self.secretary_ids), len(ids & self.chair_ids), len(ids) // size)
                   for ids in self.available_ids.values())

    def campus_group_caps(self, cohorts):
        """日期容量不足以按目标人数成组时，按学生人数为各校区分配组数上限；容量充足时返回空字典。

        先满足各校区按每组最多人数所需的最少组数，余量再按学生比例（最大余数法）分配；
        若连最少组数都放不下，则整体按学生比例分配，未能覆盖的学生会明确列为未安排。
        """
        capacity = self.slot_group_capacity()
        target, maximum = self.rules['group_size'], self.rules['group_max']
        sizes = {campus: sum(counts.values()) for campus, counts in cohorts.items()}
        if not sizes or capacity >= sum(max(-(-n // maximum), round(n / target)) for n in sizes.values()):
            return {}
        total = sum(sizes.values())
        minimum = {campus: -(-n // maximum) for campus, n in sizes.items()}
        base = minimum if sum(minimum.values()) <= capacity else {campus: 0 for campus in sizes}
        spare = capacity - sum(base.values())
        shares = {campus: spare * n / total for campus, n in sizes.items()}
        caps = {campus: base[campus] + int(shares[campus]) for campus in sizes}
        leftover = capacity - sum(caps.values())
        for campus in sorted(shares, key=lambda c: (-(shares[c] - int(shares[c])), str(c)))[:leftover]:
            caps[campus] += 1
        return caps

    def occupied(self, tid, slot, except_group=None):
        key = (tid, slot, except_group)
        if key not in self._occupied_cache:
            self._occupied_cache[key] = any(group_id != except_group and slot.overlaps(other)
                for group_id, other, _ in self.calendar().get(tid, ()))
        return self._occupied_cache[key]

    def rank(self, tid, slot, except_group=None):
        key = (tid, slot, except_group)
        if key in self._rank_cache:
            return self._rank_cache[key]
        visits = [(other, count) for group_id, other, count in self.calendar().get(tid, ())
                  if group_id != except_group]
        coverage = any(other.start.date() == slot.start.date()
                       and (other.start.hour >= 12) != (slot.start.hour >= 12) for other, _ in visits)
        result = (len(visits), sum(count for _, count in visits), -int(coverage), tid)
        self._rank_cache[key] = result
        return result

    def eligible(self, demand, slot, except_group=None):
        return {tid for tid in self.available_ids[slot] if not self.occupied(tid, slot, except_group)
                and not self.conflicts_with(tid, set(demand.mentors) - {tid})}

    def panel_for_chair(self, demand, slot, chair, eligible):
        """Feasibility lookahead only; never reserves expert/secretary identities."""
        return next(self.panel_options(demand, slot, chair, eligible, limit=1), None)

    def panel_options(self, demand, slot, chair, eligible, limit=None):
        """Enumerate distinct valid completions in preference order, within budget."""
        limit = self.MAX_PANEL_OPTIONS if limit is None else limit
        mentors = set(demand.mentors)
        if self.rules.get('avoid_supervisor'):
            eligible = eligible - mentors
            if chair in mentors:
                return
        required = self.required_reviewers(demand) - {chair}
        if not required <= self.expert_ids & eligible:
            return
        fixed = {chair, *required}
        if any(self.conflicts_with(tid, fixed - {tid}) for tid in fixed):
            return
        seats = self.rules['expert_count'] - len(fixed)
        if seats < 0:
            return
        key = lambda tid: self.rank(tid, slot)
        secretaries = sorted((eligible & self.secretary_ids) - mentors - fixed,
            key=lambda tid: (tid in self.expert_ids or tid in self.chair_ids,
                             not self.teacher_map[tid].is_external if (self.rules['expert_count'] == 5
                                 or any(self.teacher_map[t].is_external for t in fixed)) else False,
                             key(tid)))
        seen = set()
        # More external seats are allowed only when their own students require
        # them. Optional reviewers never add a second external teacher.
        limits = [max(1, sum(self.teacher_map[t].is_external for t in self.required_reviewers(demand)))]
        if limits[0] > self.rules.get('external_expert_max', 1):
            return
        for external_limit in limits:
            fixed_external = sum(self.teacher_map[tid].is_external for tid in fixed)
            if fixed_external > external_limit:
                continue
            for secretary in secretaries:
                if self.conflicts_with(secretary, fixed | mentors):
                    continue
                candidates = sorted((eligible & self.expert_ids) - fixed - {secretary},
                                    key=lambda tid: (not self.teacher_map[tid].is_external, key(tid)))
                candidates = [tid for tid in candidates if not self.conflicts_with(tid, fixed | {secretary})]
                def fill(start, picked, external):
                    if self.combination_nodes >= self.MAX_COMBINATION_NODES:
                        self.search_limited = True
                        return
                    self.combination_nodes += 1
                    needed = seats - len(picked)
                    if needed == 0:
                        yield picked
                        return
                    remaining = candidates[start:]
                    if len(remaining) < needed:
                        return
                    if sum(not self.teacher_map[tid].is_external for tid in remaining) + external_limit - external < needed:
                        return
                    for index in range(start, len(candidates) - needed + 1):
                        tid = candidates[index]
                        next_external = external + int(self.teacher_map[tid].is_external)
                        if next_external <= external_limit and not self.conflicts_with(tid, picked):
                            yield from fill(index + 1, [*picked, tid], next_external)
                for picked in fill(0, [], fixed_external):
                    members = sorted(required) + picked
                    identity = (tuple(sorted(members)), secretary)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    yield members, secretary
                    if len(seen) >= limit:
                        if limit > 1:
                            self.candidates_limited = True
                        return

    def can_staff_together(self, demand, slot, chair, overlapping):
        """Check role capacity across simultaneous panels without assigning staff.

        A total headcount cannot detect a shortage of secretaries or internal
        reviewers. Bipartite matching reserves no identities, but proves that
        distinct eligible people can fill all remaining roles at this point.
        """
        panels = [(p.demand, p.group.time_slot, p.group.chair_id, p.group.group_id) for p in overlapping]
        panels.append((demand, slot, chair, None))
        fixed = [set(d.mentors) | {c} for d, _, c, _ in panels]
        reserved = set().union(*fixed)
        if sum(len(people) for people in fixed) != len(reserved):
            return False
        domains = []
        for (item, when, leader, gid), people in zip(panels, fixed):
            reviewers = self.required_reviewers(item) | {leader}
            if not (reviewers - {leader}) <= self.expert_ids:
                return False
            external = sum(self.teacher_map[tid].is_external for tid in reviewers)
            if external > self.rules.get('external_expert_max', 1) or len(reviewers) > self.rules['expert_count']:
                return False
            if external > 1 and any(self.teacher_map[tid].is_external
                                    for tid in reviewers - self.required_reviewers(item)):
                return False
            free = {tid for tid in self.available_ids[when] - reserved
                    if not self.occupied(tid, when, gid) and not self.conflicts_with(tid, people)}
            domains.append(free & self.secretary_ids)
            extra = self.rules['expert_count'] - len(reviewers)
            experts = free & self.expert_ids
            internal = {tid for tid in experts if not self.teacher_map[tid].is_external}
            # At most one optional seat may use an external teacher.
            if extra and not external:
                domains.append(experts)
                extra -= 1
            domains.extend(internal for _ in range(extra))
        if any(not options for options in domains):
            return False
        owners = {}

        def match(index, seen):
            for tid in sorted(domains[index]):
                if tid in seen:
                    continue
                seen.add(tid)
                if tid not in owners or match(owners[tid], seen):
                    owners[tid] = index
                    return True
            return False

        return all(match(index, set()) for index in sorted(range(len(domains)), key=lambda i: len(domains[i])))

    def assign_chairs(self):
        """Phase 1: reserve ALL group chairs/times; committees remain empty."""
        from algorithm import GroupDraft
        for demand in self.demands:
            mentors = set(demand.mentors)
            if None in mentors or not mentors <= self.teacher_map.keys():
                self.failed_demands.append((demand, '导师缺失、停用或未参加本次答辩'))
                continue
            best, best_score = None, None
            causes = set()  # 各半天被拒的原因，用于给出准确的未安排说明
            for slot in self.slots:
                overlapping = [plan for plan in self.plans if slot.overlaps(plan.group.time_slot)]
                attendance = [plan.demand for plan in overlapping] + [demand]
                headcount = sum(self.rules['expert_count'] + 1 + (
                    len(item.mentors) if self.rules.get('avoid_supervisor') else 0) for item in attendance)
                if headcount > len(self.available_ids[slot]):
                    causes.add('capacity' if mentors <= self.available_ids[slot] else 'mentor_time')
                    continue
                if self.rules['expert_count'] == 5 and 4 * len(attendance) > sum(
                        not self.teacher_map[tid].is_external for tid in self.available_ids[slot]):
                    causes.add('capacity' if mentors <= self.available_ids[slot] else 'mentor_time')
                    continue
                eligible = self.eligible(demand, slot)
                if not mentors <= eligible:
                    causes.add('mentor_busy' if mentors <= self.available_ids[slot] else 'mentor_time')
                    continue
                chairs = self.chair_ids & eligible
                if self.rules.get('avoid_supervisor'):
                    chairs -= mentors
                if not chairs:
                    causes.add('panel')
                for chair in sorted(chairs, key=lambda tid: (tid not in self.required_reviewers(demand), self.rank(tid, slot))):
                    people = mentors | {chair}
                    score = (int(chair not in self.required_reviewers(demand)),
                             self.mentor_load[chair] if self.rules.get('avoid_supervisor') else 0,
                             sum(self.rank(tid, slot)[0] for tid in people),
                             sum(self.rank(tid, slot)[1] for tid in people),
                             sum(self.rank(tid, slot)[2] for tid in people), slot.start, chair)
                    # The score is known without enumerating teachers. A chair
                    # that cannot beat an already feasible choice needs no probe.
                    if best_score is not None and score >= best_score:
                        continue
                    # Feasibility lookahead assigns nobody. Actual expert and
                    # secretary reservations happen only after every chair exists.
                    if self.panel_for_chair(demand, slot, chair, eligible) is None:
                        causes.add('panel')
                        continue
                    if not self.can_staff_together(demand, slot, chair, overlapping):
                        causes.add('capacity')
                        continue
                    group_id = f'G{len(self.plans) + 1:03}'
                    best = PanelPlan(demand, GroupDraft(group_id, demand.campus, [], slot, None, chair))
                    best_score = score
            if best:
                self.plans.append(best)
                self.reserve(best.group.group_id, best.group.time_slot, mentors | {best.group.chair_id}, demand.size)
            else:
                self.failed_demands.append((demand, self.chair_failure_reason(mentors, causes)))

    def chair_failure_reason(self, mentors, causes):
        """按各半天被拒原因给出可操作的说明：时间、占用或容量，避免一律归为日期问题。"""
        if any((not self.teacher_map[tid].raw.get('availability_confirmed')
                and not self.teacher_map[tid].raw.get('availability_assumed'))
               or self.teacher_map[tid].raw.get('availability_invalid') for tid in mentors):
            return '导师可用时间待确认或格式无效'
        if 'capacity' in causes:
            return (f'导师共同可用的半天中，秘书或评审名额已被其他小组占满（全部 {len(self.secretary_ids)} 位秘书'
                    '每个半天各带一组）；请延长日期范围或补充秘书')
        if not causes or causes == {'mentor_time'}:
            return '本组导师在排期日期内没有共同可用的半天；请核对导师可用时间或延长日期范围'
        if causes <= {'mentor_time', 'mentor_busy'}:
            return '本组导师共同可用的半天均已被其他小组占用；请延长日期范围'
        return '没有同时满足导师时间、组长资格及专家人数要求的空余时段'

    def assign_staff(self):
        """Phase 2: scarce panels first, with bounded backtracking per time component.

        A failed expert choice can be undone without moving any fixed chair or
        binding any student. Disjoint time components have independent capacity.
        """
        components = []
        latest_end = None
        for plan in sorted(self.plans, key=lambda p: (p.group.time_slot.start, p.group.group_id)):
            slot = plan.group.time_slot
            if latest_end is None or slot.start >= latest_end:
                components.append([])
                latest_end = slot.end
            components[-1].append(plan)
            latest_end = max(latest_end, slot.end)

        completed = set()
        for component in components:
            best, best_score = {}, (-1, -1)
            chosen = {}
            # 搜索预算按时间分量分别计算：前面的分量用完预算不应使后面分量一组都排不上
            budget_start = self.search_nodes

            def search(pending, student_count):
                nonlocal best, best_score
                score = (student_count, len(chosen))
                if score > best_score:
                    best, best_score = dict(chosen), score
                if not pending:
                    return len(chosen) == len(component)
                if self.search_nodes - budget_start >= self.MAX_SEARCH_NODES:
                    self.search_limited = True
                    return False
                self.search_nodes += 1
                if (student_count + sum(p.demand.size for p in pending), len(chosen) + len(pending)) <= best_score:
                    return False
                # Most constrained first; option limits are explicit search
                # bounds, never proof that a schedule is impossible.
                domains = []
                for plan in pending:
                    group = plan.group
                    eligible = self.eligible(plan.demand, group.time_slot, group.group_id)
                    options = list(self.panel_options(plan.demand, group.time_slot, group.chair_id, eligible))
                    domains.append((len(options), -plan.demand.size, group.group_id, plan, options))
                _, _, gid, plan, options = min(domains, key=lambda item: item[:3])
                remaining = [p for p in pending if p is not plan]
                original = self.reservations[gid]
                for members, secretary in options:
                    people = {plan.group.chair_id, secretary, *members, *plan.demand.mentors}
                    self.reserve(gid, plan.group.time_slot, people, plan.demand.size)
                    chosen[gid] = (list(members), secretary)
                    solved = search(remaining, student_count + plan.demand.size)
                    chosen.pop(gid)
                    self.reserve(gid, *original)
                    if solved:
                        return True
                    if self.search_nodes - budget_start >= self.MAX_SEARCH_NODES:
                        self.search_limited = True
                        break
                # Keep a maximal partial plan if a genuine shortage or the
                # bounded search prevents full coverage; release skipped chairs.
                self.release(gid)
                search(remaining, student_count)
                self.reserve(gid, *original)
                return False

            if len(component) > 200:
                # Avoid recursion-depth dependence on unusually large imports.
                self.search_limited = True
                for plan in component:
                    group = plan.group
                    eligible = self.eligible(plan.demand, group.time_slot, group.group_id)
                    assignment = self.panel_for_chair(plan.demand, group.time_slot, group.chair_id, eligible)
                    if assignment:
                        members, secretary = assignment
                        best[group.group_id] = assignment
                        self.reserve(group.group_id, group.time_slot,
                                     {group.chair_id, secretary, *members, *plan.demand.mentors}, plan.demand.size)
            else:
                search(component, 0)
            for plan in component:
                group = plan.group
                if group.group_id in best:
                    group.expert_ids, group.secretary_id = best[group.group_id]
                    self.reserve(group.group_id, group.time_slot,
                                 {group.chair_id, group.secretary_id, *group.expert_ids, *plan.demand.mentors}, plan.demand.size)
                    completed.add(group.group_id)
                else:
                    self.release(group.group_id)
                    self.failed_demands.append((plan.demand, '组长已排定，但在本次搜索范围内未找到兼容其他组长、导师和已分配教师的合格专家及秘书组合'))
        self.plans = [plan for plan in self.plans if plan.group.group_id in completed]

    def can_add(self, student, group):
        if group.campus != student.campus or len(group.student_ids) >= self.rules['group_max']:
            return False
        mentor = self.teacher_map.get(student.supervisor_id)
        if mentor is None or not available(mentor, group.time_slot):
            return False
        reviewers = {group.chair_id, *group.expert_ids}
        if self.rules['defense_type'] == 'pre' and mentor.id not in reviewers:
            return False
        if (self.rules.get('avoid_supervisor') and mentor.id in reviewers) or group.secretary_id == mentor.id:
            return False
        if sum(self.student_map[sid].supervisor_id == mentor.id for sid in group.student_ids) >= self.mentor_limit(mentor.id):
            return False
        if self.occupied(mentor.id, group.time_slot, group.group_id):
            return False
        people = self.reservations[group.group_id][1]
        return not self.conflicts_with(mentor.id, people - {mentor.id})

    def assign_students(self):
        """Phase 3: bind concrete students for the first time, then locally repair."""
        pending = {s.id: s for s in self.students}
        by_mentor = defaultdict(list)
        for student in self.students:
            by_mentor[student.supervisor_id].append(student)
        # Fill planned attendance quotas, preferring continuity from pre-defense.
        for plan in self.plans:
            group = plan.group
            for tid, count in plan.demand.mentors.items():
                candidates = sorted((s for s in by_mentor[tid] if s.id in pending and s.campus == group.campus),
                                    key=lambda s: (s.previous_group_id != plan.demand.previous_group, s.id))
                for student in candidates:
                    if count <= 0:
                        break
                    if self.can_add(student, group):
                        group.student_ids.append(student.id)
                        pending.pop(student.id)
                        count -= 1
        # Release attendance estimates that did not turn into actual tasks.
        for plan in self.plans:
            group = plan.group
            self.reserve(group.group_id, group.time_slot, participants(group, self.students), len(group.student_ids))
        for student in list(pending.values()):
            for plan in sorted(self.plans, key=lambda p: (len(p.group.student_ids), p.group.group_id)):
                group = plan.group
                if self.can_add(student, group):
                    group.student_ids.append(student.id)
                    pending.pop(student.id)
                    self.reserve(group.group_id, group.time_slot, participants(group, self.students), len(group.student_ids))
                    break
        for student in pending.values():
            matching = [reason for demand, reason in self.failed_demands
                        if demand.campus == student.campus and student.supervisor_id in demand.mentors]
            self.reasons[student.id] = matching[0] if matching else '已完成组长和教师编排，但现有小组无满足导师时间、回避规则和容量要求的学生名额'
        for plan in self.plans:
            if not plan.group.student_ids:
                self.release(plan.group.group_id)
        self.plans = [plan for plan in self.plans if plan.group.student_ids]

    def attendance_score(self):
        """Fair appearances, fair reviewed students, then compact attendance."""
        unpaired, trips, fairness, student_load = 0, 0, 0, 0
        for tid, visits in self.calendar().items():
            days = defaultdict(set)
            for _, slot, _ in visits:
                days[slot.start.date()].add(slot.start.hour >= 12)
            trips += len(days)
            for day, halves in days.items():
                possible = {slot.start.hour >= 12 for slot in self.slots
                            if slot.start.date() == day and tid in self.available_ids[slot]}
                unpaired += int(len(halves) == 1 and len(possible) == 2)
            fairness += len(visits) ** 2
            student_load += sum(count for _, _, count in visits) ** 2
        return fairness, student_load, unpaired, trips

    def compact_attendance(self):
        """Bounded local repair after the three phases; never loses a student.

        Move complete panels to fill an opposite half-day, then rotate optional
        reviewers/secretaries when that improves arrivals and workload. Every
        accepted change preserves time, roles, mentor seats and affiliation.
        """
        score = self.attendance_score()
        for _ in range(3):
            improved = False
            for plan in self.plans:
                group = plan.group
                people = participants(group, self.students)
                original_slot = group.time_slot
                best_slot, best_score = original_slot, score
                for slot in self.slots:
                    if slot == original_slot or not people <= self.available_ids[slot]:
                        continue
                    if any(self.occupied(tid, slot, group.group_id) for tid in people):
                        continue
                    self.reserve(group.group_id, slot, people, len(group.student_ids))
                    candidate = self.attendance_score()
                    if candidate < best_score:
                        best_slot, best_score = slot, candidate
                    self.reserve(group.group_id, original_slot, people, len(group.student_ids))
                if best_slot != original_slot:
                    group.time_slot = best_slot
                    self.reserve(group.group_id, best_slot, people, len(group.student_ids))
                    score, improved = best_score, True
                mentors = {self.student_map[sid].supervisor_id for sid in group.student_ids}
                for old in [*group.expert_ids, group.secretary_id]:
                    if old in mentors:
                        continue
                    secretary = old == group.secretary_id
                    candidates = self.secretary_ids if secretary else self.expert_ids
                    for tid in sorted(candidates - people, key=lambda t: self.rank(t, group.time_slot)):
                        if tid in mentors or tid not in self.available_ids[group.time_slot] or self.occupied(tid, group.time_slot):
                            continue
                        replacement = (people - {old}) | {tid}
                        reviewers = {group.chair_id, *group.expert_ids}
                        if not secretary:
                            reviewers = (reviewers - {old}) | {tid}
                        if sum(self.teacher_map[t].is_external for t in reviewers) > self.rules.get('external_expert_max', 1):
                            continue
                        # Do not replace the requested external seat merely to
                        # improve fairness; rotate within the same affiliation.
                        if not secretary and self.teacher_map[old].is_external != self.teacher_map[tid].is_external:
                            continue
                        if any(self.conflicts_with(t, replacement - {t}) for t in replacement):
                            continue
                        self.reserve(group.group_id, group.time_slot, replacement, len(group.student_ids))
                        candidate = self.attendance_score()
                        if candidate < score:
                            if secretary:
                                group.secretary_id = tid
                            else:
                                group.expert_ids[group.expert_ids.index(old)] = tid
                            people, score, improved = replacement, candidate, True
                            break
                        self.reserve(group.group_id, group.time_slot, people, len(group.student_ids))
            if not improved:
                break

    def run(self):
        from algorithm import make_conflict, serialize_group
        self.assign_chairs()
        self.assign_staff()
        self.assign_students()
        # A shortage must be explicit, never represented as a tiny valid group.
        for plan in list(self.plans):
            if len(plan.group.student_ids) < self.rules.get('group_min', 1):
                for sid in plan.group.student_ids:
                    self.reasons[sid] = f'满足导师、时间与专家资格的组合不足每组至少 {self.rules["group_min"]} 人，请调整组合或日期后重试'
                self.release(plan.group.group_id)
                self.plans.remove(plan)
        self.compact_attendance()
        cross_group = None
        if self.rules['defense_type'] == 'pre' and self.rules.get('group_min', 1) >= 5:
            from .cross_group import CrossGroupRepair
            cross_group = CrossGroupRepair(self).run()
            if cross_group['accepted_pairs']:
                self.compact_attendance()
        groups = [plan.group for plan in self.plans]
        if self.rules['defense_type'] == 'pre':
            from .group_order import finalize_pre_group_numbers
            groups, names = finalize_pre_group_numbers(groups)
            self.reservations = {names.get(gid, gid): value for gid, value in self.reservations.items()}
            self.plans.sort(key=lambda p: p.group.group_id)
            self.invalidate_calendar()
        from .fairness import distribution_metrics
        fairness = distribution_metrics(groups, self.students, self.teachers)
        validation_rules = {**self.rules, 'pre_group_order': True} if self.rules['defense_type'] == 'pre' else self.rules
        conflicts = validate(groups, self.students, self.teachers, validation_rules)
        for conflict in conflicts:
            if conflict['type'] == 'missing_student' and conflict.get('student_id') in self.reasons:
                sid = conflict['student_id']
                student = self.student_map[sid]
                conflict['description'] = f'学生 {student.name} 未安排：{self.reasons[sid]}（已尝试局部补排）'
        if self.reasons and (self.search_limited or self.candidates_limited):
            conflicts.append(make_conflict('search_limit',
                '本次候选或回溯搜索达到保护上限，已保留满足硬约束的部分安排；未安排不代表无可行解，请先按各学生列出的未安排原因处理', []))
        return {'groups': [serialize_group(g) for g in groups], 'conflicts': conflicts,
                'diagnostics': {'algorithm': 'personnel-first-3', 'staff_search_nodes': self.search_nodes,
                                'fairness': fairness,
                                'cross_group': cross_group,
                                'combination_nodes': self.combination_nodes,
                                'packing': self.packing_diagnostics,
                                'search_limited': self.search_limited, 'candidates_limited': self.candidates_limited},
                'unassigned_students': [{'id': s.id, 'name': s.name, 'reason': self.reasons[s.id]}
                                        for s in self.students if s.id in self.reasons]}
