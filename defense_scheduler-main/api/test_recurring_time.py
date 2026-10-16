"""周期性时间描述解析（api/recurring_time.py）与排期集成的测试。"""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Room, Student, Teacher
from .recurring_time import expand_recurring_entry, is_no_limit_entry


class ExpandRecurringEntryTests(TestCase):
    """expand_recurring_entry 单元测试。2025-05-12 是周一。"""

    WEEK_START = date(2025, 5, 12)
    WEEK_END = date(2025, 5, 18)

    def test_weekday_span_full_day(self):
        result = expand_recurring_entry('周一至周五全天', self.WEEK_START, self.WEEK_END)
        self.assertEqual(result, [
            '2025-05-12 08:00-18:00',
            '2025-05-13 08:00-18:00',
            '2025-05-14 08:00-18:00',
            '2025-05-15 08:00-18:00',
            '2025-05-16 08:00-18:00',
        ])

    def test_weekly_afternoon(self):
        result = expand_recurring_entry('每周三下午', self.WEEK_START, self.WEEK_END)
        self.assertEqual(result, ['2025-05-14 14:00-18:00'])

    def test_xingqi_morning(self):
        result = expand_recurring_entry('星期三上午', self.WEEK_START, self.WEEK_END)
        self.assertEqual(result, ['2025-05-14 08:00-12:00'])

    def test_weekend_with_explicit_clock(self):
        result = expand_recurring_entry('周末 9:00-12:00', self.WEEK_START, self.WEEK_END)
        self.assertEqual(result, ['2025-05-17 09:00-12:00', '2025-05-18 09:00-12:00'])

    def test_workday_keyword(self):
        result = expand_recurring_entry('工作日上午', date(2025, 5, 16), date(2025, 5, 19))
        # 5-16 周五、5-19 周一，周末被跳过
        self.assertEqual(result, ['2025-05-16 08:00-12:00', '2025-05-19 08:00-12:00'])

    def test_multiple_weekdays_listed(self):
        result = expand_recurring_entry('周一、周四下午', self.WEEK_START, self.WEEK_END)
        self.assertEqual(result, ['2025-05-12 14:00-18:00', '2025-05-15 14:00-18:00'])

    def test_weekday_only_defaults_to_full_day(self):
        result = expand_recurring_entry('周二', self.WEEK_START, self.WEEK_END)
        self.assertEqual(result, ['2025-05-13 08:00-18:00'])

    def test_fullwidth_and_tilde_normalization(self):
        # 全角数字/冒号 + 波浪线 + 空格都应被归一化
        result = expand_recurring_entry('周一～周二 ９：００-１２：００', self.WEEK_START, self.WEEK_END)
        self.assertEqual(result, ['2025-05-12 09:00-12:00', '2025-05-13 09:00-12:00'])

    def test_no_limit_words_expand_to_empty(self):
        for word in ('随时', '不限', '无'):
            self.assertEqual(expand_recurring_entry(word, self.WEEK_START, self.WEEK_END), [])
            self.assertTrue(is_no_limit_entry(word))

    def test_unrecognized_text_returns_none(self):
        for text in ('待定', '另行通知', '2025-05-10 09:00-12:00', ''):
            self.assertIsNone(expand_recurring_entry(text, self.WEEK_START, self.WEEK_END))
        self.assertFalse(is_no_limit_entry('待定'))

    def test_recurring_outside_range_returns_empty(self):
        # 范围只有周六日，"周一全天"无匹配
        result = expand_recurring_entry('周一全天', date(2025, 5, 17), date(2025, 5, 18))
        self.assertEqual(result, [])


class RecurringTimeScheduleIntegrationTests(TestCase):
    """周期性时间描述在排期接口中的端到端行为。2025-05-12 是周一。"""

    RULES = {
        'defense_type': 'pre',
        'start_date': '2025-05-12',
        'end_date': '2025-05-12',
        'group_size': 1,
        'expert_count': 1,
        'avoid_weekend': False,
        'avoid_supervisor': False,
    }

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser(username='admin', password='strong-pass-123')
        self.client.force_authenticate(self.user)
        Student.objects.create(
            name='学生1', student_type='学硕', campus='创新港', defense_types=['预答辩'],
        )

    def _generate(self):
        return self.client.post('/api/schedule/generate/', {'rules': self.RULES}, format='json')

    def _assigned_teacher_names(self, response):
        names = []
        for group in response.data['groups']:
            names.extend(teacher['name'] for teacher in group['teachers'])
            names.extend(
                name for name in [group.get('chairman'), group.get('secretary')]
                if name and name != '未分配'
            )
        return names

    def test_teacher_recurring_unavailable_time_takes_effect(self):
        # "周一至周五全天"覆盖排期日（周一），忙碌老师不应被排入，且不产生格式提示
        Teacher.objects.create(name='忙碌老师', title='教授', unavailable_times='周一至周五全天')
        Teacher.objects.create(name='空闲老师甲', title='副教授')
        Teacher.objects.create(name='空闲老师乙', title='讲师')
        Room.objects.create(campus='创新港', name='A101', capacity=30, available_times='')

        response = self._generate()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('忙碌老师', self._assigned_teacher_names(response))
        notices = [c for c in response.data['conflicts'] if c['type'] == '数据完整性提示']
        self.assertEqual(notices, [])

    def test_room_recurring_available_time_takes_effect(self):
        # 教室可用时间"周一至周五全天"应展开生效，正常排出周一的场次且无提示
        Teacher.objects.create(name='王老师', title='教授')
        Teacher.objects.create(name='李老师', title='讲师')
        Room.objects.create(
            campus='创新港', name='教学楼4-106', capacity=30,
            available_times='周一至周五全天',
        )

        response = self._generate()

        self.assertEqual(response.status_code, 200)
        notices = [c for c in response.data['conflicts'] if c['type'] == '数据完整性提示']
        self.assertEqual(notices, [])
        self.assertEqual(response.data['groups'][0]['date'], '2025-05-12')

    def test_room_recurring_time_without_match_generates_notice(self):
        # 教室只在周末可用而排期日是周一：提示"没有匹配的日期"，回退全时段可用
        Teacher.objects.create(name='王老师', title='教授')
        Teacher.objects.create(name='李老师', title='讲师')
        Room.objects.create(campus='创新港', name='B202', capacity=30, available_times='周末全天')

        response = self._generate()

        self.assertEqual(response.status_code, 200)
        notices = [c for c in response.data['conflicts'] if c['type'] == '数据完整性提示']
        self.assertEqual(len(notices), 1)
        self.assertIn('B202', notices[0]['reason'])
        self.assertIn('没有匹配的日期', notices[0]['reason'])
