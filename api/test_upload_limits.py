"""Production listener limits, independent of developer server defaults."""
from unittest.mock import patch

from django.test import SimpleTestCase

from defense_scheduler.server import serve_application


class ProductionUploadLimitsTests(SimpleTestCase):
    @patch('waitress.serve')
    def test_listener_accepts_batch_limit_plus_multipart_overhead(self, serve):
        serve_application('127.0.0.1', 12345)
        self.assertEqual(serve.call_args.kwargs['max_request_body_size'], 21 * 1024 * 1024)
        self.assertEqual(serve.call_args.kwargs['host'], '127.0.0.1')
        self.assertEqual(serve.call_args.kwargs['port'], 12345)
