"""Transactional schedule editing, immutable exports and server-side audit."""
from copy import deepcopy
from functools import wraps
from types import SimpleNamespace

from django.db import transaction
from django.db.models import F, Prefetch
from rest_framework.response import Response

from .models import Group, OperationLog, ScheduleVersion, ScheduleWriteLock, Student


def audit(request, action, description, **details):
    OperationLog.objects.create(type=action, module='排期管理', description=description,
        operator=request.user.get_username(), authoritative=True, details=details)


def schedule_write(fn):
    """Serialize writers on SQLite and PostgreSQL, rolling back rejected changes."""
    @wraps(fn)
    def wrapped(self, request, *args, **kwargs):
        with transaction.atomic():
            # This must be the first query in the transaction (SQLite lock upgrade).
            ScheduleWriteLock.objects.filter(pk=1).update(revision=F('revision') + 1)
            group_ids = [request.data[k] for k in ('group_id', 'from_group_id', 'to_group_id') if request.data.get(k)]
            try:
                groups = list(Group.objects.select_related('schedule_version').filter(pk__in=group_ids))
            except (ValueError, TypeError):
                return Response({'error': '分组 ID 格式不正确'}, status=400)
            versions = {g.schedule_version_id: g.schedule_version for g in groups}
            before = {str(version.id): self._version_result(version) for version in versions.values()}
            if len(versions) > 1:
                return Response({'error': '不能跨排期版本移动学生'}, status=400)
            for version in versions.values():
                if not version.is_current or version.status == 'published':
                    return Response({'error': '该版本已发布或已归档，请生成新草稿后修改'}, status=409)
                expected = request.data.get('expected_revision')
                if expected is not None and str(expected) != str(version.revision):
                    return Response({'error': '排期已被其他操作修改，请刷新后重新编辑'}, status=409)
            response = fn(self, request, *args, **kwargs)
            if response.status_code >= 400:
                transaction.set_rollback(True)
                return response
            if versions and request.data.get('expected_revision') is None:
                transaction.set_rollback(True)
                return Response({'error': '缺少编辑版本号，请刷新页面后重新提交'}, status=428)
            for version in versions.values():
                # Commands may update their own ORM instance's relation baseline.
                # Reload it before validating and incrementing this transaction.
                version.refresh_from_db()
                edited_group = next((g for g in groups if str(g.pk) == str(request.data.get('group_id'))), None)
                secretary_edit = request.data.get('action') == 'change_secretary'
                group_data = request.data.get('group_data') or {}
                if fn.__name__ == 'adjust_group' and edited_group and any(
                        key in group_data for key in ('secretary', 'secretaryId')):
                    # Complete edit forms also submit an unchanged secretary.
                    # Only an actual change authorizes rebinding the students.
                    saved_secretary_id = Group.objects.filter(pk=edited_group.pk).values_list('secretary_id', flat=True).first()
                    secretary_edit = secretary_edit or saved_secretary_id != edited_group.secretary_id
                if version.defense_type == 'pre' and secretary_edit and edited_group:
                    self._sync_student_secretaries(version, group_id=edited_group.pk)
                version.revision += 1
                version.conflicts_snapshot = self._check_conflicts(version)
                version.save(update_fields=['revision', 'conflicts_snapshot'])
                if isinstance(response.data, dict) and 'conflicts' in response.data:
                    response.data['conflicts'] = version.conflicts_snapshot
                    response.data['revision'] = version.revision
            audit(request, '调整' if group_ids else '生成', f'完成排期操作：{fn.__name__}',
                  group_ids=group_ids, version_ids=list(versions), changes=request.data,
                  before=before, after={str(v.id): self._version_result(v) for v in versions.values()})
            return response
    return wrapped


class FrozenList(list):
    def all(self):
        return self
    def select_related(self, *args):
        return self
    def prefetch_related(self, *args):
        return self
    def order_by(self, *args):
        return self


def capture_export_groups(version):
    if version.export_snapshot:
        return deepcopy(version.export_snapshot)
    from .models import Teacher
    teacher_details = list(Teacher.objects.values_list('id', 'name', 'title'))
    titles = {name: title for _, name, title in teacher_details}
    teacher_names = {teacher_id: name for teacher_id, name, _ in teacher_details}
    # A formal draft's explicit edits belong to this version. A later pre round
    # may rebind Student globally without changing these saved relationships.
    secretary_bindings = {row['id']: row['secretary_id']
        for row in version.input_snapshot.get('students', []) if 'secretary_id' in row
    } if version.defense_type == 'formal' else {}
    def fields(obj):
        if obj is None:
            return None
        return {f.attname: getattr(obj, f.attname) for f in obj._meta.fields}
    def student_fields(student):
        values = fields(student)
        mentor_name = student.mentor.name if student.mentor_id else student.mentor_name
        values['mentor_name'] = mentor_name
        if student.pk in secretary_bindings:
            secretary_id = secretary_bindings[student.pk]
            values['bound_secretary_id'] = secretary_id
            # Preserve a dangling ID so validation can report the data error;
            # neither an explicit None nor a missing teacher falls back.
            values['secretary_name'] = teacher_names.get(secretary_id, '')
        elif student.bound_secretary_id:
            values['secretary_name'] = student.bound_secretary.name
        values['mentor_title'] = titles.get(mentor_name, '')
        return values
    return [dict(id=g.id, group_id=g.group_id, time=g.time, campus=g.campus,
                 room=fields(g.room), chair=fields(g.chair), secretary=fields(g.secretary),
                 experts=[fields(t) for t in g.experts.all()],
                 students=[student_fields(s) for s in g.students.all()])
            for g in version.groups.select_related('room', 'chair', 'secretary').prefetch_related(
                'experts', Prefetch('students', queryset=Student.objects.select_related('mentor', 'bound_secretary'))).order_by('id')]


def export_groups(version):
    if not version.export_snapshot and version.defense_type != 'formal':
        return version.groups.select_related('room', 'chair', 'secretary').prefetch_related(
            'experts', Prefetch('students', queryset=Student.objects.select_related('mentor', 'bound_secretary'))).order_by('id')
    groups = FrozenList()
    rows = version.export_snapshot or capture_export_groups(version)
    for row in rows:
        values = dict(row)
        for key in ('room', 'chair', 'secretary'):
            values[key] = SimpleNamespace(**values[key]) if values[key] else None
            values[f'{key}_id'] = values[key].id if values[key] else None
        for key in ('experts', 'students'):
            values[key] = FrozenList(SimpleNamespace(**item) for item in values[key])
        groups.append(SimpleNamespace(**values))
    return groups
