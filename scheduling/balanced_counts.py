"""Bounded integer packing of mentor seat counts, before assigning identities."""
from collections import Counter
from collections import defaultdict
from heapq import heappush, heappushpop
from itertools import combinations, product
from random import Random
from math import ceil
from .fairness import mentor_share_excess, panel_cost


def pack_counts(counts, target, minimum, maximum, experts, external_max,
                teacher_map, chair_ids, feasible, seeds=()):
    """Jointly balance group size, mentor shares and mentor appearances.

    Columns describe mentor seat quotas, never student IDs. Uncovered seats
    have a dominant cost, so an optimizer timeout keeps an explicit partial
    result rather than inventing a small panel or violating availability.
    """
    import numpy as np
    from scipy.sparse import csc_matrix
    from scipy.optimize._highspy import _core as highs_core

    mentors = sorted(counts, key=str)
    # Coverage dominates; the three quality goals use comparable unit costs.
    total = sum(counts.values())
    secondary_bound = sum(n * n for n in counts.values()) + total * (experts + 1)
    deviation_bound = max((minimum - target) ** 2, (maximum - target) ** 2)
    uncovered_weight = total * (maximum ** 2 + deviation_bound + 1) + secondary_bound + 1
    rows, cols, values, candidates, costs, bounds = [], [], [], [], [], []
    index = {tid: i for i, tid in enumerate(mentors)}
    shortlists = defaultdict(list)
    legacy_shortlists = defaultdict(list)
    complete_candidates = set()
    def member_sets(length):
        if length <= 3:
            yield from combinations(mentors, length)
            return
        # Five-reviewer mode must consider four/five mentors too. Bound this
        # extension explicitly rather than enumerating n-choose-five sets.
        rng = Random(100 + length)
        choices = set()
        for anchor in mentors:
            if anchor not in teacher_map:
                continue
            external = [tid for tid in mentors if tid != anchor and tid in teacher_map and teacher_map[tid].is_external]
            internal = [tid for tid in mentors if tid != anchor and tid in teacher_map and not teacher_map[tid].is_external]
            anchor_external = int(teacher_map[anchor].is_external)
            for external_count in range(anchor_external, min(external_max, length) + 1):
                take_external = external_count - anchor_external
                take_internal = length - 1 - take_external
                if take_external > len(external) or take_internal > len(internal):
                    continue
                # Sample within feasible affiliation counts rather than mostly
                # drawing prohibited three/four-external combinations.
                for _ in range(64):
                    choices.add(tuple(sorted([anchor, *rng.sample(external, take_external),
                                              *rng.sample(internal, take_internal)], key=str)))
        yield from sorted(choices, key=str)

    for length in range(1, min(experts, len(mentors)) + 1):
        for members in member_sets(length):
            if any(t not in teacher_map for t in members):
                continue
            external = sum(teacher_map[t].is_external for t in members)
            if external > external_max or (length == experts and not chair_ids.intersection(members)):
                continue
            if sum(min(counts[t], maximum) for t in members) < minimum:
                continue
            if not feasible(Counter({t: 1 for t in members})):
                continue
            for seats in product(*(range(1, min(counts[t], maximum - length + 1) + 1) for t in members)):
                size = sum(seats)
                if not minimum <= size <= maximum:
                    continue
                if (len(mentors) <= 30 and length <= 3) or length < 3:
                    complete_candidates.add((members, seats))
                    continue
                # Keep alternatives for EVERY mentor, size and affiliation
                # count. A deterministic mix avoids favoring low teacher IDs.
                mix = sum((index[t] + 13) ** 3 * (n + 7) for t, n in zip(members, seats)) % 104729
                item = (-mentor_share_excess(Counter(dict(zip(members, seats))), experts), -mix, members, seats)
                for tid in members:
                    if length == 3:
                        legacy = legacy_shortlists[tid, size, external]
                        legacy_item = (-mix, members, seats)
                        if len(legacy) < 64:
                            heappush(legacy, legacy_item)
                        else:
                            heappushpop(legacy, legacy_item)
                    heap = shortlists[tid, size, external]
                    if len(heap) < 64:
                        heappush(heap, item)
                    else:
                        heappushpop(heap, item)
    seed_keys = []
    for seed in seeds:
        if minimum <= sum(seed.values()) <= maximum and feasible(seed):
            members = tuple(sorted(seed, key=str))
            seed_keys.append((members, tuple(seed[t] for t in members)))
    selected = sorted({(members, seats) for heap in shortlists.values() for _, _, members, seats in heap}
                      | {(members, seats) for heap in legacy_shortlists.values() for _, members, seats in heap}
                      | set(seed_keys) | complete_candidates)
    for members, seats in selected:
        column = len(candidates)
        demand = Counter(dict(zip(members, seats)))
        size = sum(seats)
        external = sum(teacher_map[t].is_external for t in members)
        candidates.append(demand)
        costs.append(panel_cost(demand, target, experts) + .001 * max(0, external - 1) + .00001)
        bounds.append(min(counts[t] // n for t, n in demand.items()))
        for tid, value in demand.items():
            rows.append(index[tid]); cols.append(column); values.append(value)
            rows.append(len(mentors) + index[tid]); cols.append(column); values.append(1)
    count = len(candidates)
    for tid in mentors:
        rows.append(index[tid]); cols.append(len(costs)); values.append(1)
        costs.append(uncovered_weight)
        bounds.append(counts[tid])
    attendance_columns = {}
    for tid in mentors:
        attendance_columns[tid] = []
        for visit in range(1, counts[tid] + 1):
            attendance_columns[tid].append(len(costs))
            rows.append(len(mentors) + index[tid]); cols.append(len(costs)); values.append(-1)
            costs.append(2 * visit - 1)
            bounds.append(1)
    if not mentors:
        return [], {'status': 'empty', 'candidates': 0}
    matrix = csc_matrix((np.array(values, dtype=float), (np.array(rows), np.array(cols))),
                        shape=(2 * len(mentors), len(costs)))
    totals = np.array([counts[t] for t in mentors] + [0] * len(mentors), dtype=float)
    lookup = {key: i for i, key in enumerate(selected)}
    initial = np.zeros(len(costs))
    for key in seed_keys:
        initial[lookup[key]] += 1
    initial[count:count + len(mentors)] = totals[:len(mentors)] - matrix[:len(mentors), :count] @ initial[:count]
    for tid in mentors:
        visits = sum(initial[i] for i, candidate in enumerate(candidates) if tid in candidate)
        for column in attendance_columns[tid][:int(visits)]:
            initial[column] = 1
    # A moderate first objective finds incumbents faster than a single heavily
    # weighted objective. Refine headcounts only after protecting its coverage.
    refinement_costs = np.array(costs, dtype=float)
    costs = np.array([100 * (sum(d.values()) - target) ** 2 + mentor_share_excess(d, experts)
                      + 1000 * int(sum(d.values()) == 4)
                      + max(0, sum(teacher_map[t].is_external for t in d) - 1) + .01
                      for d in candidates]
                     + [100 * uncovered_weight + 1000 * total * int(minimum == 4)] * len(mentors)
                     + list(costs[count + len(mentors):]), dtype=float)
    assert len(costs) == matrix.shape[1]
    # SciPy's pinned HiGHS binding accepts an incumbent. Starting from the
    # validated greedy cover ensures a timeout can never discard that cover.
    lp = highs_core.HighsLp()
    lp.num_col_, lp.num_row_ = len(costs), 2 * len(mentors)
    coverage_bounds = list(bounds)
    for i, demand in enumerate(candidates):
        if len(demand) > 3 and not initial[i]:
            coverage_bounds[i] = 0
    if not sum(initial[count:count + len(mentors)]):
        coverage_bounds[count:count + len(mentors)] = [0] * len(mentors)
    lp.col_cost_, lp.col_lower_, lp.col_upper_ = costs, np.zeros(len(costs)), coverage_bounds
    lp.row_lower_, lp.row_upper_ = totals, totals
    lp.a_matrix_.format_ = highs_core.MatrixFormat.kColwise
    lp.a_matrix_.num_col_, lp.a_matrix_.num_row_ = len(costs), 2 * len(mentors)
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = matrix.indptr, matrix.indices, matrix.data
    lp.integrality_ = [highs_core.HighsVarType.kInteger] * len(costs)
    solver = highs_core._Highs()
    solver.setOptionValue('output_flag', False)
    solver.setOptionValue('time_limit', 45.0)
    solver.setOptionValue('threads', 1)
    solver.setOptionValue('random_seed', 0)
    solver.setOptionValue('mip_rel_gap', .01)
    solver.setOptionValue('mip_heuristic_effort', .5)
    solver.passModel(lp)
    incumbent = initial.copy()
    coverage_seed = 'greedy'
    full_cover_status = 'not_needed'
    all_columns = np.arange(len(costs), dtype=np.int32)
    missing_columns = np.arange(count, count + len(mentors), dtype=np.int32)
    external_visits = sum(ceil(n / maximum) for tid, n in counts.items()
                          if tid in teacher_map and teacher_map[tid].is_external)
    preferred_groups = max(ceil(total / maximum), (total + target // 2) // target,
                           ceil(external_visits / external_max))
    preferred_groups = min(preferred_groups, total // minimum) if total // minimum >= ceil(total / maximum) else None
    prefer_group_count = preferred_groups is not None and round(sum(initial[:count])) != preferred_groups
    group_row = False
    if count and (sum(initial[count:count + len(mentors)]) > 0 or prefer_group_count):
        # A dedicated feasibility model is much easier than simultaneously
        # finding complete coverage and optimizing several quality objectives.
        # Once found, this cover remains an incumbent across every timeout.
        solver.changeColsBounds(len(mentors), missing_columns, np.zeros(len(mentors)), np.zeros(len(mentors)))
        solver.changeColsCost(len(costs), all_columns, np.zeros(len(costs)))
        if preferred_groups is not None:
            solver.addRow(preferred_groups, preferred_groups, count, np.arange(count, dtype=np.int32), np.ones(count))
            group_row = True
        solver.setOptionValue('time_limit', 15.0)
        solver.run()
        full_cover_status = str(solver.getModelStatus())
        full = solver.getSolution()
        if full.value_valid:
            values = np.array(full.col_value)
            rounded = np.rint(values)
            if (len(values) == len(costs) and np.max(np.abs(values - rounded)) <= 1e-5
                    and np.allclose(matrix @ rounded, totals)
                    and not sum(rounded[count:count + len(mentors)])):
                incumbent = rounded
                coverage_seed = 'full_cover_search'
        if coverage_seed != 'full_cover_search' and group_row:
            solver.deleteRows(1, np.array([matrix.shape[0]], dtype=np.int32))
            group_row = False
            if sum(incumbent[count:count + len(mentors)]) > 0:
                solver.clearSolver()
                solver.run()
                full = solver.getSolution()
                if full.value_valid:
                    values = np.array(full.col_value)
                    rounded = np.rint(values)
                    if (np.max(np.abs(values - rounded)) <= 1e-5 and np.allclose(matrix @ rounded, totals)
                            and not sum(rounded[count:count + len(mentors)])):
                        incumbent = rounded
                        coverage_seed = 'full_cover_search'
        solver.clearSolver()
        if not sum(incumbent[count:count + len(mentors)]):
            coverage_bounds[count:count + len(mentors)] = [0] * len(mentors)
        solver.changeColsBounds(len(costs), all_columns, np.zeros(len(costs)), np.array(coverage_bounds, dtype=float))
        solver.changeColsCost(len(costs), all_columns, costs)
        solver.setOptionValue('time_limit', 45.0)
    solver.setSolution(len(costs), all_columns, incumbent)
    solver.run()
    solved = solver.getSolution()
    candidate = np.array(solved.col_value) if solved.value_valid else incumbent
    if len(candidate) != len(costs) or np.dot(costs, candidate) > np.dot(costs, incumbent):
        candidate = incumbent
    if solver.getModelStatus() != highs_core.HighsModelStatus.kOptimal and count > 100:
        solver.clearSolver()
        solver.setOptionValue('time_limit', 25.0)
        solver.setOptionValue('random_seed', 1)
        solver.setSolution(len(costs), np.arange(len(costs), dtype=np.int32), candidate)
        solver.run()
        next_solution = solver.getSolution()
        if next_solution.value_valid and np.dot(costs, next_solution.col_value) < np.dot(costs, candidate):
            candidate = np.array(next_solution.col_value)
    coverage_status = str(solver.getModelStatus())
    if count:
        # This extra constraint prevents the size optimization from discarding
        # students already covered, even when the search times out.
        missing_columns = np.arange(count, count + len(mentors), dtype=np.int32)
        solver.clearSolver()
        solver.changeColsBounds(len(costs), np.arange(len(costs), dtype=np.int32),
                                np.zeros(len(costs)), np.array(bounds, dtype=float))
        solver.addRow(0, round(sum(candidate[count:count + len(mentors)])),
                      len(mentors), missing_columns, np.ones(len(mentors)))
        # Preserve a feasible majority of target-sized panels, while allowing
        # the joint quality objective to trade some sixes for fairer shares.
        majority = np.array([1.0 if sum(d.values()) == target else -1.0 for d in candidates])
        if np.dot(majority, candidate[:count]) >= 0:
            solver.addRow(0, np.inf, count, np.arange(count, dtype=np.int32), majority)
        solver.changeColsCost(len(costs), np.arange(len(costs), dtype=np.int32), refinement_costs)
        solver.setOptionValue('time_limit', 25.0)
        solver.setOptionValue('mip_rel_gap', 0.0)
        solver.setOptionValue('random_seed', 2)
        solver.setSolution(len(costs), np.arange(len(costs), dtype=np.int32), candidate)
        solver.run()
        refined = solver.getSolution()
        if refined.value_valid:
            proposed = np.array(refined.col_value)
            integral = np.rint(proposed)
            if (np.max(np.abs(proposed - integral)) <= 1e-5
                    and np.allclose(matrix @ integral, totals)
                    and sum(integral[count:count + len(mentors)]) <= round(sum(candidate[count:count + len(mentors)]))
                    and np.dot(refinement_costs, integral) < np.dot(refinement_costs, candidate)):
                candidate = integral
    integers = np.rint(candidate).astype(int)
    # Never trust a timed-out solver's non-integral or infeasible incumbent.
    if (np.max(np.abs(candidate - integers)) > 1e-5
            or not np.allclose(matrix @ integers, totals)):
        return [], {'status': 'search_limit', 'candidates': count}
    packed = [Counter(candidate) for candidate, copies in zip(candidates, integers[:count])
              for _ in range(int(copies))]
    return packed, {'status': 'feasible' if solver.getModelStatus() == highs_core.HighsModelStatus.kOptimal else 'bounded',
                    'solver_status': str(solver.getModelStatus()),
                    'coverage_solver_status': coverage_status,
                    'coverage_seed': coverage_seed, 'full_cover_status': full_cover_status,
                    'preferred_groups': preferred_groups, 'group_count_protected': group_row,
                    'initial_cost': round(float(np.dot(costs, initial)), 2),
                    'final_cost': round(float(np.dot(costs, candidate)), 2),
                    'candidates': count, 'uncovered': int(sum(integers[count:count + len(mentors)]))}
