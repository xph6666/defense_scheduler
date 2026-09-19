"""修改密码接口（/api/auth/change-password/）的测试。"""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

CHANGE_URL = '/api/auth/change-password/'
OLD_PASSWORD = 'old-pass-123'
NEW_PASSWORD = 'brand-new-pass-456'


class AuthChangePasswordTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='admin', password=OLD_PASSWORD)

    def _login(self):
        response = self.client.post(
            '/api/auth/login/',
            {'username': 'admin', 'password': OLD_PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        return response.data['token']

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

    def test_change_password_success_rotates_token(self):
        old_token = self._login()
        self._auth(old_token)

        response = self.client.post(
            CHANGE_URL,
            {'oldPassword': OLD_PASSWORD, 'newPassword': NEW_PASSWORD},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        new_token = response.data['token']
        self.assertNotEqual(new_token, old_token)
        # 旧 Token 已作废
        self.assertFalse(Token.objects.filter(key=old_token).exists())

        # 新密码可登录，旧密码不再可用
        self.client.credentials()
        login_new = self.client.post(
            '/api/auth/login/', {'username': 'admin', 'password': NEW_PASSWORD}, format='json',
        )
        self.assertEqual(login_new.status_code, 200)
        login_old = self.client.post(
            '/api/auth/login/', {'username': 'admin', 'password': OLD_PASSWORD}, format='json',
        )
        self.assertEqual(login_old.status_code, 400)

    def test_wrong_old_password_rejected(self):
        self._auth(self._login())

        response = self.client.post(
            CHANGE_URL,
            {'oldPassword': 'wrong-pass', 'newPassword': NEW_PASSWORD},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('原密码不正确', response.data['error'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_weak_new_password_rejected(self):
        self._auth(self._login())

        for weak in ('123', '12345678'):
            response = self.client.post(
                CHANGE_URL,
                {'oldPassword': OLD_PASSWORD, 'newPassword': weak},
                format='json',
            )
            self.assertEqual(response.status_code, 400, weak)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_same_password_rejected(self):
        self._auth(self._login())

        response = self.client.post(
            CHANGE_URL,
            {'oldPassword': OLD_PASSWORD, 'newPassword': OLD_PASSWORD},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_requires_authentication(self):
        response = self.client.post(
            CHANGE_URL,
            {'oldPassword': OLD_PASSWORD, 'newPassword': NEW_PASSWORD},
            format='json',
        )
        self.assertIn(response.status_code, (401, 403))
