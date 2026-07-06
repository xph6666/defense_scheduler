from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from math import ceil
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TIME_FMT = "%Y-%m-%d %H:%M"
DATE_FMT = "%Y-%m-%d"
DEFAULT_SLOT_DURATION_MINUTES = 180


@dataclass(frozen=True)
class TimeRange:
    """Closed-open time range [start, end)."""

    start: datetime
    end: datetime

    def overlaps(self, other: "TimeRange") -> bool:
        return self.start < other.end and other.start < self.end

    @property
    def label(self) -> str:
        return f"{self.start.strftime(TIME_FMT)}-{self.end.strftime('%H:%M')}"


@dataclass
class Teacher:
    id: int
    name: str
    college: Optional[str] = None
    is_external: bool = False
    title: Optional[str] = None
    available_time: List[str] = field(default_factory=list)
    campus_preference: Optional[str] = None
    forbidden_with: List[int] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Student:
    id: int
    name: str
    type: Optional[str] = None
    supervisor_id: Optional[int] = None
    campus: Optional[str] = None
    secretary_id: Optional[int] = None
    previous_group_id: Optional[Any] = None  # 上一场次（预答辩）的组标识，正式答辩沿用分组
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Room:
    id: int
    campus: Optional[str] = None
    name: Optional[str] = None
    available_time: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GroupDraft:
    group_id: str
    campus: Optional[str]
    student_ids: List[int]
    time_slot: Optional[TimeRange] = None
    room_id: Optional[int] = None
    chair_id: Optional[int] = None
    expert_ids: List[int] = field(default_factory=list)
    secretary_id: Optional[int] = None


class SchedulingError(Exception):
    """Raised when input validation fails or scheduling cannot proceed."""


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def generate_schedule(
    teachers: List[dict],
    students: List[dict],
    rooms: List[dict],
    rules: Dict[str, Any],
) -> Dict[str, List[dict]]:
    """
    Generate defense groups and return conflicts for unmet constraints.
    """
    parsed_teachers = [parse_teacher(t) for t in teachers]
    parsed_students = [parse_student(s) for s in students]
    parsed_rooms = [parse_room(r) for r in rooms]

    validate_inputs(parsed_teachers, parsed_students, parsed_rooms, rules)

    candidate_slots = build_candidate_slots(rules, parsed_rooms)
    grouped_students = build_student_groups(parsed_students, rules)

    drafts: List[GroupDraft] = []
    conflicts: List[dict] = []

    teacher_busy: Dict[int, List[TimeRange]] = {}
    room_busy: Dict[int, List[TimeRange]] = {}
    teacher_day_campus: Dict[Tuple[int, date], set] = {}

    for idx, student_batch in enumerate(grouped_students, start=1):
        campus = infer_group_campus(student_batch)
        group = GroupDraft(
            group_id=f"G{idx}",
            campus=campus,
            student_ids=[s.id for s in student_batch],
        )
        conflicts.extend(check_group_size(group.group_id, len(student_batch), rules))

        slot, room, assignment_conflicts = assign_slot_and_room(
            group=group,
            students_in_group=student_batch,
            rooms=parsed_rooms,
            candidate_slots=candidate_slots,
            room_busy=room_busy,
            rules=rules,
        )
        conflicts.extend(assignment_conflicts)

        if slot is not None:
            group.time_slot = slot
        if room is not None:
            group.room_id = room.id
            room_busy.setdefault(room.id, []).append(slot)  # type: ignore[arg-type]

        chair_id, expert_ids, secretary_id, people_conflicts = assign_teachers(
            group=group,
            students_in_group=student_batch,
            teachers=parsed_teachers,
            teacher_busy=teacher_busy,
            rules=rules,
            teacher_day_campus=teacher_day_campus,
        )
        group.chair_id = chair_id
        group.expert_ids = expert_ids
        group.secretary_id = secretary_id
        conflicts.extend(people_conflicts)

        if group.time_slot is not None:
            reserve_teacher_time(teacher_busy, group, teacher_day_campus)

        drafts.append(group)

    conflicts.extend(detect_global_conflicts(drafts, parsed_students, parsed_teachers, parsed_rooms, rules))

    return {
        "groups": [serialize_group(d) for d in drafts],
        "conflicts": deduplicate_conflicts(conflicts),
    }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_teacher(raw: Dict[str, Any]) -> Teacher:
    return Teacher(
        id=int(raw["id"]),
        name=str(raw.get("name", "")),
        college=raw.get("college"),
        is_external=bool(raw.get("is_external", False)),
        title=raw.get("title"),
        available_time=list(raw.get("available_time", []) or []),
        campus_preference=raw.get("campus_preference"),
        forbidden_with=list(raw.get("forbidden_with", []) or []),
        raw=dict(raw),
    )


