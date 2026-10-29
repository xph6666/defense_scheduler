"""正式答辩专家轮换：沿用预答辩各组的学生和秘书，主席与专家全部重新分配。

业务规则（2026-10-30 用户确认）：
- 组号、学生、秘书沿用当前预答辩；本组预答辩的组长和专家不再评审本组。
- 导师回避：评审不能是本组学生的导师，导师不要求到场。
- 按预答辩原组号自然升序安排日期和半天；允许同一半天并行多组。
- 每组恰好 expert_count 位评审（含主席），外院至多 external_expert_max 位，其余为本院。
- 主席优先达到正式答辩职称要求（教授），人数不足时放宽到预答辩组长职称，并逐组提示。
- 软目标：集中在最早的几天；同一教师同一天只在一个校区；评审出场次数均衡。

求解分两步，均为确定性计算：
1. 放置：小规模整数规划确定各组所在半天，受秘书和各半天评审容量约束；再逐个半天用
   指派问题校核，校核不可行时禁止该组留在该半天并重新规划。
2. 指派：逐个半天用指派问题分配主席与专家，再按全局目标逐个半天重新指派，直到不再改进。
有限规模内的近似求解不承诺全局最优；所有结果最后都经过全局硬约束校验。
"""
from collections import Counter, defaultdict
from dataclasses import dataclass

from .current import available, validate
from .group_order import group_order_key
from .policies import formal_chair_level, secretary_is_qualified, teacher_can_role

# 指派代价；BIG 表示该席位不允许安排此教师
BIG = 1e9
W_TITLE = 400            # 主席职称低于正式要求（按放宽要求安排）
W_EXTERNAL_CHAIR = 300   # 外院教师任主席（院内主席优先）
W_NO_EXTERNAL = 150      # 外院席位改由本院教师担任
W_CROSS = 200            # 同一教师同一天在两个校区
W_NEW_DAY = 25           # 教师当天新增一次到场
W_FAIR = 10              # 评审出场次数平方和

# 放置代价：未安排远大于多用一天，多用一天远大于秘书跨校区等软目标
P_UNPLACED = 100000      # 每名未安排学生
P_DAY = 1000             # 每使用一天（越靠后略贵，使安排集中在最前面的几天）
P_SECRETARY_CROSS = 200  # 秘书同一天在两个校区
P_MISMATCH = 60          # 同一天上午、下午某校区组数之差（评审需跨校区或空闲）
P_OVERLOAD = 30          # 半天满负荷时多出的一组（为同日同校区留余地）


@dataclass(frozen=True)
class Shell:
    """沿用自预答辩的小组；excluded 为不能评审本组的教师（导师、原评审、秘书及与秘书回避者）。"""
    group_id: str
    campus: str | None
    student_ids: tuple
    secretary_id: int
    excluded: frozenset


def rotate_panels(source, teachers, students, rules):
    """入口：source 为预答辩 GroupDraft 列表，返回与排期生成相同结构的结果。"""
    return FormalRotation(source, teachers, students, rules).run()


class Ledger:
    """除正在指派的半天外的已定安排：评审出场次数，以及教师在各半天所在的校区。"""

    def __init__(self, planner, placement, panels, skip):
        self.planner = planner
        self.reviews = Counter()
        self.duty = {}
        for index, t in placement.items():
            if t == skip:
                continue
            shell = planner.shells[index]
            key = (planner.slot_day[t], planner.slot_half[t])
            self.duty[(shell.secretary_id, *key)] = shell.campus
            panel = panels.get(shell.group_id)
            if panel:
                for tid in (panel[0], *panel[1]):
                    self.reviews[tid] += 1
                    self.duty[(tid, *key)] = shell.campus

    def teacher_cost(self, tid, t, campus):
        """在半天 t、校区 campus 再安排该教师一次的边际代价（与全局目标一致）。"""
        day, half = self.planner.slot_day[t], self.planner.slot_half[t]
        cost = W_FAIR * (2 * self.reviews[tid] + 1)
        other = self.duty.get((tid, day, 1 - half))
        if other is None:
            return cost + W_NEW_DAY
        return cost if other == campus else cost + W_CROSS


