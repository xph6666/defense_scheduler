"""Keep stable teacher references compatible with existing name-based imports.

Names remain available for unresolved historical records and after a teacher is
deleted. A linked teacher's current name is authoritative. Published schedule
snapshots are deliberately excluded from these reference-data mutations.
"""
import re

from django.db import transaction
from django.db.models import Q

from ..models import Student, Teacher


class ReferenceDataError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


REFERENCE_FIELDS = (
    ('mentor', 'mentor_name', 'mentorId', 'mentorName'),
    ('bound_secretary', 'secretary_name', 'secretaryId', 'secretaryName'),
)


def sync_student_references(attrs, instance=None):
    """Return validated model attributes for an ID or legacy-name update.

    Omitted references stay unchanged. A name-only import matches an existing
    teacher when possible; unresolved names remain editable legacy data. Sending
    both a teacher ID and a different name is an error instead of silently
    replacing one input with the other.
    """
    result = dict(attrs)
    for relation, name_field, id_label, name_label in REFERENCE_FIELDS:
        has_id = relation in result
        has_name = name_field in result
        if not has_id and not has_name:
            continue
        name = str(result.get(name_field) or '').strip() if has_name else None
        if has_id:
            teacher = result[relation]
            canonical_name = teacher.name if teacher else ''
            if has_name and name != canonical_name:
                raise ReferenceDataError({name_label: [f'{name_label} 与 {id_label} 指向的教师不一致']})
            result[name_field] = canonical_name
        else:
            teacher = Teacher.objects.filter(name=name).first() if name else None
            result[relation] = teacher
            result[name_field] = teacher.name if teacher else name
    return result


def sync_teacher_rename(teacher, previous_name):
    """Refresh mutable references after a successful teacher rename.

    Call inside the transaction that saves the teacher. Only exact name tokens
    in exclusion lists are replaced, so names containing the old name survive.
    """
    for relation, name_field, _, _ in REFERENCE_FIELDS:
        Student.objects.filter(
            Q(**{relation: teacher})
            | Q(**{f'{relation}__isnull': True, name_field: previous_name})
        ).update(**{relation: teacher, name_field: teacher.name})
    if previous_name == teacher.name:
        return
    for other in Teacher.objects.exclude(avoid_teacher_names='').iterator():
        parts = re.split(r'([,，;；、\n/])', other.avoid_teacher_names)
        changed = False
        for index in range(0, len(parts), 2):
            if parts[index].strip() == previous_name:
                parts[index] = parts[index].replace(previous_name, teacher.name, 1)
                changed = True
        if changed:
            Teacher.objects.filter(pk=other.pk).update(avoid_teacher_names=''.join(parts))


@transaction.atomic
def rename_teacher(teacher, new_name):
    """Rename a teacher and all mutable references atomically."""
    new_name = str(new_name or '').strip()
    if not new_name:
        raise ReferenceDataError({'name': ['教师姓名不能为空']})
    locked = Teacher.objects.select_for_update().get(pk=teacher.pk)
    if Teacher.objects.filter(name=new_name).exclude(pk=locked.pk).exists():
        raise ReferenceDataError({'name': ['教师姓名已存在，请使用唯一姓名']})
    previous_name = locked.name
    locked.name = new_name
    locked.save(update_fields=['name'])
    sync_teacher_rename(locked, previous_name)
    teacher.name = new_name
    return teacher
