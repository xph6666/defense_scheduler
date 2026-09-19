"""Capture successful base-data changes on the server, in the same transaction."""
from django.db import transaction
from django.db.models import F
from .models import OperationLog, ScheduleVersion, ScheduleWriteLock


class AuditedDataMixin:
    def perform_update(self, serializer):
        self._audit_before = dict(self.get_serializer(serializer.instance).data)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._audit_before = dict(self.get_serializer(instance).data)
        super().perform_destroy(instance)

    def dispatch(self, request, *args, **kwargs):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return super().dispatch(request, *args, **kwargs)
        with transaction.atomic():
            ScheduleWriteLock.objects.filter(pk=1).update(revision=F('revision') + 1)
            response = super().dispatch(request, *args, **kwargs)
            if response.status_code < 400:
                # Resource edits invalidate an administrator's open draft form.
                ScheduleVersion.objects.filter(is_current=True, status='draft').update(revision=F('revision') + 1)
                OperationLog.objects.create(type='数据变更', module=self.basename,
                    operator=self.request.user.get_username(), authoritative=True,
                    description=f'{request.method} {request.path}',
                    details={'action': self.action, 'object_id': kwargs.get('pk'),
                             'before': getattr(self, '_audit_before', None), 'after': response.data})
            else:
                transaction.set_rollback(True)
            return response
