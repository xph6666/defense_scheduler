"""Campus batch selection and shared staff reservations."""
from collections import defaultdict
from django.db.models import Q
from ..models import ScheduleVersion
from ..schedule_integrity import export_groups


def current_pre(rules):
    campus = rules.get('campus_scope', '')
    versions = ScheduleVersion.objects.filter(defense_type='pre', is_current=True)
    if campus:
        return versions.filter(campus_scope=campus).first() or versions.filter(campus_scope='').first()
    return versions.filter(campus_scope='').first()


def replaced_versions(rules):
    versions = ScheduleVersion.objects.filter(defense_type=rules['defense_type'], is_current=True)
    campus = rules.get('campus_scope', '')
    return versions.filter(Q(campus_scope=campus) | Q(campus_scope='')) if campus else versions


def other_batch_reservations(rules, *, exclude_version_id=None):
    """Reserve staff in other current batches, including frozen published exports."""
    busy = defaultdict(list)
    versions = ScheduleVersion.objects.filter(is_current=True).exclude(pk=exclude_version_id)
    versions = versions.exclude(pk__in=replaced_versions(rules).values_list('pk', flat=True))
    for version in versions:
        for group in export_groups(version):
            if not group.time:
                continue
            people = {group.chair_id, group.secretary_id, *[t.id for t in group.experts.all()]} - {None}
            if (version.rules_snapshot.get('formal_mentor_same_session') or
                    (version.defense_type in ('pre', 'formal') and not version.rules_snapshot.get('formal_rotation'))):
                people.update(getattr(s, 'mentor_id', None) for s in group.students.all())
            for teacher_id in people - {None}:
                busy[teacher_id].append((group.time, version.pk, group.group_id, version.campus_scope or group.campus))
    return busy


def cross_batch_conflicts(version, groups):
    if not version.campus_scope:
        return []
    from algorithm import parse_time_range, SchedulingError, make_conflict
    rules = {**version.rules_snapshot, 'campus_scope': version.campus_scope}
    busy = other_batch_reservations(rules, exclude_version_id=version.pk)
    result = []
    for group in groups:
        if not group.time:
            continue
        try:
            slot = parse_time_range(group.time)
        except SchedulingError:
            continue
        people = {group.chair_id, group.secretary_id, *[t.id for t in group.experts.all()]} - {None}
        if version.defense_type in ('pre', 'formal') and not rules.get('formal_rotation'):
            people.update(getattr(s, 'mentor_id', None) for s in group.students.all())
        for tid in people:
            for text, other_id, other_group, campus in busy.get(tid, []):
                try:
                    other = parse_time_range(text)
                except SchedulingError:
                    continue
                if slot.start < other.end and other.start < slot.end:
                    result.append(make_conflict('teacher_time_conflict',
                        f'{group.group_id} 教师编号 {tid} 与{campus}批次 vID {other_id} 的 {other_group} 时间冲突',
                        [group.group_id], group_db_ids=[group.id]))
    return result