class FormalRotation:
    MAX_PLACEMENT_ROUNDS = 30
    MAX_DESCENT_ROUNDS = 4
    PLACEMENT_TIME_LIMIT = 20.0
    EXTRA_DAYS = 2

    def __init__(self, source, teachers, students, rules):
        from algorithm import build_candidate_slots
        self.rules, self.teachers, self.students = rules, teachers, students
        self.teacher_map = {t.id: t for t in teachers}
        self.student_map = {s.id: s for s in students}
        self.slots = build_candidate_slots(rules, [])
        self.days = sorted({slot.start.date() for slot in self.slots})
        day_index = {day: index for index, day in enumerate(self.days)}
        self.slot_day = [day_index[slot.start.date()] for slot in self.slots]
        self.slot_half = [int(slot.start.hour >= 12) for slot in self.slots]
        self.day_slots = defaultdict(lambda: ([], []))
        for t in range(len(self.slots)):
            self.day_slots[self.slot_day[t]][self.slot_half[t]].append(t)
        self.size = rules['expert_count']
        self.external_max = max(0, int(rules.get('external_expert_max', 1)))
        # 席位结构：主席 1 个、仅本院席位若干、可安排外院的席位至多 external_max 个
        self.flex_seats = min(self.external_max, self.size - 1)
        self.internal_seats = self.size - 1 - self.flex_seats
        self.external = {t.id: bool(t.is_external) for t in teachers}
        self.expert = {t.id: teacher_can_role(t, 'expert') for t in teachers}
        self.chair_level = {t.id: formal_chair_level(t, rules) for t in teachers}
        self.internal_pool = {t.id for t in teachers if not t.is_external
                              and (self.expert[t.id] or self.chair_level[t.id] is not None)}
        self.incompatible = defaultdict(set)
        for teacher in teachers:
            for other in teacher.forbidden_with:
                self.incompatible[teacher.id].add(other)
                self.incompatible[other].add(teacher.id)
        self.free = [frozenset(t.id for t in teachers if available(t, slot)) for slot in self.slots]
        self.reasons = {}
        self.shells = self.build_shells(source)
        self.capacity = [self.slot_capacity(t) for t in range(len(self.slots))]
        self._single = {}
        self.placement_status = 'not_run'
        self.placement_rounds = 0
        self.descent_rounds = 0

    # ------------------------------------------------------------------ 输入
    def build_shells(self, source):
        group_min, group_max = self.rules.get('group_min', 1), self.rules['group_max']
        title = self.rules.get('secretary_title', '讲师')
        shells, inherited = [], set()
        for previous in sorted(source, key=lambda g: group_order_key(g.group_id)):
            ids = tuple(sid for sid in previous.student_ids if sid in self.student_map)
            inherited.update(ids)
            if not ids:
                continue
            label = previous.group_id
            mentors = {self.student_map[sid].supervisor_id for sid in ids} - {None}
            secretary = self.teacher_map.get(previous.secretary_id)
            if not group_min <= len(ids) <= group_max:
                reason = (f'预答辩 {label} 在本阶段的学生人数不满足 {group_min}～{group_max} 人，'
                          '请先调整预答辩或核对参与名单')
            elif secretary is None:
                reason = f'沿用预答辩 {label} 的秘书未参加正式答辩或已停用，请核对教师名单'
            elif not secretary_is_qualified(secretary, title):
                reason = f'沿用预答辩 {label} 的秘书 {secretary.name} 不具备秘书资格'
            elif secretary.id in mentors:
                reason = f'沿用预答辩 {label} 的秘书 {secretary.name} 是本组学生的导师，不能担任本组秘书'
            else:
                reason = None
            if reason:
                for sid in ids:
                    self.reasons[sid] = reason
                continue
            excluded = (mentors | {previous.chair_id, previous.secretary_id, *previous.expert_ids}
                        | self.incompatible[previous.secretary_id]) - {None}
            shells.append(Shell(label, previous.campus, ids, previous.secretary_id, frozenset(excluded)))
        for sid in self.student_map.keys() - inherited:
            self.reasons[sid] = '本轮预答辩未生成该学生的分组，无法沿用；请先完成预答辩安排'
        return shells

    def slot_capacity(self, t):
        """该半天可同时开设组数的估计上界：本院人数、主席人选和评审总人数取最小值。"""
        ids = self.free[t]
        internal = len(ids & self.internal_pool)
        external = any(self.expert[tid] and self.external[tid] for tid in ids)
        chairs = sum(1 for tid in ids if self.chair_level[tid] is not None)
        reviewers = sum(1 for tid in ids if self.expert[tid] or self.chair_level[tid] is not None)
        internal_need = self.size - (self.flex_seats if external else 0)
        return max(0, min(internal // max(1, internal_need), chairs, reviewers // self.size))

    # ------------------------------------------------------------------ 指派
    def seat_cost(self, kind, tid):
        """席位代价；None 表示该教师不能坐此席位。"""
        if kind == 'chair':
            level = self.chair_level.get(tid)
            if level is None:
                return None
            return (W_TITLE if level else 0) + (W_EXTERNAL_CHAIR if self.external[tid] else 0)
        if not self.expert.get(tid):
            return None
        if kind == 'internal':
            return None if self.external[tid] else 0
        return 0 if self.external[tid] else W_NO_EXTERNAL

    def assign_slot(self, t, shells, ledger=None, banned=frozenset()):
        """为同一半天的若干小组指派主席和专家（指派问题）；不可行时返回 None。"""
        import numpy as np
        from scipy.optimize import linear_sum_assignment
        kinds = ['chair'] + ['internal'] * self.internal_seats + ['flex'] * self.flex_seats
        # 本半天各组秘书已被占用，不能同时担任评审
        columns = sorted(self.free[t] - {shell.secretary_id for shell in shells})
        if len(columns) < len(kinds) * len(shells):
            return None

        def seat_array(kind):
            costs = [self.seat_cost(kind, tid) for tid in columns]
            return np.array([BIG if cost is None else cost for cost in costs])

        base = {kind: seat_array(kind) for kind in set(kinds)}
        matrix = np.full((len(kinds) * len(shells), len(columns)), BIG)
        rows = []
        for shell in shells:
            allowed = np.array([tid not in shell.excluded and (shell.group_id, tid) not in banned for tid in columns])
            extra = (np.array([ledger.teacher_cost(tid, t, shell.campus) for tid in columns])
                     if ledger is not None else np.zeros(len(columns)))
            for kind in kinds:
                seat = base[kind]
                matrix[len(rows)] = np.where(allowed & (seat < BIG), seat + extra, BIG)
                rows.append((shell.group_id, kind))
        picked_rows, picked_columns = linear_sum_assignment(matrix)
        chosen = matrix[picked_rows, picked_columns]
        if (chosen >= BIG).any():
            return None
        panels = {}
        for row, column in zip(picked_rows, picked_columns):
            gid, kind = rows[row]
            panel = panels.setdefault(gid, [None, []])
            if kind == 'chair':
                panel[0] = columns[column]
            else:
                panel[1].append(columns[column])
        ordered = {gid: (chair, sorted(experts, key=lambda tid: (self.external[tid], tid)))
                   for gid, (chair, experts) in panels.items()}
        return ordered, float(chosen.sum())

    def violation(self, panels):
        """检查外院人数和回避同组教师；返回需禁止的 (组号, 教师) 或 None。"""
        for gid in sorted(panels):
            chair, experts = panels[gid]
            members = [chair, *experts]
            externals = [tid for tid in members if self.external[tid]]
            if len(externals) > self.external_max:
                # 外院主席占用外院名额时禁止其任本组，优先保留本院主席
                return gid, chair if self.external[chair] else max(externals)
            for tid in members:
                clash = self.incompatible[tid] & set(members)
                if clash:
                    return gid, max(clash)
        return None

    def staff_slot(self, t, shells, ledger=None):
        """带修复的半天指派：违反外院上限或回避同组时追加禁止对后重解。"""
        banned = set()
        for _ in range(len(shells) * self.size + 1):
            solved = self.assign_slot(t, shells, ledger, frozenset(banned))
            if solved is None:
                return None
            problem = self.violation(solved[0])
            if problem is None:
                return solved
            banned.add(problem)
        return None

    def slot_cost(self, t, shells, panels, ledger):
        """按指派代价计算某半天现有安排的代价，与重新指派的结果可直接比较。"""
        total = 0.0
        for shell in shells:
            chair, experts = panels[shell.group_id]
            total += self.seat_cost('chair', chair) + ledger.teacher_cost(chair, t, shell.campus)
            total += W_NO_EXTERNAL * max(0, self.flex_seats - sum(self.external[tid] for tid in experts))
            total += sum(ledger.teacher_cost(tid, t, shell.campus) for tid in experts)
        return total

    # ------------------------------------------------------------------ 放置
    def single_ok(self, index, t):
        """该组单独放在半天 t 时能否组成合格评审组（秘书可用且指派可行）。"""
        key = (index, t)
        if key not in self._single:
            shell = self.shells[index]
            self._single[key] = (shell.secretary_id in self.free[t]
                                 and self.staff_slot(t, [shell]) is not None)
        return self._single[key]

    def lower_bound_days(self):
        loads = Counter(shell.secretary_id for shell in self.shells)
        per_day = max((len(morning) + len(afternoon) for morning, afternoon in self.day_slots.values()), default=2)
        days = max([1] + [-(-load // max(1, per_day)) for load in loads.values()])
        # Repeated secretaries separated by other group numbers still force the
        # following groups forward; estimate this ordered half-day lower bound.
        last, half = {}, 0
        for shell in self.shells:
            half = max(half, last.get(shell.secretary_id, -1) + 1)
            last[shell.secretary_id] = half
        days = max(days, -(-(half + 1) // max(1, per_day)))
        total, needed = 0, 0
        for d in range(len(self.days)):
            if total >= len(self.shells):
                break
            total += sum(self.capacity[t] for half in self.day_slots[d] for t in half)
            needed = d + 1
        return max(days, needed)

    def solve_placement(self, window, banned):
        """整数规划：前 window 天内为各组选半天；返回 ({组序号: 半天}, 状态) 或 (None, 状态)。"""
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_matrix
        slots = [t for t in range(len(self.slots)) if self.slot_day[t] < window]
        costs, upper, integral = [], [], []
        rows, cols, values, lower, high = [], [], [], [], []

        def variable(cost, bound=1.0, integer=True):
            costs.append(cost)
            upper.append(bound)
            integral.append(int(integer))
            return len(costs) - 1

        def constrain(terms, low, up):
            row = len(lower)
            lower.append(low)
            high.append(up)
            for col, value in terms:
                rows.append(row)
                cols.append(col)
                values.append(value)

        # 越早的半天代价越低：同等条件下集中在最前面的几天
        x = {(i, t): variable(0.01 * t) for i in range(len(self.shells)) for t in slots
             if (i, t) not in banned and self.single_ok(i, t)}
        unplaced = [variable(P_UNPLACED * len(shell.student_ids)) for shell in self.shells]
        used = [variable(P_DAY * (1 + 0.001 * d)) for d in range(window)]
        by_shell, at_slot = defaultdict(list), defaultdict(list)
        for (i, t), col in x.items():
            by_shell[i].append(col)
            at_slot[t].append((i, col))
        for i in range(len(self.shells)):
            constrain([(col, 1) for col in by_shell[i]] + [(unplaced[i], 1)], 1, 1)
        # Prefix maxima enforce chronological group order even across unplaced
        # groups. Unplaced groups do not reset the last assigned half-day.
        horizon = max(slots, default=0)
        previous = None
        for i in range(len(self.shells)):
            prefix = variable(0, horizon, False)
            when = [(x[i, t], t) for t in slots if (i, t) in x]
            constrain(when + [(prefix, -1)], -np.inf, 0)
            if previous is not None:
                constrain([(previous, 1), (prefix, -1)], -np.inf, 0)
                constrain([(previous, 1), (unplaced[i], -horizon)] +
                          [(col, -value) for col, value in when], -np.inf, 0)
            previous = prefix
        secretaries = defaultdict(set)
        for i, shell in enumerate(self.shells):
            secretaries[shell.secretary_id].add(i)
        # 同一秘书同一半天最多一组
        for members in secretaries.values():
            for t in slots:
                terms = [(col, 1) for i, col in at_slot[t] if i in members]
                if len(terms) > 1:
                    constrain(terms, -np.inf, 1)
        # 半天容量；只要该半天有组即计为使用当天
        for t in slots:
            terms = [(col, 1) for _, col in at_slot[t]]
            if not terms:
                continue
            capacity = self.capacity[t]
            constrain(terms + [(used[self.slot_day[t]], -capacity)], -np.inf, 0)
            if capacity > 1:
                over = variable(P_OVERLOAD, capacity, False)
                constrain(terms + [(over, -1)], -np.inf, capacity - 1)
        # 秘书同一天尽量只在一个校区
        for members in secretaries.values():
            places = sorted({self.shells[i].campus for i in members}, key=str)
            if len(places) < 2:
                continue
            for d in range(window):
                in_day = [t for half in self.day_slots[d] for t in half]
                flags = []
                for campus in places:
                    terms = [(col, 1) for t in in_day for i, col in at_slot[t]
                             if i in members and self.shells[i].campus == campus]
                    if terms:
                        flag = variable(0)
                        constrain(terms + [(flag, -len(in_day))], -np.inf, 0)
                        flags.append(flag)
                if len(flags) > 1:
                    cross = variable(P_SECRETARY_CROSS, len(flags), False)
                    constrain([(flag, 1) for flag in flags] + [(cross, -1)], -np.inf, 1)
        # 同一天上午、下午各校区组数尽量一致，评审可以整天留在一个校区
        campuses = sorted({shell.campus for shell in self.shells}, key=str)
        if len(campuses) > 1:
            for d in range(window):
                morning, afternoon = self.day_slots[d]
                for campus in campuses:
                    am = [col for t in morning for i, col in at_slot[t] if self.shells[i].campus == campus]
                    pm = [col for t in afternoon for i, col in at_slot[t] if self.shells[i].campus == campus]
                    if not am and not pm:
                        continue
                    gap = variable(P_MISMATCH, len(self.shells), False)
                    constrain([(col, 1) for col in am] + [(col, -1) for col in pm] + [(gap, -1)], -np.inf, 0)
                    constrain([(col, 1) for col in pm] + [(col, -1) for col in am] + [(gap, -1)], -np.inf, 0)
        matrix = coo_matrix((values, (rows, cols)), shape=(len(lower), len(costs))).tocsr()
        result = milp(np.array(costs, dtype=float), integrality=np.array(integral),
                      bounds=Bounds(np.zeros(len(costs)), np.array(upper, dtype=float)),
                      constraints=LinearConstraint(matrix, np.array(lower, dtype=float), np.array(high, dtype=float)),
                      options={'time_limit': self.PLACEMENT_TIME_LIMIT, 'disp': False})
        if result.x is None:
            return None, f'milp_status_{result.status}'
        placement = {i: t for (i, t), col in x.items() if result.x[col] > 0.5}
        return placement, 'optimal' if result.status == 0 else f'milp_status_{result.status}'

    def greedy_placement(self, window, banned):
        """整数规划无解时按原组号依次放置；跳过不可排组时仍保留时间下界。"""
        placement = {}
        at_slot = defaultdict(list)
        earliest = 0
        for i, shell in enumerate(self.shells):
            for t in range(earliest, len(self.slots)):
                if self.slot_day[t] >= window or (i, t) in banned or not self.single_ok(i, t):
                    continue
                chosen = at_slot[t]
                if len(chosen) >= self.capacity[t] or any(
                        self.shells[j].secretary_id == shell.secretary_id for j in chosen):
                    continue
                if self.staff_slot(t, [self.shells[j] for j in chosen] + [shell]) is None:
                    continue
                chosen.append(i)
                placement[i] = t
                earliest = t
                break
        return placement

    def slot_members(self, placement):
        by_slot = defaultdict(list)
        for i, t in placement.items():
            by_slot[t].append(i)
        return {t: sorted(members, key=lambda i: group_order_key(self.shells[i].group_id)) for t, members in by_slot.items()}

    def infeasible_slots(self, placement):
        """逐个半天校核评审可行性；不可行时找出最受限且移出后可行的小组。"""
        culprits = set()
        for t, members in sorted(self.slot_members(placement).items()):
            if self.staff_slot(t, [self.shells[i] for i in members]) is not None:
                continue
            order = sorted(members, key=lambda i: (-len(self.shells[i].excluded & self.internal_pool),
                                                   self.shells[i].group_id))
            culprit = next((i for i in order if self.staff_slot(
                t, [self.shells[j] for j in members if j != i]) is not None), order[0])
            culprits.add((culprit, t))
        return culprits

    def place(self):
        window = min(len(self.days), self.lower_bound_days() + self.EXTRA_DAYS)
        banned, placement = set(), {}
        for rounds in range(1, self.MAX_PLACEMENT_ROUNDS + 1):
            self.placement_rounds = rounds
            baseline = self.greedy_placement(window, banned)
            if len(baseline) == len(self.shells):
                self.placement_status = 'ordered_greedy_complete'
                return baseline
            placement, self.placement_status = self.solve_placement(window, banned)
            if placement is None:
                placement, self.placement_status = baseline, 'ordered_greedy'
            elif sum(len(self.shells[i].student_ids) for i in baseline) > sum(
                    len(self.shells[i].student_ids) for i in placement):
                placement, self.placement_status = baseline, 'ordered_greedy_better_coverage'
            culprits = self.infeasible_slots(placement)
            if culprits:
                banned |= culprits
                continue
            if len(placement) < len(self.shells) and window < len(self.days):
                window = min(len(self.days), window * 2)
                continue
            return placement
        # 达到轮数上限：只保留校核可行的安排，其余小组列为未安排
        while culprits := self.infeasible_slots(placement):
            for i, _ in culprits:
                placement.pop(i, None)
        return placement

    def staff(self, placement):
        """先按时间顺序逐个半天指派，再逐个半天重新指派以降低全局代价。"""
        members = self.slot_members(placement)
        order = sorted(members)
        panels = {}
        for t in order:
            solved = self.staff_slot(t, [self.shells[i] for i in members[t]], Ledger(self, placement, panels, t))
            if solved:
                panels.update(solved[0])
        for rounds in range(1, self.MAX_DESCENT_ROUNDS + 1):
            self.descent_rounds = rounds
            improved = False
            for t in order:
                shells = [self.shells[i] for i in members[t]]
                if any(shell.group_id not in panels for shell in shells):
                    continue
                ledger = Ledger(self, placement, panels, t)
                current = self.slot_cost(t, shells, panels, ledger)
                solved = self.staff_slot(t, shells, ledger)
                if solved and solved[1] < current - 1e-6:
                    panels.update(solved[0])
                    improved = True
            if not improved:
                break
        return panels

    # ------------------------------------------------------------------ 输出
    def unplaced_reason(self, index):
        shell = self.shells[index]
        secretary = self.teacher_map[shell.secretary_id]
        internal = self.size - self.flex_seats
        if not self.slots:
            return '正式答辩日期范围内没有可安排的半天，请检查日期、周末及排除日期设置'
        if not any(shell.secretary_id in ids for ids in self.free):
            return f'沿用的秘书 {secretary.name} 在正式答辩日期内没有可用半天，请核对其时间或调整日期'
        if not any(self.single_ok(index, t) for t in range(len(self.slots))):
            return (f'在正式答辩日期内，找不到满足导师回避、本组原评审全部更换、主席职称及至少 {internal} 位'
                    '本院专家要求的评审组合，请核对教师资格或可用时间')
        return (f'正式答辩日期范围容量不足：须按预答辩原组号依次顺排，共 {len(self.slots)} 个半天，每组需 {self.size} 位专家（本院至少 '
                f'{internal} 位），按教师人数最多约可安排 {sum(self.capacity)} 组；请延长日期范围')

    def run(self):
        from algorithm import GroupDraft, serialize_group
        from .fairness import distribution_metrics
        placement = self.place() if self.shells and self.slots else {}
        panels = self.staff(placement)
        groups = []
        for i, t in sorted(placement.items(), key=lambda item: (item[1], group_order_key(self.shells[item[0]].group_id))):
            shell = self.shells[i]
            if shell.group_id in panels:
                chair, experts = panels[shell.group_id]
                groups.append(GroupDraft(shell.group_id, shell.campus, list(shell.student_ids), self.slots[t],
                                         None, chair, list(experts), shell.secretary_id))
        staffed = {group.group_id for group in groups}
        for i, shell in enumerate(self.shells):
            if shell.group_id not in staffed:
                reason = self.unplaced_reason(i)
                for sid in shell.student_ids:
                    self.reasons[sid] = reason
        conflicts = validate(groups, self.students, self.teachers, self.rules)
        for conflict in conflicts:
            sid = conflict.get('student_id')
            if conflict['type'] == 'missing_student' and sid in self.reasons:
                conflict['description'] = f'学生 {self.student_map[sid].name} 未安排：{self.reasons[sid]}'
        reviews = Counter(tid for group in groups for tid in (group.chair_id, *group.expert_ids))
        internal_loads = Counter(reviews[tid] for tid in sorted(self.internal_pool))
        campuses = defaultdict(set)
        for group in groups:
            for tid in (group.chair_id, group.secretary_id, *group.expert_ids):
                campuses[tid, group.time_slot.start.date()].add(group.campus)
        diagnostics = {
            'algorithm': 'formal-rotation-1',
            'group_order': 'ascending_original_group_number',
            'placement_status': self.placement_status,
            'placement_rounds': self.placement_rounds,
            'descent_rounds': self.descent_rounds,
            'days_used': sorted({group.time_slot.start.date().isoformat() for group in groups}),
            'groups_per_slot': dict(sorted(Counter(group.time_slot.label for group in groups).items())),
            'relaxed_chairs': sum(self.chair_level.get(group.chair_id) == 1 for group in groups),
            'groups_without_external': sum(not any(self.external[tid] for tid in (group.chair_id, *group.expert_ids))
                                           for group in groups),
            'cross_campus_teacher_days': sum(len(places) > 1 for places in campuses.values()),
            'internal_appearance_distribution': {str(n): count for n, count in sorted(internal_loads.items())},
            'fairness': distribution_metrics(groups, self.students, self.teachers, mentors_attend=False),
        }
        return {'groups': [serialize_group(group) for group in groups], 'conflicts': conflicts,
                'diagnostics': diagnostics,
                'unassigned_students': [{'id': sid, 'name': self.student_map[sid].name, 'reason': reason}
                                        for sid, reason in sorted(self.reasons.items())]}
