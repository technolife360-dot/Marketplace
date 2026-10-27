"""The deployed WSGI allowlist must serve new UI assets without exposing files."""
import unittest
import app
from test_http_workflows import BrowserClient


class PremiumAssets(unittest.TestCase):
    def test_premium_assets_are_served_with_their_correct_mime_types(self):
        application = app.VercelWSGIApplication()
        application._startup_complete = True
        client = BrowserClient(application)
        for path, mime in (
            ('/static/premium-storefront.css', 'text/css'),
            ('/static/premium-motion.js', 'application/javascript'),
            ('/static/vendor/motion-14.7.1.min.js', 'application/javascript'),
        ):
            with self.subTest(path=path):
                status, payload, headers = client.request('GET', path)
                self.assertEqual(status, 200)
                self.assertTrue(headers['Content-Type'].startswith(mime))
                self.assertGreater(len(payload), 100)
        for path in ('/static/../app.py', '/static/../.env'):
            self.assertEqual(client.request('GET', path)[0], 404)
