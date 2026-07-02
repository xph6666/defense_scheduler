from django.test import TestCase
from rest_framework.test import APIClient


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
