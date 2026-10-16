"""导入时对时间字段的即时校验提醒（warnings）的测试。"""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Room, Teacher
from .tests import make_xlsx_upload


class ImportTimeWarningTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser(username='admin', password='strong-pass-123')
        self.client.force_authenticate(self.user)

    def _import_teachers(self, rows):
        upload = make_xlsx_upload('教师.xlsx', [['姓名', '职称', '不可用时间']] + rows)
        return self.client.post('/api/teachers/import_data/', {'file': upload}, format='multipart')

    def _import_rooms(self, rows):
        upload = make_xlsx_upload('教室.xlsx', [['校区', '教室名称', '容量', '可用时间']] + rows)
        return self.client.post('/api/rooms/import_data/', {'file': upload}, format='multipart')

    def test_teacher_unrecognized_time_returns_warning(self):
        response = self._import_teachers([['张老师', '教授', '待定']])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['warningCount'], 1)
        warning = response.data['warnings'][0]
        self.assertIn('第 2 行', warning)
        self.assertIn('张老师', warning)
        self.assertIn('待定', warning)
        self.assertIn('周一至周五全天', warning)
        # 数据本身仍然入库，只是提醒
        self.assertTrue(Teacher.objects.filter(name='张老师').exists())

    def test_teacher_recurring_and_absolute_times_pass_silently(self):
        response = self._import_teachers([
            ['李老师', '副教授', '周一至周五全天'],
            ['王老师', '讲师', '2025-05-10 09:00-12:00'],
            ['赵老师', '教授', ''],
        ])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['warningCount'], 0)
        self.assertEqual(response.data['warnings'], [])

    def test_room_unrecognized_time_returns_warning(self):
        response = self._import_rooms([['创新港', 'B202', 30, '另行通知']])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['warningCount'], 1)
        warning = response.data['warnings'][0]
        self.assertIn('B202', warning)
        self.assertIn('另行通知', warning)
        self.assertIn('全时段可用', warning)
        self.assertTrue(Room.objects.filter(name='B202').exists())

    def test_room_no_limit_word_passes_silently(self):
        response = self._import_rooms([['创新港', 'A101', 30, '随时']])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['warningCount'], 0)
