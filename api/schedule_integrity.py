"""Transactional schedule editing, immutable exports and server-side audit."""
from functools import wraps
from types import SimpleNamespace

from django.db import transaction
from django.db.models import F
from rest_framework.response import Response

from .models import Group, OperationLog, ScheduleVersion, ScheduleWriteLock


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
                if version.defense_type == 'pre':
                    self._sync_student_secretaries(version)
                version.revision += 1
                version.conflicts_snapshot = self._check_conflicts(version)
                version.save(update_fields=['revision', 'conflicts_snapshot'])
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
    from .models import Teacher
    titles = dict(Teacher.objects.values_list('name', 'title'))
    def fields(obj):
        if obj is None:
            return None
        return {f.name: getattr(obj, f.name) for f in obj._meta.fields}
    return [dict(id=g.id, group_id=g.group_id, time=g.time, campus=g.campus,
                 room=fields(g.room), chair=fields(g.chair), secretary=fields(g.secretary),
                 experts=[fields(t) for t in g.experts.all()],
                 students=[{**fields(s), 'mentor_title': titles.get(s.mentor_name, '')} for s in g.students.all()])
            for g in version.groups.select_related('room', 'chair', 'secretary').prefetch_related('experts', 'students')]


def export_groups(version):
    if not version.export_snapshot:
        return version.groups.select_related('room', 'chair', 'secretary').prefetch_related('experts', 'students').order_by('id')
    groups = FrozenList()
    for row in version.export_snapshot:
        values = dict(row)
        for key in ('room', 'chair', 'secretary'):
            values[key] = SimpleNamespace(**values[key]) if values[key] else None
            values[f'{key}_id'] = values[key].id if values[key] else None
        for key in ('experts', 'students'):
            values[key] = FrozenList(SimpleNamespace(**item) for item in values[key])
        groups.append(SimpleNamespace(**values))
    return groups
