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
            ('/static/storefront-showcase.js', 'application/javascript'),
            ('/static/storefront-showcase.css', 'text/css'),
            ('/static/assets/sentryloot-mark.png', 'image/png'),
            ('/static/assets/sentryloot-mark-256.webp', 'image/webp'),
            ('/static/assets/sentryloot-mark-128.png', 'image/png'),
            ('/static/assets/sentryloot-mark-512.png', 'image/png'),
            ('/static/assets/game-art/pubg-mobile-640.webp', 'image/webp'),
            ('/static/assets/game-art/valorant-3840.webp', 'image/webp'),
            ('/static/assets/game-art/fortnite-640.webp', 'image/webp'),
            ('/static/assets/game-art/dota-2-3840.webp', 'image/webp'),
        ):
            with self.subTest(path=path):
                status, payload, headers = client.request('GET', path)
                self.assertEqual(status, 200)
                self.assertTrue(headers['Content-Type'].startswith(mime))
                self.assertGreater(len(payload), 100)
        for path in ('/static/../app.py', '/static/../.env'):
            self.assertEqual(client.request('GET', path)[0], 404)
        for path in ('/static/assets/game-art/../../app.py', '/static/assets/game-art/sources.json',
                     '/static/assets/game-art/not-a-game-640.webp'):
            self.assertEqual(client.request('GET', path)[0], 404)
