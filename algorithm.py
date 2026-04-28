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

    This Week 1-2 skeleton focuses on:
    1. Input normalization / validation
    2. Candidate slot construction
    3. Student grouping
    4. Greedy room + teacher assignment hooks
    5. Deterministic conflict reporting

    Notes for integration:
    - The current interface document uses `teachers.available_time` to mean
      *unavailable* time, while `rooms.available_time` means *available* time.
      This file preserves that assumption.
    - When a full feasible solution is not found, the function returns partial
      groups together with conflict records instead of raising, unless inputs
      are invalid.
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

    for idx, student_batch in enumerate(grouped_students, start=1):
        campus = infer_group_campus(student_batch)
        group = GroupDraft(
            group_id=f"G{idx}",
            campus=campus,
            student_ids=[s.id for s in student_batch],
        )

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
        )
        group.chair_id = chair_id
        group.expert_ids = expert_ids
        group.secretary_id = secretary_id
        conflicts.extend(people_conflicts)

        if group.time_slot is not None:
            reserve_teacher_time(teacher_busy, group)

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

def build_candidate_slots(rules: Dict[str, Any], rooms: Sequence[Room]) -> List[TimeRange]:
    """
    Build candidate slots from room availability when possible.
    Falls back to date-range-derived default slots if room data is missing.
    """
    slot_map: Dict[Tuple[datetime, datetime], TimeRange] = {}

    for room in rooms:
        for raw_slot in room.available_time:
            time_range = parse_time_range(raw_slot)
            slot_map[(time_range.start, time_range.end)] = time_range

    if slot_map:
        return sorted(slot_map.values(), key=lambda s: (s.start, s.end))

    start = datetime.strptime(rules["start_date"], DATE_FMT).date()
    end = datetime.strptime(rules["end_date"], DATE_FMT).date()

    slots: List[TimeRange] = []
    current = start
    while current <= end:
        if rules.get("avoid_weekend", False) and current.weekday() >= 5:
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
    """Naive Week 1 grouping: sort by campus then chunk by group_size."""
    target_size = int(rules["group_size"])
    ordered = sorted(students, key=lambda s: ((s.campus or ""), s.id))

    groups: List[List[Student]] = []
    for i in range(0, len(ordered), target_size):
        groups.append(list(ordered[i : i + target_size]))
    return groups


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
) -> Tuple[Optional[int], List[int], Optional[int], List[dict]]:
    conflicts: List[dict] = []
    slot = group.time_slot
    needed_experts = int(rules.get("expert_count", 0))
    need_chair = bool(rules.get("need_chair", False))

    supervisor_ids = {s.supervisor_id for s in students_in_group if s.supervisor_id is not None}
    forbidden_secretary_ids = {s.secretary_id for s in students_in_group if s.secretary_id is not None}

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

    chair_id: Optional[int] = None
    if need_chair:
        chair = next((t for t in available_teachers if meets_chair_requirement(t, rules)), None)
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

    expert_ids: List[int] = []
    for teacher in available_teachers:
        if len(expert_ids) >= needed_experts:
            break
        if teacher.id in supervisor_ids:
            continue
        if conflicts_with_selected_teachers(teacher.id, expert_ids + ([chair_id] if chair_id else []), teachers):
            continue
        expert_ids.append(teacher.id)

    if len(expert_ids) < needed_experts:
        conflicts.append(
            make_conflict(
                conflict_type="insufficient_experts",
                description=(
                    f"{group.group_id} requires {needed_experts} experts but only {len(expert_ids)} "
                    f"eligible experts were assigned"
                ),
                related_ids=[group.group_id] + expert_ids,
            )
        )

    secretary_id = next(
        (
            t.id
            for t in available_teachers
            if t.id not in expert_ids
            and t.id != chair_id
            and t.id not in supervisor_ids
            and t.id not in forbidden_secretary_ids
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
    if teacher.id in {sid for sid in supervisor_ids if sid is not None} and rules.get("avoid_supervisor", False):
        return False
    if not is_resource_available(busy_slots, slot):
        return False
    unavailable = [parse_time_range(x) for x in teacher.available_time]
    if not is_resource_available(unavailable, slot):
        return False
    return True


def meets_chair_requirement(teacher: Teacher, rules: Dict[str, Any]) -> bool:
    required = (rules.get("chair_title") or "").lower()
    if not required:
        return True
    title = (teacher.title or "").lower()
    return required in title


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


def reserve_teacher_time(teacher_busy: Dict[int, List[TimeRange]], group: GroupDraft) -> None:
    if group.time_slot is None:
        return
    role_ids = [group.chair_id, group.secretary_id, *group.expert_ids]
    for teacher_id in [tid for tid in role_ids if tid is not None]:
        teacher_busy.setdefault(int(teacher_id), []).append(group.time_slot)


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

    # Supervisor avoidance check.
    for draft in drafts:
        if not rules.get("avoid_supervisor", False):
            continue
        assigned_teachers = {draft.chair_id, draft.secretary_id, *draft.expert_ids}
        for sid in draft.student_ids:
            student = student_map.get(sid)
            if student is None or student.supervisor_id is None:
                continue
            if student.supervisor_id in assigned_teachers:
                teacher_name = teacher_map.get(student.supervisor_id).name if student.supervisor_id in teacher_map else str(student.supervisor_id)
                conflicts.append(
                    make_conflict(
                        conflict_type="supervisor_avoidance",
                        description=(
                            f"Supervisor {teacher_name} is assigned to {draft.group_id} while supervisor avoidance is enabled"
                        ),
                        related_ids=[draft.group_id, sid, student.supervisor_id],
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
    if room.available_time:
        return [parse_time_range(raw) for raw in room.available_time]

    # Fallback to all candidate slots if room availability is not specified.
    start = datetime.strptime(rules["start_date"], DATE_FMT)
    end = datetime.strptime(rules["end_date"], DATE_FMT) + timedelta(days=1)
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
        start_clock, end_clock = time_part.split("-")
        start = datetime.strptime(f"{date_part} {start_clock}", TIME_FMT)
        end = datetime.strptime(f"{date_part} {end_clock}", TIME_FMT)
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
