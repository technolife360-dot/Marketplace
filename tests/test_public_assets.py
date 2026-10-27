import io
import unittest
from unittest.mock import patch

import app
import public_assets


class PublicArtworkTests(unittest.TestCase):
    def request(self, path):
        application = app.VercelWSGIApplication()
        application._startup_complete = True
        result = {}
        def start_response(status, headers):
            result['status'] = int(status.split()[0])
            result['headers'] = dict(headers)
        body = b''.join(application({'REQUEST_METHOD': 'GET', 'PATH_INFO': path,
                                     'QUERY_STRING': '', 'REMOTE_ADDR': '127.0.0.1',
                                     'wsgi.input': io.BytesIO()}, start_response))
        return result, body

    def test_legacy_images_work_when_the_original_files_are_absent(self):
        with patch.object(app, 'ROOT', app.Path('/nonexistent-image-free-bundle')):
            for path, asset in public_assets.IMAGE_MANIFEST.items():
                with self.subTest(path=path):
                    response, body = self.request(path)
                    self.assertEqual(response['status'], 308)
                    self.assertEqual(response['headers']['Location'], asset['url'])
                    self.assertEqual(body, b'')

    def test_private_and_foreign_urls_are_not_rewritten(self):
        for value in ('https://private.example/evidence.webp',
                      'https://other.example/static/assets/topup-uc.png',
                      'https://gamestorehub.com.evil.test/static/assets/topup-uc.png',
                      '/static/assets/../secret.png', '/api/orders/abc/evidence',
                      '/static/assets/roboto-variable.ttf'):
            self.assertEqual(public_assets.image_url(value), value)

    def test_api_image_urls_and_cache_versions_are_preserved(self):
        value = {'images': ['/static/assets/topup-uc.png?v=3'], 'stock': 2}
        result = public_assets.rewrite_payload(value)
        self.assertEqual(result['images'][0], public_assets.SITE_ASSET_BASE + 'topup-uc.png?v=3')
        self.assertEqual(result['stock'], 2)
        self.assertEqual(value['images'][0], '/static/assets/topup-uc.png?v=3')

    def test_html_uses_new_local_brand_mark_and_font_stays_local(self):
        response, body = self.request('/')
        self.assertEqual(response['status'], 200)
        self.assertIn(b'/static/assets/sentryloot-mark-256.webp?v=1', body)
        self.assertIn(b'/static/assets/sentryloot-mark-128.png?v=1', body)
        self.assertNotIn(b'/static/assets/sentryloot-logo-crest.jpg', body)
        response, body = self.request('/static/assets/roboto-variable.ttf')
        self.assertEqual(response['status'], 200)
        self.assertTrue(body)

    def test_compressed_font_is_preloaded_and_served_as_woff2(self):
        response, page = self.request('/')
        self.assertEqual(response['status'], 200)
        self.assertIn(b'href="/static/assets/roboto-variable.woff2" as="font" type="font/woff2" crossorigin', page)
        response, body = self.request('/static/assets/roboto-variable.woff2')
        self.assertEqual(response['status'], 200)
        self.assertEqual(response['headers']['Content-Type'], 'font/woff2')
        self.assertTrue(response['headers']['Cache-Control'].startswith('public,'))
        self.assertTrue(body.startswith(b'wOF2'))
