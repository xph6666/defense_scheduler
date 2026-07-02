import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings


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
