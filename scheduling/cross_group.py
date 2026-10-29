"""Bounded two-group student repartitioning with transactional personnel repair."""
from collections import Counter, defaultdict
from itertools import combinations, product

from .current import participants, validate
from .fairness import distribution_metrics, panel_cost


class CrossGroupRepair:
    MAX_PAIRS = 80
    MAX_SPLITS = 6
    MAX_STAFF_OPTIONS = 8
    MAX_ROUNDS = 3
    MAX_COMBINATION_NODES = 150000

    def __init__(self, planner):
        self.p = planner
        self.checked = self.accepted = 0
        self.started_nodes = planner.combination_nodes

    def counts(self, group):
        return Counter(self.p.student_map[sid].supervisor_id for sid in group.student_ids)

    def cost(self, group):
        return panel_cost(self.counts(group), self.p.rules['group_size'], self.p.rules['expert_count'])

    def quality(self):
        return (sum(self.cost(plan.group) for plan in self.p.plans)
                + sum(len(visits) ** 2 for visits in self.p.calendar().values()))

    def exhausted(self):
        return (self.checked >= self.MAX_PAIRS or
                self.p.combination_nodes - self.started_nodes >= self.MAX_COMBINATION_NODES or
                self.p.combination_nodes >= self.p.MAX_COMBINATION_NODES)

    def partitions(self, left, right):
        """Enumerate mentor quotas, then bind IDs with minimum unnecessary moves."""
        old_left, old_right = self.counts(left), self.counts(right)
        total = old_left + old_right
        mentors = sorted(total, key=str)
        minimum, maximum = self.p.rules.get('group_min', 1), self.p.rules['group_max']
        experts = self.p.rules['expert_count']
        external_max = self.p.rules.get('external_expert_max', 1)
        options = []
        majority = sum(len(plan.group.student_ids) == self.p.rules['group_size'] for plan in self.p.plans)
        old_targets = sum(len(g.student_ids) == self.p.rules['group_size'] for g in (left, right))
        # At most 14 students, with an explicit bound even for legacy inputs.
        if sum(total.values()) > 14:
            return []
        for seats in product(*(range(total[t] + 1) for t in mentors)):
            a = Counter({tid: n for tid, n in zip(mentors, seats) if n})
            b = total - a
            if not (minimum <= sum(a.values()) <= maximum and minimum <= sum(b.values()) <= maximum):
                continue
            if len(a) > experts or len(b) > experts:
                continue
            if any(sum(self.p.teacher_map[t].is_external for t in c) > external_max for c in (a, b)):
                continue
            if a == old_left and b == old_right:
                continue
            targets = sum(sum(c.values()) == self.p.rules['group_size'] for c in (a, b))
            if 2 * majority >= len(self.p.plans) and 2 * (majority - old_targets + targets) < len(self.p.plans):
                continue
            score = sum(panel_cost(c, self.p.rules['group_size'], experts) for c in (a, b))
            moves = sum(abs(a[t] - old_left[t]) for t in mentors)
            options.append((score, moves, seats, a, b))
        return [(a, b) for _, _, _, a, b in sorted(options, key=lambda item: item[:3])[:self.MAX_SPLITS]]

    def bind(self, left, right, counts):
        by_mentor = defaultdict(list)
        for sid in [*left.student_ids, *right.student_ids]:
            by_mentor[self.p.student_map[sid].supervisor_id].append(sid)
        original = set(left.student_ids)
        a, b = [], []
        for tid, ids in by_mentor.items():
            ids.sort(key=lambda sid: (sid not in original, sid))
            a.extend(ids[:counts[tid]])
            b.extend(ids[counts[tid]:])
        return a, b

    def staff_options(self, old, counts, ids, preferred_slots):
        from algorithm import GroupDraft
        from .personnel_first import Demand
        demand = Demand(old.campus, counts)
        slots = list(dict.fromkeys([*preferred_slots, *self.p.slots]))
        produced = 0
        for slot in slots:
            if self.exhausted():
                return
            eligible = self.p.eligible(demand, slot)
            if not set(counts) <= eligible:
                continue
            chairs = sorted(self.p.chair_ids & eligible,
                            key=lambda tid: (tid != old.chair_id, tid not in counts, self.p.rank(tid, slot)))[:4]
            for chair in chairs:
                for members, secretary in self.p.panel_options(demand, slot, chair, eligible, limit=2):
                    yield GroupDraft(old.group_id, old.campus, list(ids), slot, None, chair, list(members), secretary)
                    produced += 1
                    if produced >= self.MAX_STAFF_OPTIONS:
                        return

    def try_pair(self, left_plan, right_plan):
        left, right = left_plan.group, right_plan.group
        quotas = self.partitions(left, right)
        if not quotas:
            return False
        original = {g.group_id: self.p.reservations[g.group_id] for g in (left, right)}
        before = self.quality()
        before_pair = self.cost(left) + self.cost(right)
        before_fair = sum(len(visits) ** 2 for visits in self.p.calendar().values())
        best, best_score = None, before
        # Every probe is temporary; plans remain untouched until a whole pair
        # has passed staffing and global hard-constraint validation.
        try:
            for gid in original:
                self.p.release(gid)
            rest_visits = Counter({tid: len(visits) for tid, visits in self.p.calendar().items()})
            rest_square = sum(n * n for n in rest_visits.values())
            rest_cost = before - before_pair - before_fair
            for a, b in quotas:
                if self.exhausted():
                    break
                ids_a, ids_b = self.bind(left, right, a)
                for ga in self.staff_options(left, a, ids_a, [left.time_slot, right.time_slot]):
                    people_a = participants(ga, self.p.students)
                    self.p.reserve(ga.group_id, ga.time_slot, people_a, len(ids_a))
                    try:
                        for gb in self.staff_options(right, b, ids_b, [right.time_slot, left.time_slot]):
                            people_b = participants(gb, self.p.students)
                            counts = rest_visits.copy()
                            counts.update(people_a)
                            counts.update(people_b)
                            score = rest_cost + self.cost(ga) + self.cost(gb) + rest_square + sum(
                                counts[t] ** 2 - rest_visits[t] ** 2 for t in people_a | people_b)
                            if score < best_score:
                                best, best_score = (ga, gb), score
                    finally:
                        self.p.release(ga.group_id)
        finally:
            for gid, reservation in original.items():
                self.p.reserve(gid, *reservation)
        if best is None:
            return False
        proposed = [best[0] if plan is left_plan else best[1] if plan is right_plan else plan.group
                    for plan in self.p.plans]
        soft = {'external_distribution', 'half_day_coverage', 'student_group_exception', 'missing_student',
                'mentor_student_imbalance', 'pre_group_capacity'}
        if any(c['type'] not in soft for c in validate(proposed, self.p.students, self.p.teachers, self.p.rules)):
            return False
        from .personnel_first import Demand
        for plan, group in zip((left_plan, right_plan), best):
            plan.group = group
            plan.demand = Demand(group.campus, self.counts(group))
            self.p.reserve(group.group_id, group.time_slot, participants(group, self.p.students), len(group.student_ids))
        self.accepted += 1
        return True

    def run(self):
        before = distribution_metrics([plan.group for plan in self.p.plans], self.p.students, self.p.teachers)
        before_quality = self.quality()
        for _ in range(self.MAX_ROUNDS):
            changed = False
            pairs = [(a, b) for a, b in combinations(self.p.plans, 2) if a.group.campus == b.group.campus]
            pairs.sort(key=lambda pair: (-(self.cost(pair[0].group) + self.cost(pair[1].group)),
                                         pair[0].group.group_id, pair[1].group.group_id))
            for a, b in pairs:
                if self.exhausted():
                    break
                changed |= self.try_pair(a, b)
                self.checked += 1
            if not changed or self.exhausted():
                break
        after = distribution_metrics([plan.group for plan in self.p.plans], self.p.students, self.p.teachers)
        return {'checked_pairs': self.checked, 'accepted_pairs': self.accepted,
                'search_limited': self.exhausted(), 'before_quality': before_quality, 'after_quality': self.quality(),
                'before_share_excess': before['share_excess'], 'after_share_excess': after['share_excess'],
                'before_appearance_square_sum': before['appearance_square_sum'],
                'after_appearance_square_sum': after['appearance_square_sum']}
