import os
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings

from defense_scheduler.runtime import configure_local_runtime, ensure_initial_admin
from desktop_launcher import select_listen_port, should_open_browser


class FrontendServingTests(SimpleTestCase):
    def test_root_serves_built_frontend_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dist_dir = Path(tmpdir)
            (dist_dir / 'index.html').write_text('<html><body>frontend</body></html>', encoding='utf-8')

            with override_settings(FRONTEND_DIST_DIR=dist_dir):
                response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'frontend')

    def test_assets_are_served_from_built_frontend_dist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dist_dir = Path(tmpdir)
            assets_dir = dist_dir / 'assets'
            assets_dir.mkdir()
            (assets_dir / 'app.js').write_text('console.log("frontend")', encoding='utf-8')

            with override_settings(FRONTEND_DIST_DIR=dist_dir):
                response = self.client.get('/assets/app.js')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'frontend')

    def test_public_favicon_is_served_from_built_frontend_dist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dist_dir = Path(tmpdir)
            (dist_dir / 'favicon.svg').write_text('<svg>frontend</svg>', encoding='utf-8')

            with override_settings(FRONTEND_DIST_DIR=dist_dir):
                response = self.client.get('/favicon.svg')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
        self.assertContains(response, 'frontend')


class LocalRuntimeConfigTests(SimpleTestCase):
    def test_configure_local_runtime_uses_persistent_app_data_directory(self):
        with tempfile.TemporaryDirectory() as app_tmp, tempfile.TemporaryDirectory() as bundle_tmp:
            app_root = Path(app_tmp)
            bundle_root = Path(bundle_tmp)
            (bundle_root / 'dist').mkdir()

            with patch.dict(os.environ, {}, clear=True):
                config = configure_local_runtime(app_root=app_root, bundle_root=bundle_root)

                self.assertEqual(os.environ['DJANGO_DEBUG'], 'false')
                self.assertEqual(os.environ['DJANGO_DB_PATH'], str(app_root / 'app-data' / 'db.sqlite3'))
                self.assertEqual(os.environ['FRONTEND_DIST_DIR'], str(bundle_root / 'dist'))
                self.assertTrue(config.app_data_dir.exists())
                self.assertTrue(config.secret_key_file.exists())
                self.assertEqual(os.environ['DJANGO_SECRET_KEY'], config.secret_key_file.read_text(encoding='utf-8'))

    def test_existing_secret_key_is_reused_across_restarts(self):
        with tempfile.TemporaryDirectory() as app_tmp, tempfile.TemporaryDirectory() as bundle_tmp:
            app_root = Path(app_tmp)
            secret_file = app_root / 'app-data' / 'secret.key'
            secret_file.parent.mkdir()
            secret_file.write_text('existing-secret-key', encoding='utf-8')

            with patch.dict(os.environ, {}, clear=True):
                configure_local_runtime(app_root=app_root, bundle_root=Path(bundle_tmp))

                self.assertEqual(os.environ['DJANGO_SECRET_KEY'], 'existing-secret-key')


class InitialAdminTests(TestCase):
    def test_initial_admin_is_created_when_database_has_no_users(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_data_dir = Path(tmpdir)

            credentials = ensure_initial_admin(app_data_dir)

            self.assertEqual(credentials.username, 'admin')
            self.assertTrue(User.objects.filter(username='admin', is_superuser=True).exists())
            self.assertTrue((app_data_dir / 'INITIAL_ADMIN.txt').exists())
            self.assertIn(credentials.password, (app_data_dir / 'INITIAL_ADMIN.txt').read_text(encoding='utf-8'))

    def test_initial_admin_is_not_created_when_users_already_exist(self):
        User.objects.create_user(username='existing', password='existing-password')

        with tempfile.TemporaryDirectory() as tmpdir:
            credentials = ensure_initial_admin(Path(tmpdir))

            self.assertIsNone(credentials)
            self.assertFalse((Path(tmpdir) / 'INITIAL_ADMIN.txt').exists())
            self.assertFalse(User.objects.filter(username='admin').exists())

class DesktopLauncherTests(SimpleTestCase):
    def test_select_listen_port_falls_back_when_preferred_port_is_busy(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved_socket:
            reserved_socket.bind(('127.0.0.1', 0))
            reserved_socket.listen()
            busy_port = reserved_socket.getsockname()[1]

            selected_port = select_listen_port('127.0.0.1', busy_port)

        self.assertNotEqual(selected_port, busy_port)
        self.assertGreater(selected_port, 0)

    def test_browser_launch_can_be_disabled_for_smoke_tests(self):
        with patch.dict(os.environ, {'DEFENSE_SCHEDULER_OPEN_BROWSER': 'false'}, clear=False):
            self.assertFalse(should_open_browser())

    def test_packaged_entrypoint_reuses_desktop_launcher_main(self):
        from defense_scheduler import desktop_entry
        import desktop_launcher

        self.assertIs(desktop_entry.main, desktop_launcher.main)
