"""Pure committee rules shared by generation and saved-result validation.

The catalog uses the frontend RuleConfig names; this module also accepts the
algorithm's snake_case rules. Legacy rules count ordinary experts separately.
V2 explicitly declares that the chair is included in the expert headcount.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any


_CATALOG_PATH = Path(__file__).resolve().parent.parent / "shared" / "defense-policy.json"
with _CATALOG_PATH.open(encoding="utf-8") as _catalog_file:
    _CATALOG = json.load(_catalog_file)

_DEFENSE_TYPES = {
    "pre": "pre", "预答辩": "pre",
    "formal": "formal", "正式答辩": "formal",
    "mid": "mid", "中期答辩": "mid",
}
_ROLE_ALIASES = {
    "组长": "chair", "leader": "chair", "主席": "chair",
    "chairman": "chair", "chair": "chair",
    "专家": "expert", "普通专家": "expert", "组员": "expert",
    "expert": "expert", "member": "expert",
    "秘书": "secretary", "secretary": "secretary",
    "导师": "supervisor", "supervisor": "supervisor",
}
_TITLE_RANKS = {
    "教授": 3, "正高": 3, "正高级": 3, "professor": 3,
    "副教授": 2, "副高": 2, "副高级": 2, "associate professor": 2,
    "讲师": 1, "lecturer": 1,
    "助教": 0, "assistant": 0, "teaching assistant": 0,
}
_MISSING = object()


def scenario_policy(defense_type: str) -> dict[str, Any]:
    """Return an independent copy of a Chinese- or code-named scenario."""
    key = _DEFENSE_TYPES.get(str(defense_type).strip().lower())
    if key is None:
        raise ValueError(f"不支持的答辩类型：{defense_type}")
    return deepcopy(_CATALOG["scenarios"][key])


def _value(source: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(source, Mapping):
            if name in source:
                return source[name]
        elif hasattr(source, name):
            return getattr(source, name)
    return default


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off", "否", "停用")
    return bool(value)


def _teacher_raw(teacher: Any) -> dict[str, Any]:
    if isinstance(teacher, Mapping):
        return dict(teacher)
    raw = dict(getattr(teacher, "raw", {}) or {})
    aliases = {
        "is_active": ("isActive", "active"),
        "is_external": ("isExternal",),
        "member_eligible": ("memberEligible",),
        "is_software_teacher": ("isSoftwareTeacher",),
    }
    for field in ("id", "name", "title", "college", "roles", "is_active",
                  "is_external", "member_eligible", "is_software_teacher"):
        if (field not in raw and not any(alias in raw for alias in aliases.get(field, ()))
                and hasattr(teacher, field)):
            raw[field] = getattr(teacher, field)
    return raw


def _is_active(raw: Mapping[str, Any]) -> bool:
    value = _value(raw, "is_active", "isActive", "active", default=_MISSING)
    return value is _MISSING or value is None or _boolean(value)


def _member_eligible(raw: Mapping[str, Any]) -> bool:
    value = _value(raw, "member_eligible", "memberEligible", default=_MISSING)
    return value is _MISSING or value is None or _boolean(value)


def _allowed_roles(raw: Mapping[str, Any]) -> set[str] | None:
    roles = raw.get("roles")
    if isinstance(roles, str):
        roles = [role for role in re.split(r"[,，;；/、\s]+", roles) if role]
    if not roles:
        return None
    return {_ROLE_ALIASES.get(str(role).strip().lower(), str(role).strip().lower())
            for role in roles}


def teacher_can_role(raw: Any, role: str) -> bool:
    """Check active state and declared role eligibility without changing input.

    Empty role lists retain the legacy unrestricted behavior. A teacher marked
    unsuitable as a committee member can still chair a group when qualified.
    """
    raw = _teacher_raw(raw)
    role = _ROLE_ALIASES.get(str(role).strip().lower(), str(role).strip().lower())
    if not _is_active(raw) or (role == "expert" and not _member_eligible(raw)):
        return False
    roles = _allowed_roles(raw)
    return roles is None or role in roles


def is_software_teacher(raw: Any) -> bool:
    """Recognize the software-college affiliation or an additional manual flag.

    The flag defaults to false on existing teacher records and adds eligibility;
    it does not cancel a software-college teacher's existing affiliation.
    """
    raw = _teacher_raw(raw)
    explicit = _value(raw, "is_software_teacher", "isSoftwareTeacher", default=False)
    return (_boolean(explicit)
            or (not _boolean(_value(raw, "is_external", "isExternal", default=False))
                and "软件" in str(raw.get("college") or "")))


def _includes_chair(rules: Mapping[str, Any]) -> bool:
    expert = rules.get("expertCount") or {}
    value = _value(rules, "expert_count_includes_chair", "expertCountIncludesChair",
                   default=_value(expert, "includesChair", default=False))
    return _boolean(value)


def _number(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    return int(value)


def committee_member_target(rules: Mapping[str, Any]) -> int:
    """Convert configured expert total into the ordinary-member target.

    A required chair reserves one seat only when the rules explicitly count the
    chair in that total. Legacy expert_count continues to mean ordinary members.
    """
    expert = rules.get("expertCount") or {}
    target = _number(_value(rules, "expert_count", default=expert.get("target", 0)))
    need_chair = _boolean(_value(rules, "need_chair", "needChair", default=False))
    return max(0, target - int(_includes_chair(rules) and need_chair))


def _normal_id(value: Any) -> Any:
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


def _teacher_map(teachers: Any) -> dict[Any, dict[str, Any]]:
    if isinstance(teachers, Mapping):
        return {_normal_id(key): _teacher_raw(teacher) for key, teacher in teachers.items()}
    return {_normal_id(_value(teacher, "id")): _teacher_raw(teacher) for teacher in teachers}


def _meets_title(title: Any, required: Any) -> bool:
    required = str(required or "").strip().lower()
    if not required:
        return True
    title = str(title or "").strip().lower()
    rank = _TITLE_RANKS.get(required)
    return title == required if rank is None else _TITLE_RANKS.get(title, -1) >= rank


def committee_violations(draft: Any, teachers: Any, rules: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate one committee from a dictionary or a GroupDraft-like object.

    Teachers may be dictionaries/domain objects in a sequence or an ID-keyed
    mapping. The result is independent of Django and never mutates its inputs.
    A chair also present in expert_ids occupies one seat and is checked as chair.
    """
    group_id = _value(draft, "group_id", "groupId", default="")
    chair = _normal_id(_value(draft, "chair_id", "chairId"))
    secretary = _normal_id(_value(draft, "secretary_id", "secretaryId"))
    experts = {_normal_id(value) for value in
               (_value(draft, "expert_ids", "expertIds", default=[]) or []) if value is not None}
    teacher_map = _teacher_map(teachers)
    included = _includes_chair(rules)
    defense = _DEFENSE_TYPES.get(str(_value(rules, "defense_type", "defenseType", default="")).strip().lower())
    policy = scenario_policy(defense) if defense is not None else {}
    qualifications = rules.get("roleQualification") or {}
    defaults = policy.get("roleQualification", {}) if included else {}
    chair_key = "chairmanMinTitle" if defense == "formal" else "leaderMinTitle"
    chair_title = _value(rules, "chair_title", default=qualifications.get(chair_key, defaults.get(chair_key, "")))
    secretary_title = _value(rules, "secretary_title", default=qualifications.get("secretaryMinTitle", defaults.get("secretaryMinTitle", "")))
    conflicts: list[dict[str, Any]] = []

    def report(kind: str, description: str, ids: list[Any], **extra: Any) -> None:
        conflicts.append({"type": kind, "description": f"{group_id} {description}".strip(),
                          "related_ids": [group_id, *ids], "group_id": group_id, **extra})

    assigned_roles = [(chair, "chair", chair_title), (secretary, "secretary", secretary_title)]
    assigned_roles.extend((tid, "expert", "") for tid in sorted(experts - {chair}, key=str))
    inactive_reported: set[Any] = set()
    role_labels = {"chair": "主席" if defense == "formal" else "组长", "secretary": "秘书", "expert": "专家"}
    for tid, role, required_title in assigned_roles:
        if tid is None or tid not in teacher_map:
            continue
        raw = teacher_map[tid]
        name = raw.get("name") or str(tid)
        if not _is_active(raw):
            if tid not in inactive_reported:
                report("teacher_inactive", f"教师 {name} 已停用，不能参与本组排期", [tid])
                inactive_reported.add(tid)
            continue
        if role == "expert" and not _member_eligible(raw):
            report("member_ineligible", f"教师 {name} 不适合担任组员，仅可按资格担任主席/组长", [tid])
            continue
        if not teacher_can_role(raw, role) or not _meets_title(raw.get("title"), required_title):
            report("role_qualification", f"教师 {name} 不具备担任{role_labels[role]}的角色或职称资格", [tid], role=role)

    # A legacy rule has no new scenario headcount constraint. V2 always enforces
    # the documented minimum/fixed count, even when its configured target differs.
    if included:
        committee = experts | ({chair} if chair is not None else set())
        configured_expert = rules.get("expertCount") or {}
        minimum = max(_number(policy.get("expertCount", {}).get("min")),
                      _number(_value(rules, "expert_min", default=configured_expert.get("min", 0))))
        maxima = [value for value in (
            policy.get("expertCount", {}).get("max"),
            _value(rules, "expert_max", default=configured_expert.get("max")),
        ) if value is not None]
        maximum = min(map(int, maxima)) if maxima else None
        if len(committee) < minimum or (maximum is not None and len(committee) > maximum):
            limit = f"恰好 {minimum} 人" if minimum == maximum else f"至少 {minimum} 人"
            if maximum is not None and minimum != maximum:
                limit += f"，最多 {maximum} 人"
            report("expert_count_out_of_range", f"专家人数应为{limit}（含主席/组长），实际 {len(committee)} 人", [],
                   assigned=len(committee), min_required=minimum, max_allowed=maximum)

    software_min = _value(rules, "software_teacher_min", "software_minimum", "formal_software_min",
                          "formalSoftwareMin", "softwareTeacherMin", default=_MISSING)
    if defense == "formal" and (included or software_min is not _MISSING):
        minimum = max(3 if included else 0, _number(software_min, 3) if software_min is not _MISSING else 3)
        committee = experts | ({chair} if chair is not None else set())
        software_count = sum(is_software_teacher(teacher_map[tid]) for tid in committee if tid in teacher_map)
        if software_count < minimum:
            report("software_majority", f"正式答辩至少需要 {minimum} 位软件学院导师，实际 {software_count} 人", [],
                   assigned=software_count, min_required=minimum)
    return conflicts
