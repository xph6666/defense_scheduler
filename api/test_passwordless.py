from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(ALLOWED_HOSTS=['127.0.0.1', 'testserver'])
class LocalPasswordlessTests(TestCase):
    def test_local_access_without_token_and_with_stale_token(self):
        client = APIClient()
        for token in ('', 'Token expired-token'):
            response = client.get('/api/teachers/', HTTP_HOST='127.0.0.1:8000',
                                  HTTP_AUTHORIZATION=token)
            self.assertEqual(response.status_code, 200)

    def test_local_administrator_can_write_without_password(self):
        response = APIClient().post('/api/operation-logs/', {
            'type': '测试', 'module': '测试', 'description': '免密操作验证',
        }, format='json', HTTP_HOST='127.0.0.1:8000')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['operator'], 'local-admin')

    def test_remote_and_cross_site_requests_still_require_authentication(self):
        for headers in (
            {'REMOTE_ADDR': '192.168.1.20', 'HTTP_HOST': '127.0.0.1:8000'},
            {'HTTP_HOST': 'testserver'},
            {'HTTP_HOST': '127.0.0.1:8000', 'HTTP_ORIGIN': 'https://example.com'},
            {'HTTP_HOST': '127.0.0.1:8000', 'HTTP_SEC_FETCH_SITE': 'cross-site'},
        ):
            response = APIClient().get('/api/teachers/', **headers)
            self.assertIn(response.status_code, (401, 403))
