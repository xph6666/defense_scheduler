"""Transactional relationship-aware student movement commands."""
from ..models import Teacher


def move_student_bundle(student, source, target, *, preserve_secretary=True, move_mentor=True, replacement_secretary=None):
    previous_secretary = student.bound_secretary or source.secretary
    if source.schedule_version.defense_type == 'formal':
        saved = next((s for s in source.schedule_version.input_snapshot.get('students', []) if s['id'] == student.pk), None)
        if saved and saved.get('secretary_id'):
            previous_secretary = Teacher.objects.filter(pk=saved['secretary_id']).first() or previous_secretary
    if previous_secretary is None and student.secretary_name:
        previous_secretary = Teacher.objects.filter(name=student.secretary_name).first()
    mentor = student.mentor
    if mentor is None and student.mentor_name:
        mentor = Teacher.objects.filter(name=student.mentor_name).first()
    source.students.remove(student)
    target.students.add(student)
    changes = {'studentId': student.pk, 'fromGroupId': source.pk, 'toGroupId': target.pk,
        'mentorId': mentor.pk if mentor else None, 'mentorMoved': False,
        'secretaryPreserved': preserve_secretary}
    if preserve_secretary and previous_secretary:
        # Keep existing target students' secretary assignment. A mismatch is an
        # explicit draft conflict; it must never silently rebind that whole group.
        if target.secretary_id is None:
            target.secretary = previous_secretary
            target.save(update_fields=['secretary'])
        student.secretary_name = previous_secretary.name
        student.bound_secretary = previous_secretary
    elif not preserve_secretary:
        new_secretary = replacement_secretary or target.secretary
        student.bound_secretary = new_secretary
        student.secretary_name = new_secretary.name if new_secretary else ''
    # Formal-stage relationship changes are persisted in that version's input
    # snapshot by the caller; the global binding belongs to the pre round.
    if source.schedule_version.defense_type != 'formal':
        student.save(update_fields=['secretary_name', 'bound_secretary'])
    # In pre/mid defenses the mentor is a committee member in the student's group.
    # Formal defenses keep the mentor identity and use the same-session validator.
    if move_mentor and mentor and source.schedule_version.defense_type in ('pre', 'mid'):
        if target.chair_id != mentor.pk:
            target.experts.add(mentor)
        remaining = source.students.filter(mentor_id=mentor.pk).exists() or source.students.filter(mentor_name=mentor.name).exists()
        if not remaining:
            source.experts.remove(mentor)
            if source.chair_id == mentor.pk:
                source.chair = None
                source.save(update_fields=['chair'])
        changes['mentorMoved'] = True
    changes['secretaryId'] = student.bound_secretary_id
    return changes
