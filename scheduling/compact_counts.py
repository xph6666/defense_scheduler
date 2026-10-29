"""Small exact count models: replace six seven-seat groups by seven sixes."""
from collections import Counter


def repack_sixes(packed, experts, external_max, teacher_map, chair_ids, feasible, limit=None):
    """limit：最多再增加的组数（每次重编增加 1 组）；为 None 时不限，按原规则最多三次。"""
    import numpy as np
    from scipy.sparse import csc_matrix
    from scipy.optimize._highspy import _core as h
    result = [Counter(c) for c in packed]
    accepted = 0
    for _ in range(3 if limit is None else min(3, limit)):
        indexes = [i for i, c in enumerate(result) if sum(c.values()) == 7][:6]
        if len(indexes) != 6:
            break
        totals = sum((result[i] for i in indexes), Counter())
        mentors = sorted(totals, key=str)
        costs, upper = [], []
        rows, columns, values, lows, highs = [], [], [], [], []
        def variable(cost, limit):
            costs.append(cost); upper.append(limit)
            return len(costs) - 1
        def constraint(terms, low, high):
            row = len(lows); lows.append(low); highs.append(high)
            for col, value in terms:
                rows.append(row); columns.append(col); values.append(value)
        x, y = {}, {}
        for tid in mentors:
            for group in range(7):
                limit = min(6, totals[tid])
                x[tid, group], y[tid, group] = variable(0, limit), variable(0, 1)
                increments = [variable((2 * seat - 1) / 2, 1) for seat in range(1, limit + 1)]
                constraint([(x[tid, group], 1), *[(col, -1) for col in increments]], 0, 0)
                constraint([(x[tid, group], 1), (y[tid, group], -limit)], -np.inf, 0)
                constraint([(x[tid, group], 1), (y[tid, group], -1)], 0, np.inf)
            constraint([(x[tid, group], 1) for group in range(7)], totals[tid], totals[tid])
            visits = [variable(2 * visit - 1, 1) for visit in range(1, 8)]
            constraint([(y[tid, group], 1) for group in range(7)] + [(col, -1) for col in visits], 0, 0)
        for group in range(7):
            constraint([(x[tid, group], 1) for tid in mentors], 6, 6)
            constraint([(y[tid, group], 1) for tid in mentors], 1, experts)
            constraint([(y[tid, group], 1) for tid in mentors if teacher_map[tid].is_external], 0, external_max)
            # If every reviewer seat is a required mentor, one must qualify as chair.
            constraint([(y[tid, group], 1 if tid in chair_ids else -experts) for tid in mentors],
                       -experts * (experts - 1), np.inf)
        matrix = csc_matrix((values, (rows, columns)), shape=(len(lows), len(costs)))
        model = h.HighsLp()
        model.num_col_, model.num_row_ = len(costs), len(lows)
        model.col_cost_, model.col_lower_, model.col_upper_ = costs, np.zeros(len(costs)), upper
        model.row_lower_, model.row_upper_ = lows, highs
        model.integrality_ = [h.HighsVarType.kInteger] * len(costs)
        model.a_matrix_.format_ = h.MatrixFormat.kColwise
        model.a_matrix_.num_col_, model.a_matrix_.num_row_ = len(costs), len(lows)
        model.a_matrix_.start_, model.a_matrix_.index_, model.a_matrix_.value_ = matrix.indptr, matrix.indices, matrix.data
        solver = h._Highs()
        for key, value in [('output_flag', False), ('threads', 1), ('random_seed', 0), ('time_limit', 8.0)]:
            solver.setOptionValue(key, value)
        solver.passModel(model); solver.run()
        solution = solver.getSolution()
        if not solution.value_valid:
            break
        raw = np.array(solution.col_value); rounded = np.rint(raw)
        if np.max(abs(raw - rounded)) > 1e-5:
            break
        proposed = [Counter({tid: int(rounded[x[tid, group]]) for tid in mentors if rounded[x[tid, group]]})
                    for group in range(7)]
        if (sum(proposed, Counter()) != totals or any(sum(c.values()) != 6 or not feasible(c) for c in proposed)):
            break
        kept = [c for i, c in enumerate(result) if i not in indexes]
        result = kept + proposed
        accepted += 1
    return result, accepted