def parse_student(raw: Dict[str, Any]) -> Student:
    return Student(
        id=int(raw["id"]),
        name=str(raw.get("name", "")),
        type=raw.get("type"),
        supervisor_id=raw.get("supervisor_id"),
        campus=raw.get("campus"),
        secretary_id=raw.get("secretary_id"),
        previous_group_id=raw.get("previous_group_id"),
        raw=dict(raw),
    )


def parse_room(raw: Dict[str, Any]) -> Room:
    return Room(
        id=int(raw["id"]),
        campus=raw.get("campus"),
        name=raw.get("name"),
        available_time=list(raw.get("available_time", []) or []),
        raw=dict(raw),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_inputs(
    teachers: Sequence[Teacher],
    students: Sequence[Student],
    rooms: Sequence[Room],
    rules: Dict[str, Any],
) -> None:
    if not students:
        raise SchedulingError("students cannot be empty")
    if not teachers:
        raise SchedulingError("teachers cannot be empty")
    if not rooms:
        raise SchedulingError("rooms cannot be empty")

    required_rule_fields = ["start_date", "end_date", "group_size", "expert_count"]
    missing = [key for key in required_rule_fields if key not in rules]
    if missing:
        raise SchedulingError(f"missing required rules: {', '.join(missing)}")

    try:
        start_date = datetime.strptime(rules["start_date"], DATE_FMT).date()
        end_date = datetime.strptime(rules["end_date"], DATE_FMT).date()
    except (TypeError, ValueError) as exc:
        raise SchedulingError("start_date and end_date must use YYYY-MM-DD") from exc
    if end_date < start_date:
        raise SchedulingError("end_date must be >= start_date")

    if int(rules["group_size"]) <= 0:
        raise SchedulingError("group_size must be > 0")
    if int(rules["expert_count"]) < 0:
        raise SchedulingError("expert_count must be >= 0")

    teacher_ids = {t.id for t in teachers}
    for student in students:
        if student.supervisor_id is not None and student.supervisor_id not in teacher_ids:
            raise SchedulingError(
                f"student {student.id} references missing supervisor_id={student.supervisor_id}"
            )
        if student.secretary_id is not None and student.secretary_id not in teacher_ids:
            raise SchedulingError(
                f"student {student.id} references missing secretary_id={student.secretary_id}"
            )


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------

def get_supervisor_policy(rules: Dict[str, Any]) -> str:
    """导师约束三态：same_group=导师必须与学生同组（预答辩/中期）；
    avoid=导师回避（正式答辩）；none=不限。兼容旧布尔键 avoid_supervisor。"""
    policy = rules.get("supervisor_policy")
    if policy in ("same_group", "avoid", "none"):
        return policy
    return "avoid" if rules.get("avoid_supervisor", False) else "none"


def parse_excluded_dates(rules: Dict[str, Any]) -> set:
    """解析规则中的排除日期（法定节假日等），格式非法的条目忽略。"""
    excluded = set()
    for raw in rules.get("exclude_dates") or []:
        try:
            excluded.add(datetime.strptime(str(raw).strip(), DATE_FMT).date())
        except (TypeError, ValueError):
            continue
    return excluded


def slot_date_is_allowed(day: date, rules: Dict[str, Any], excluded_dates: set) -> bool:
    if rules.get("avoid_weekend", False) and day.weekday() >= 5:
        return False
    if day in excluded_dates:
        return False
    return True


def build_candidate_slots(rules: Dict[str, Any], rooms: Sequence[Room]) -> List[TimeRange]:
    """
    Build candidate slots from room availability when possible.
    Falls back to date-range-derived default slots if room data is missing.
    """
    excluded_dates = parse_excluded_dates(rules)
    slot_map: Dict[Tuple[datetime, datetime], TimeRange] = {}

    for room in rooms:
        for raw_slot in room.available_time:
            time_range = parse_time_range(raw_slot)
            if not slot_date_is_allowed(time_range.start.date(), rules, excluded_dates):
                continue
            slot_map[(time_range.start, time_range.end)] = time_range

    if slot_map:
        return sorted(slot_map.values(), key=lambda s: (s.start, s.end))

    start = datetime.strptime(rules["start_date"], DATE_FMT).date()
    end = datetime.strptime(rules["end_date"], DATE_FMT).date()

    slots: List[TimeRange] = []
    current = start
    while current <= end:
        if not slot_date_is_allowed(current, rules, excluded_dates):
            current += timedelta(days=1)
            continue
        morning = default_slot(current, 9, 0)
        afternoon = default_slot(current, 14, 0)
        slots.extend([morning, afternoon])
        current += timedelta(days=1)
    return slots


def default_slot(day: date, hour: int, minute: int) -> TimeRange:
    start = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
    end = start + timedelta(minutes=DEFAULT_SLOT_DURATION_MINUTES)
    return TimeRange(start=start, end=end)


def build_student_groups(students: Sequence[Student], rules: Dict[str, Any]) -> List[List[Student]]:
    """按规则选择分组策略：

    - grouping=secretary：按既定秘书聚类（正式答辩沿用预答辩的"秘书+学生组不变"）；
    - grouping=supervisor 或导师同组模式：按导师聚类装箱，同导师学生尽量同组；
    - 默认：按校区排序后以目标人数切块，尾组不足下限时并入前一组（不突破上限）。

    软权重：balance_student_count 低于 50 时装箱允许填到人数上限（组数更少）；
    prefer_academic_master_first 高于 50 时学硕占比高的组优先获得靠前的时间槽。
    """
    target_size = int(rules["group_size"])
    min_size = int(rules.get("group_min", 0) or 0)
    max_size = int(rules.get("group_max", 0) or 0)
    grouping = str(rules.get("grouping") or "")
    soft = rules.get("soft_weights") or {}
    balance_weight = int(soft.get("balance_student_count", 50) or 0)
    fill_limit = target_size if balance_weight >= 50 else (max_size or target_size)

    if grouping == "secretary" and any(
        s.secretary_id is not None or s.previous_group_id is not None for s in students
    ):
        groups = _group_by_secretary(students, target_size, min_size, max_size, fill_limit)
    elif grouping == "supervisor" or (not grouping and get_supervisor_policy(rules) == "same_group"):
        groups = _pack_student_clusters(
            students, cluster_key=lambda s: s.supervisor_id,
            target_size=target_size, min_size=min_size, max_size=max_size,
            fill_limit=fill_limit,
        )
    else:
        ordered = sorted(students, key=lambda s: ((s.campus or ""), s.id))

        groups = []
        for i in range(0, len(ordered), target_size):
            groups.append(list(ordered[i : i + target_size]))

        if (
            min_size > 0
            and len(groups) >= 2
            and len(groups[-1]) < min_size
            and (max_size <= 0 or len(groups[-2]) + len(groups[-1]) <= max_size)
        ):
            groups[-2].extend(groups.pop())

    master_weight = int(soft.get("prefer_academic_master_first", 0) or 0)
    if master_weight > 50:
        # 学硕占比高的组排前面，从而优先分配靠前的时间槽（稳定排序保持组内原序）
        groups.sort(key=lambda batch: -sum(1 for s in batch if (s.type or "") == "学硕"))
    return groups


def _group_by_secretary(
    students: Sequence[Student],
    target_size: int,
    min_size: int,
    max_size: int,
    fill_limit: int,
) -> List[List[Student]]:
    """跨场次沿用分组：优先按上一场次的组标识聚类（组原样保留）；
    没有组标识的学生按绑定秘书聚类（同一秘书可能带多个组，仅作兜底）；
    两者都没有的学生按导师聚类补组。"""
    bound: Dict[Any, List[Student]] = {}
    unbound: List[Student] = []
    for student in sorted(students, key=lambda s: s.id):
        if student.previous_group_id is not None:
            bound.setdefault(('prev', str(student.previous_group_id)), []).append(student)
        elif student.secretary_id is not None:
            bound.setdefault(('sec', str(student.secretary_id)), []).append(student)
        else:
            unbound.append(student)

    groups = [batch for _, batch in sorted(bound.items())]
    if unbound:
        groups.extend(_pack_student_clusters(
            unbound, cluster_key=lambda s: s.supervisor_id,
            target_size=target_size, min_size=min_size, max_size=max_size,
            fill_limit=fill_limit,
        ))
    return groups


def _pack_student_clusters(
    students: Sequence[Student],
    cluster_key,
    target_size: int,
    min_size: int,
    max_size: int,
    fill_limit: int = 0,
) -> List[List[Student]]:
    """按 cluster_key（如导师）聚簇后做装箱：大簇优先、同校区才可同箱。

    fill_limit 为装箱合并阈值（人数均衡权重高时取目标人数，低时取上限）。
    """
    capacity = max_size or target_size
    fill_limit = fill_limit or target_size
    clusters: Dict[Any, List[Student]] = {}
    for student in sorted(students, key=lambda s: s.id):
        key = ((student.campus or ""), cluster_key(student))
        clusters.setdefault(key, []).append(student)

    ordered_clusters = sorted(
        clusters.values(),
        key=lambda cluster: (-len(cluster), (cluster[0].campus or ""), cluster[0].id),
    )

    bins: List[List[Student]] = []
    for cluster in ordered_clusters:
        # 单簇超过容量（同一导师学生过多）时按目标人数拆开
        while len(cluster) > capacity:
            bins.append(list(cluster[:target_size]))
            cluster = cluster[target_size:]
        placed = False
        for existing in bins:
            if (
                len(existing) + len(cluster) <= fill_limit
                and (existing[0].campus or "") == (cluster[0].campus or "")
            ):
                existing.extend(cluster)
                placed = True
                break
        if not placed:
            bins.append(list(cluster))

    # 不足下限的箱子尝试并入同校区且不超上限的箱子
    merged: List[List[Student]] = []
    for group in sorted(bins, key=lambda g: -len(g)):
        if min_size and len(group) < min_size:
            host = next(
                (
                    existing for existing in merged
                    if (existing[0].campus or "") == (group[0].campus or "")
                    and (capacity <= 0 or len(existing) + len(group) <= capacity)
                ),
                None,
            )
            if host is not None:
                host.extend(group)
                continue
        merged.append(group)
    return merged


def check_group_size(group_id: str, size: int, rules: Dict[str, Any]) -> List[dict]:
    """组人数超出配置区间时生成提示（并组无法解决时兜底告知用户）。"""
    min_size = int(rules.get("group_min", 0) or 0)
    max_size = int(rules.get("group_max", 0) or 0)
    if min_size and size < min_size:
        return [
            make_conflict(
                conflict_type="group_size_out_of_range",
                description=f"{group_id} has {size} students, below the configured minimum of {min_size}",
                related_ids=[group_id],
            )
        ]
    if max_size and size > max_size:
        return [
            make_conflict(
                conflict_type="group_size_out_of_range",
                description=f"{group_id} has {size} students, above the configured maximum of {max_size}",
                related_ids=[group_id],
            )
        ]
    return []


def infer_group_campus(students: Sequence[Student]) -> Optional[str]:
    campuses = {s.campus for s in students if s.campus}
    if len(campuses) == 1:
        return next(iter(campuses))
    return None


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

def assign_slot_and_room(
    group: GroupDraft,
    students_in_group: Sequence[Student],
    rooms: Sequence[Room],
    candidate_slots: Sequence[TimeRange],
    room_busy: Dict[int, List[TimeRange]],
    rules: Dict[str, Any],
) -> Tuple[Optional[TimeRange], Optional[Room], List[dict]]:
    conflicts: List[dict] = []

    preferred_rooms = [r for r in rooms if group.campus is None or r.campus == group.campus]
    fallback_rooms = [r for r in rooms if r not in preferred_rooms]

    for room in preferred_rooms + fallback_rooms:
        room_slots = parse_room_available_slots(room, rules, candidate_slots)
        for slot in room_slots:
            if not is_resource_available(room_busy.get(room.id, []), slot):
                continue
            return slot, room, conflicts

    conflicts.append(
        make_conflict(
            conflict_type="room_or_time_unavailable",
            description=f"No available room/time slot could be assigned for {group.group_id}",
            related_ids=[group.group_id] + [s.id for s in students_in_group],
        )
    )
    return None, None, conflicts


def assign_teachers(
    group: GroupDraft,
    students_in_group: Sequence[Student],
    teachers: Sequence[Teacher],
    teacher_busy: Dict[int, List[TimeRange]],
    rules: Dict[str, Any],
    teacher_day_campus: Optional[Dict[Tuple[int, date], set]] = None,
) -> Tuple[Optional[int], List[int], Optional[int], List[dict]]:
    conflicts: List[dict] = []
    slot = group.time_slot
    needed_experts = int(rules.get("expert_count", 0))
    need_chair = bool(rules.get("need_chair", False))
    policy = get_supervisor_policy(rules)
    soft = rules.get("soft_weights") or {}

    supervisor_ids = {s.supervisor_id for s in students_in_group if s.supervisor_id is not None}
    # 学生既定秘书（预答辩确定，正式答辩沿用）：统计组内绑定情况
    desired_secretary_counts: Dict[int, int] = {}
    for student in students_in_group:
        if student.secretary_id is not None:
            desired_secretary_counts[student.secretary_id] = (
                desired_secretary_counts.get(student.secretary_id, 0) + 1
            )

    teacher_name_map = {t.id: t.name for t in teachers}
    available_teachers = [
        t for t in teachers
        if teacher_is_eligible(
            teacher=t,
            slot=slot,
            busy_slots=teacher_busy.get(t.id, []),
            supervisor_ids=supervisor_ids,
            rules=rules,
        )
    ]
    if rules.get("prefer_senior", False) or int(soft.get("prefer_senior_teacher", 0) or 0) > 50:
        # 稳定排序：职称高者优先被选为主席/专家，同职称保持原有顺序
        available_teachers.sort(key=lambda t: title_rank(t.title), reverse=True)

    # 软权重：减少跨校区——当天已在其他校区有安排的教师排到候选队尾
    if (
        int(soft.get("avoid_cross_campus", 0) or 0) > 0
        and slot is not None
        and group.campus
        and teacher_day_campus
    ):
        def cross_campus_penalty(teacher: Teacher) -> int:
            campuses = teacher_day_campus.get((teacher.id, slot.start.date()))
            if campuses and group.campus not in campuses:
                return 1
            return 0

        available_teachers.sort(key=cross_campus_penalty)

    expert_ids: List[int] = []
    # 导师同组模式：组内学生的导师优先进入专家席（预答辩/中期的硬约束）
    if policy == "same_group":
        available_ids = {t.id for t in available_teachers}
        for supervisor_id in sorted(supervisor_ids):
            if supervisor_id in available_ids:
                if supervisor_id not in expert_ids:
                    expert_ids.append(supervisor_id)
            else:
                supervisor_name = teacher_name_map.get(supervisor_id, str(supervisor_id))
                conflicts.append(
                    make_conflict(
                        conflict_type="supervisor_missing",
                        description=(
                            f"Supervisor {supervisor_name} cannot join {group.group_id} "
                            f"although supervisors must sit in their students' group"
                        ),
                        related_ids=[group.group_id, supervisor_id],
                    )
                )

    chair_id: Optional[int] = None
    if need_chair:
        chair = None
        if policy == "same_group":
            # 优先让组内导师专家中符合职称要求者担任组长/主席（真实安排的常见做法）
            chair = next(
                (t for t in available_teachers if t.id in expert_ids and meets_chair_requirement(t, rules)),
                None,
            )
            if chair is not None:
                expert_ids.remove(chair.id)
        if chair is None:
            chair = next(
                (t for t in available_teachers if t.id not in expert_ids and meets_chair_requirement(t, rules)),
                None,
            )
        if chair is not None:
            chair_id = chair.id
            available_teachers = [t for t in available_teachers if t.id != chair.id]
        else:
            conflicts.append(
                make_conflict(
                    conflict_type="chair_unavailable",
                    description=f"No eligible chair found for {group.group_id}",
                    related_ids=[group.group_id],
                )
            )

    for teacher in available_teachers:
        if len(expert_ids) >= needed_experts:
            break
        if teacher.id in expert_ids:
            continue
        if policy == "avoid" and teacher.id in supervisor_ids:
            continue
        if conflicts_with_selected_teachers(teacher.id, expert_ids + ([chair_id] if chair_id else []), teachers):
            continue
        expert_ids.append(teacher.id)

    if len(expert_ids) < needed_experts:
        shortage = make_conflict(
            conflict_type="insufficient_experts",
            description=(
                f"{group.group_id} requires {needed_experts} experts but only {len(expert_ids)} "
                f"eligible experts were assigned"
            ),
            related_ids=[group.group_id] + expert_ids,
        )
        # 附带数量信息，便于调用方区分"低于理想值"与"低于可接受下限"
        shortage["required"] = needed_experts
        shortage["assigned"] = len(expert_ids)
        shortage["min_required"] = int(rules.get("expert_min", 0) or 0)
        conflicts.append(shortage)

    secretary_min_rank = title_rank(rules.get("secretary_title")) if rules.get("secretary_title") else -1
    secretary_id: Optional[int] = None

    # 跨场次连续性：优先沿用学生既定的秘书（不再受职称门槛限制，历史事实优先）
    if desired_secretary_counts:
        preferred_id = max(sorted(desired_secretary_counts), key=lambda k: desired_secretary_counts[k])
        preferred = next((t for t in available_teachers if t.id == preferred_id), None)
        if (
            preferred is not None
            and preferred.id not in expert_ids
            and preferred.id != chair_id
            and preferred.id not in supervisor_ids
        ):
            secretary_id = preferred.id
        else:
            preferred_name = teacher_name_map.get(preferred_id, str(preferred_id))
            conflicts.append(
                make_conflict(
                    conflict_type="secretary_continuity_broken",
                    description=(
                        f"Students in {group.group_id} previously followed secretary {preferred_name}, "
                        f"but the secretary is unavailable for this group"
                    ),
                    related_ids=[group.group_id, preferred_id],
                )
            )

    if secretary_id is None:
        # 秘书不能是组内任何学生的导师（“秘书的学生不能在秘书所在组”）
        secretary_id = next(
            (
                t.id
                for t in available_teachers
                if t.id not in expert_ids
                and t.id != chair_id
                and t.id not in supervisor_ids
                and (secretary_min_rank < 0 or title_rank(t.title) >= secretary_min_rank)
            ),
            None,
        )
    if secretary_id is None:
        conflicts.append(
            make_conflict(
                conflict_type="secretary_unavailable",
                description=f"No eligible secretary found for {group.group_id}",
                related_ids=[group.group_id],
            )
        )

    return chair_id, expert_ids, secretary_id, conflicts


def teacher_is_eligible(
    teacher: Teacher,
    slot: Optional[TimeRange],
    busy_slots: Sequence[TimeRange],
    supervisor_ids: Iterable[Optional[int]],
    rules: Dict[str, Any],
) -> bool:
    if slot is None:
        return True
    if teacher.id in {sid for sid in supervisor_ids if sid is not None} and get_supervisor_policy(rules) == "avoid":
        return False
    if not is_resource_available(busy_slots, slot):
        return False
    unavailable = [parse_time_range(x) for x in teacher.available_time]
    if not is_resource_available(unavailable, slot):
        return False
    return True


# 职称等级表：等级越高越资深。键统一小写，中英文写法都收录。
TITLE_RANKS = {
    "教授": 3,
    "professor": 3,
    "副教授": 2,
    "associate professor": 2,
    "讲师": 1,
    "lecturer": 1,
    "助教": 0,
    "assistant": 0,
    "teaching assistant": 0,
}


def title_rank(title: Optional[str]) -> int:
    return TITLE_RANKS.get((title or "").strip().lower(), -1)


def meets_chair_requirement(teacher: Teacher, rules: Dict[str, Any]) -> bool:
    """按职称等级判断能否担任主席。

    注意不能用子串匹配："教授" in "副教授" 为 True，会把副教授错配成教授。
    要求的职称不在等级表里时退回精确匹配。
    """
    required = (rules.get("chair_title") or "").strip()
    if not required:
        return True
    required_rank = title_rank(required)
    if required_rank < 0:
        return (teacher.title or "").strip().lower() == required.lower()
    return title_rank(teacher.title) >= required_rank


def conflicts_with_selected_teachers(
    candidate_teacher_id: int,
    selected_teacher_ids: Sequence[Optional[int]],
    teachers: Sequence[Teacher],
) -> bool:
    teacher_map = {t.id: t for t in teachers}
    candidate = teacher_map.get(candidate_teacher_id)
    if candidate is None:
        return True

    selected = {tid for tid in selected_teacher_ids if tid is not None}
    for tid in selected:
        other = teacher_map.get(tid)
        if other is None:
            continue
        if tid in candidate.forbidden_with or candidate_teacher_id in other.forbidden_with:
            return True
    return False


def reserve_teacher_time(
    teacher_busy: Dict[int, List[TimeRange]],
    group: GroupDraft,
    teacher_day_campus: Optional[Dict[Tuple[int, date], set]] = None,
) -> None:
    if group.time_slot is None:
        return
    role_ids = [group.chair_id, group.secretary_id, *group.expert_ids]
    for teacher_id in [tid for tid in role_ids if tid is not None]:
        teacher_busy.setdefault(int(teacher_id), []).append(group.time_slot)
        if teacher_day_campus is not None and group.campus:
            key = (int(teacher_id), group.time_slot.start.date())
            teacher_day_campus.setdefault(key, set()).add(group.campus)


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def detect_global_conflicts(
    drafts: Sequence[GroupDraft],
    students: Sequence[Student],
    teachers: Sequence[Teacher],
    rooms: Sequence[Room],
    rules: Dict[str, Any],
) -> List[dict]:
    conflicts: List[dict] = []
    teacher_map = {t.id: t for t in teachers}
    student_map = {s.id: s for s in students}
    room_map = {r.id: r for r in rooms}

    # Duplicate teacher/room at same time.
    for i, left in enumerate(drafts):
        if left.time_slot is None:
            continue
        left_people = {left.chair_id, left.secretary_id, *left.expert_ids}
        for right in drafts[i + 1 :]:
            if right.time_slot is None:
                continue
            if not left.time_slot.overlaps(right.time_slot):
                continue

            right_people = {right.chair_id, right.secretary_id, *right.expert_ids}
            shared_people = {pid for pid in left_people & right_people if pid is not None}
            if shared_people:
                conflicts.append(
                    make_conflict(
                        conflict_type="time_conflict",
                        description=(
                            f"Teachers {sorted(shared_people)} appear in both {left.group_id} and {right.group_id} "
                            f"during overlapping time slots"
                        ),
                        related_ids=[left.group_id, right.group_id, *sorted(shared_people)],
                    )
                )

            if left.room_id is not None and left.room_id == right.room_id:
                conflicts.append(
                    make_conflict(
                        conflict_type="room_conflict",
                        description=(
                            f"Room {left.room_id} is assigned to both {left.group_id} and {right.group_id} "
                            f"during overlapping time slots"
                        ),
                        related_ids=[left.group_id, right.group_id, left.room_id],
                    )
                )

    # Supervisor policy check: avoidance (formal) or must-sit-in-group (pre/mid).
    policy = get_supervisor_policy(rules)
    for draft in drafts:
        assigned_teachers = {draft.chair_id, draft.secretary_id, *draft.expert_ids}
        for sid in draft.student_ids:
            student = student_map.get(sid)
            if student is None or student.supervisor_id is None:
                continue
            supervisor_name = (
                teacher_map[student.supervisor_id].name
                if student.supervisor_id in teacher_map
                else str(student.supervisor_id)
            )
            if policy == "avoid" and student.supervisor_id in assigned_teachers:
                conflicts.append(
                    make_conflict(
                        conflict_type="supervisor_avoidance",
                        description=(
                            f"Supervisor {supervisor_name} is assigned to {draft.group_id} while supervisor avoidance is enabled"
                        ),
                        related_ids=[draft.group_id, sid, student.supervisor_id],
                    )
                )
            if policy == "same_group" and student.supervisor_id not in assigned_teachers:
                conflicts.append(
                    make_conflict(
                        conflict_type="supervisor_missing",
                        description=(
                            f"Supervisor {supervisor_name} cannot join {draft.group_id} "
                            f"although supervisors must sit in their students' group"
                        ),
                        related_ids=[draft.group_id, student.supervisor_id],
                    )
                )

    # Secretary constraints: continuity with the pre-assigned secretary and
    # "a secretary must not supervise students in their own group".
    for draft in drafts:
        student_supervisors = {
            student_map[sid].supervisor_id
            for sid in draft.student_ids
            if student_map.get(sid) and student_map[sid].supervisor_id is not None
        }
        if draft.secretary_id is not None and draft.secretary_id in student_supervisors:
            secretary_name = (
                teacher_map[draft.secretary_id].name
                if draft.secretary_id in teacher_map
                else str(draft.secretary_id)
            )
            conflicts.append(
                make_conflict(
                    conflict_type="secretary_is_supervisor",
                    description=(
                        f"Secretary {secretary_name} of {draft.group_id} supervises students in the same group"
                    ),
                    related_ids=[draft.group_id, draft.secretary_id],
                )
            )

        desired_counts: Dict[int, int] = {}
        for sid in draft.student_ids:
            student = student_map.get(sid)
            if student is not None and student.secretary_id is not None:
                desired_counts[student.secretary_id] = desired_counts.get(student.secretary_id, 0) + 1
        if desired_counts and draft.secretary_id is not None:
            preferred_id = max(sorted(desired_counts), key=lambda k: desired_counts[k])
            if preferred_id != draft.secretary_id:
                preferred_name = (
                    teacher_map[preferred_id].name if preferred_id in teacher_map else str(preferred_id)
                )
                conflicts.append(
                    make_conflict(
                        conflict_type="secretary_continuity_broken",
                        description=(
                            f"Students in {draft.group_id} previously followed secretary {preferred_name}, "
                            f"but the secretary is unavailable for this group"
                        ),
                        related_ids=[draft.group_id, preferred_id],
                    )
                )

    # Room-campus mismatch check.
    for draft in drafts:
        if draft.room_id is None or draft.campus is None:
            continue
        room = room_map.get(draft.room_id)
        if room is not None and room.campus and room.campus != draft.campus:
            conflicts.append(
                make_conflict(
                    conflict_type="campus_mismatch",
                    description=(
                        f"{draft.group_id} is inferred for campus {draft.campus} but assigned room {room.id} on campus {room.campus}"
                    ),
                    related_ids=[draft.group_id, room.id],
                )
            )

    return conflicts


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def serialize_group(group: GroupDraft) -> dict:
    return {
        "group_id": group.group_id,
        "time": group.time_slot.label if group.time_slot else None,
        "room_id": group.room_id,
        "campus": group.campus,
        "chair_id": group.chair_id,
        "expert_ids": group.expert_ids,
        "secretary_id": group.secretary_id,
        "student_ids": group.student_ids,
    }


def make_conflict(conflict_type: str, description: str, related_ids: List[Any]) -> dict:
    return {
        "type": conflict_type,
        "description": description,
        "related_ids": related_ids,
    }


def deduplicate_conflicts(conflicts: Sequence[dict]) -> List[dict]:
    seen = set()
    result = []
    for item in conflicts:
        key = (item.get("type"), item.get("description"), tuple(item.get("related_ids", [])))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def parse_room_available_slots(
    room: Room,
    rules: Dict[str, Any],
    candidate_slots: Sequence[TimeRange],
) -> List[TimeRange]:
    excluded_dates = parse_excluded_dates(rules)
    start = datetime.strptime(rules["start_date"], DATE_FMT)
    end = datetime.strptime(rules["end_date"], DATE_FMT) + timedelta(days=1)

    if room.available_time:
        # 教室可用时段必须落在排期日期范围内（真实借用记录常含往年/范围外日期）
        return [
            time_range
            for time_range in (parse_time_range(raw) for raw in room.available_time)
            if start <= time_range.start < end
            and slot_date_is_allowed(time_range.start.date(), rules, excluded_dates)
        ]

    # Fallback to all candidate slots if room availability is not specified.
    return [slot for slot in candidate_slots if start <= slot.start < end]


def parse_time_range(raw: str) -> TimeRange:
    """
    Parse either of these formats:
    - 2025-05-10 09:00-12:00
    - 2025-05-10 09:00-2025-05-10 12:00
    """
    raw = raw.strip()
    try:
        date_part, time_part = raw.split(" ", 1)
    except ValueError as exc:
        raise SchedulingError(f"invalid time range: {raw}") from exc

    if time_part.count("-") == 1 and ":" in time_part:
        try:
            start_clock, end_clock = time_part.split("-")
            start = datetime.strptime(f"{date_part} {start_clock}", TIME_FMT)
            end = datetime.strptime(f"{date_part} {end_clock}", TIME_FMT)
        except ValueError as exc:
            raise SchedulingError(f"invalid time range: {raw}") from exc
        if end <= start:
            raise SchedulingError(f"invalid time range (end <= start): {raw}")
        return TimeRange(start=start, end=end)

    try:
        left, right = raw.split("-", 1)
        start = datetime.strptime(left.strip(), TIME_FMT)
        end = datetime.strptime(right.strip(), TIME_FMT)
    except ValueError as exc:
        raise SchedulingError(f"invalid time range: {raw}") from exc

    if end <= start:
        raise SchedulingError(f"invalid time range (end <= start): {raw}")
    return TimeRange(start=start, end=end)


def is_resource_available(existing_ranges: Sequence[TimeRange], target: TimeRange) -> bool:
    return all(not current.overlaps(target) for current in existing_ranges)


# ---------------------------------------------------------------------------
# Example local run (remove if not needed in production)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_data = {
        "teachers": [
            {
                "id": 1,
                "name": "Prof. Zhang",
                "title": "professor",
                "available_time": ["2025-05-10 14:00-17:00"],
                "forbidden_with": [2],
            },
            {
                "id": 2,
                "name": "Prof. Wang",
                "title": "professor",
                "available_time": [],
            },
            {
                "id": 3,
                "name": "Assoc. Prof. Li",
                "title": "associate professor",
                "available_time": [],
            },
            {
                "id": 4,
                "name": "Lecturer Zhao",
                "title": "lecturer",
                "available_time": [],
            },
        ],
        "students": [
            {"id": 101, "name": "A", "supervisor_id": 1, "campus": "Innovation Harbor"},
            {"id": 102, "name": "B", "supervisor_id": 1, "campus": "Innovation Harbor"},
            {"id": 103, "name": "C", "supervisor_id": 2, "campus": "Innovation Harbor"},
        ],
        "rooms": [
            {
                "id": 201,
                "campus": "Innovation Harbor",
                "name": "A101",
                "available_time": ["2025-05-10 09:00-12:00"],
            }
        ],
        "rules": {
            "defense_type": "pre",
            "start_date": "2025-05-10",
            "end_date": "2025-05-10",
            "avoid_weekend": False,
            "avoid_supervisor": False,
            "group_size": 3,
            "expert_count": 2,
            "need_chair": True,
            "chair_title": "professor",
        },
    }

    from pprint import pprint

    pprint(generate_schedule(**sample_data))
