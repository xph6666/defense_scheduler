from django.test import TestCase
from rest_framework.test import APIClient

from .models import Room, Student, Teacher


class IntegrationContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_rule_config_api_supports_frontend_contract(self):
        response = self.client.get('/api/rule-config/', {'defense_type': 'pre'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['defenseType'], '预答辩')
        self.assertIn('studentCount', response.data)

        response = self.client.post(
            '/api/rule-config/',
            {
                'defense_type': 'pre',
                'defenseType': '预答辩',
                'studentCount': {'target': 6, 'min': 3, 'max': 8},
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['studentCount']['target'], 6)

    def test_operation_logs_api_supports_frontend_contract(self):
        create_response = self.client.post(
            '/api/operation-logs/',
            {
                'type': 'save_rule_config',
                'module': 'rule-config',
                'description': 'updated rule config',
                'operator': 'admin',
                'result': 'success',
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertIn('createdAt', create_response.data)

        list_response = self.client.get('/api/operation-logs/')
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)

        clear_response = self.client.delete('/api/operation-logs/')
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.data['message'], '日志已清空')
        self.assertEqual(self.client.get('/api/operation-logs/').data, [])


class ScheduleContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        for index, title in enumerate(['教授', '副教授', '讲师', '讲师'], start=1):
            Teacher.objects.create(
                name=f'教师{index}',
                college='计算机学院',
                title=title,
                roles=['专家', '秘书'],
                available_types=['预答辩'],
            )
        Room.objects.create(
            campus='创新港',
            name='A101',
            capacity=30,
            available_times='',
        )
        for index in range(1, 4):
            Student.objects.create(
                name=f'学生{index}',
                student_type='学硕',
                mentor_name='教师1',
                campus='创新港',
                defense_types=['预答辩'],
                secretary_name='教师4',
            )

    def test_schedule_generate_current_conflict_check_and_export_use_current_models(self):
        generate_response = self.client.post(
            '/api/schedule/generate/',
            {
                'rules': {
                    'defense_type': 'pre',
                    'start_date': '2025-05-10',
                    'end_date': '2025-05-10',
                    'group_size': 3,
                    'expert_count': 2,
                    'avoid_weekend': False,
                    'avoid_supervisor': False,
                }
            },
            format='json',
        )

        self.assertEqual(generate_response.status_code, 200)
        self.assertEqual(generate_response.data['defenseType'], '预答辩')
        self.assertEqual(generate_response.data['groups'][0]['students'][0]['studentType'], '学硕')
        self.assertEqual(generate_response.data['groups'][0]['students'][0]['mentorName'], '教师1')

        current_response = self.client.get('/api/schedule/current/', {'defense_type': 'pre'})
        self.assertEqual(current_response.status_code, 200)
        self.assertEqual(len(current_response.data['groups']), 1)

        conflicts_response = self.client.post(
            '/api/schedule/check-conflicts/',
            {'defense_type': 'pre'},
            format='json',
        )
        self.assertEqual(conflicts_response.status_code, 200)
        self.assertIsInstance(conflicts_response.data, list)

        export_response = self.client.get('/api/schedule/export/', {'defense_type': 'pre'})
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(
            export_response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
