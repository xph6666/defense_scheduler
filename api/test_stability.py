"""Regression cases from the production-readiness review (isolated test DB)."""
from django.contrib.auth.models import User
from django.test import TestCase, SimpleTestCase
from rest_framework.test import APIClient

from algorithm import generate_schedule
from .models import Group, Room, ScheduleVersion, Student, Teacher
from .views import ScheduleViewSet


class SchedulingFeasibilityTests(SimpleTestCase):
    def test_tries_another_slot_when_teachers_are_busy(self):
        result = generate_schedule(
            [{'id': i, 'name': f'T{i}', 'available_time': ['2026-09-16 09:00-12:00']} for i in (1, 2)],
            [{'id': 1, 'name': 'S1'}],
            [{'id': 1, 'available_time': ['2026-09-16 09:00-12:00', '2026-09-16 14:00-17:00']}],
            {'start_date': '2026-09-16', 'end_date': '2026-09-16', 'group_size': 1, 'expert_count': 1},
        )
        self.assertEqual(result['groups'][0]['time'], '2026-09-16 14:00-17:00')
        self.assertEqual(result['conflicts'], [])

    def test_explicit_empty_availability_is_not_unlimited(self):
        result = generate_schedule(
            [{'id': 1, 'name': 'T1'}], [{'id': 1, 'name': 'S1'}],
            [{'id': 1, 'availability_restricted': True, 'available_time': []}],
            {'start_date': '2026-09-16', 'end_date': '2026-09-16', 'group_size': 1, 'expert_count': 0},
        )
        self.assertIsNone(result['groups'][0]['room_id'])


class ScheduleIntegrityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('reviewer', is_staff=True))
        self.version = ScheduleVersion.objects.create(defense_type='pre')
        self.teacher = Teacher.objects.create(name='Reviewer', title='教授')
        self.room = Room.objects.create(name='R1', campus='创新港')
        self.a = Group.objects.create(schedule_version=self.version, group_id='A',
            time='2026-09-16 09:00-11:00', chair=self.teacher, room=self.room, campus='创新港')
        self.b = Group.objects.create(schedule_version=self.version, group_id='B',
            time='2026-09-16 10:00-12:00', chair=self.teacher, room=self.room, campus='创新港')
        self.student = Student.objects.create(name='S1', student_no='001', defense_types=['预答辩'])
        self.a.students.add(self.student)

    def test_overlapping_intervals_report_teacher_and_room_conflicts(self):
        kinds = {c['type'] for c in ScheduleViewSet()._check_conflicts(self.version)}
        self.assertTrue(kinds & {'time_conflict', 'teacher_time_conflict'})
        self.assertIn('room_conflict', kinds)

    def test_cross_version_move_is_rejected_without_writes(self):
        other = ScheduleVersion.objects.create(defense_type='formal')
        target = Group.objects.create(schedule_version=other, group_id='C', time=self.b.time)
        response = self.client.post('/api/schedule/adjust/', {
            'action': 'move_student', 'student_id': self.student.id,
            'from_group_id': self.a.id, 'to_group_id': target.id,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.a.students.filter(pk=self.student.pk).exists())
        self.assertFalse(target.students.exists())

    def test_whole_group_edit_cannot_duplicate_student(self):
        response = self.client.post('/api/schedule/adjust-group/', {
            'group_id': self.b.id, 'group_data': {'students': [{'id': self.student.id}]},
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.b.students.exists())

    def test_retired_version_cannot_be_adjusted(self):
        self.version.is_current = False
        self.version.save()
        response = self.client.post('/api/schedule/adjust/', {
            'action': 'change_time', 'group_id': self.a.id, 'new_time': '2026-09-17 09:00-11:00',
        }, format='json')
        self.assertEqual(response.status_code, 409)

    def test_conflict_check_and_current_agree_after_edit(self):
        checked = self.client.post('/api/schedule/check-conflicts/', {'defense_type': 'pre'}, format='json')
        current = self.client.get('/api/schedule/current/', {'defense_type': 'pre'})
        self.assertEqual(current.data['conflicts'], checked.data)

    def test_stale_revision_is_rejected_without_mutation(self):
        self.version.revision = 3
        self.version.save()
        response = self.client.post('/api/schedule/adjust/', {
            'action': 'change_time', 'group_id': self.a.id,
            'new_time': '2026-09-17 09:00-11:00', 'expected_revision': 2,
        }, format='json')
        self.assertEqual(response.status_code, 409)
        self.a.refresh_from_db()
        self.assertEqual(self.a.time, '2026-09-16 09:00-11:00')

    def test_missing_revision_is_rejected_without_mutation(self):
        response = self.client.post('/api/schedule/adjust/', {
            'action': 'change_time', 'group_id': self.a.id, 'new_time': '2026-09-17 09:00-11:00',
        }, format='json')
        self.assertEqual(response.status_code, 428)
        self.a.refresh_from_db()
        self.assertEqual(self.a.time, '2026-09-16 09:00-11:00')

    def test_published_version_is_frozen_and_export_uses_snapshot(self):
        from .schedule_integrity import export_groups
        self.b.delete()
        self.a.secretary = Teacher.objects.create(name='Secretary', title='讲师')
        self.a.save()
        response = self.client.post('/api/schedule/publish/', {
            'version_id': self.version.id, 'expected_revision': 0,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        Teacher.objects.filter(pk=self.teacher.pk).update(name='Renamed')
        self.student.delete()
        current = self.client.get('/api/schedule/current/')
        self.assertEqual(current.data['groups'][0]['chairman'], 'Reviewer')
        self.assertEqual(current.data['groups'][0]['students'][0]['name'], 'S1')
        self.version.refresh_from_db()
        frozen = list(export_groups(self.version))[0]
        self.assertEqual(frozen.chair.name, 'Reviewer')
        self.assertEqual(frozen.students.all()[0].name, 'S1')
        response = self.client.post('/api/schedule/adjust/', {
            'action': 'change_time', 'group_id': self.a.id,
            'new_time': '2026-09-17 09:00-11:00', 'expected_revision': 1,
        }, format='json')
        self.assertEqual(response.status_code, 409)

    def test_publish_rejects_conflicts(self):
        response = self.client.post('/api/schedule/publish/', {
            'version_id': self.version.id, 'expected_revision': 0,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, 'draft')

    def test_group_edit_synchronizes_secretary_and_audit_actor(self):
        from .models import OperationLog
        secretary = Teacher.objects.create(name='Secretary', title='讲师')
        response = self.client.post('/api/schedule/adjust-group/', {
            'group_id': self.a.id, 'group_data': {'secretary': secretary.name}, 'expected_revision': 0,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.secretary_name, secretary.name)
        log = OperationLog.objects.get(authoritative=True)
        self.assertEqual(log.operator, 'reviewer')
        response = self.client.delete('/api/operation-logs/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(OperationLog.objects.filter(pk=log.pk).exists())

    def test_generation_retry_reuses_version(self):
        request = {'rules': {'defense_type': 'pre', 'start_date': '2026-09-16',
            'end_date': '2026-09-16', 'group_size': 1, 'expert_count': 0}, 'request_key': 'same-generation'}
        first = self.client.post('/api/schedule/generate/', request, format='json')
        second = self.client.post('/api/schedule/generate/', request, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(first.data['versionId'], second.data['versionId'])
        self.assertEqual(ScheduleVersion.objects.filter(request_key='same-generation').count(), 1)


class SessionSecurityTests(TestCase):
    def test_logout_revokes_the_server_token(self):
        from rest_framework.authtoken.models import Token
        user = User.objects.create_user('session-user')
        token = Token.objects.create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(client.post('/api/auth/logout/').status_code, 200)
        self.assertEqual(client.get('/api/students/').status_code, 401)

    def test_expired_token_is_rejected(self):
        from datetime import timedelta
        from django.utils import timezone
        from rest_framework.authtoken.models import Token
        user = User.objects.create_user('expired-session')
        token = Token.objects.create(user=user)
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(days=2))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(client.get('/api/students/').status_code, 401)
