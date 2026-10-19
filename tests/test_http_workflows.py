"""Exercise the deployed WSGI boundary with isolated local accounts and data."""
import base64
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import app


class BrowserClient:
    def __init__(self, application):
        self.application = application
        self.cookie = ''
        self.csrf = ''

    def request(self, method, url, data=None, *, csrf=True, raw=None, length=None):
        parsed = urlsplit(url)
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else b''
        environ = {'REQUEST_METHOD': method, 'PATH_INFO': parsed.path, 'QUERY_STRING': parsed.query,
                   'REMOTE_ADDR': '127.0.0.1', 'wsgi.input': io.BytesIO(body), 'HTTP_COOKIE': self.cookie}
        if method in ('POST', 'PATCH', 'DELETE'):
            environ.update(CONTENT_TYPE='application/json', CONTENT_LENGTH=str(len(body)) if length is None else length)
            if csrf and self.csrf:
                environ['HTTP_X_CSRF_TOKEN'] = self.csrf
        response = {}
        def start_response(status, headers):
            response.update(status=int(status.split()[0]), headers=dict(headers))
            for key, value in headers:
                if key.lower() == 'set-cookie' and value.startswith(app.COOKIE_NAME + '='):
                    self.cookie = value.split(';', 1)[0]
        payload = b''.join(self.application(environ, start_response))
        if 'application/json' in response['headers'].get('Content-Type', '') and payload:
            payload = json.loads(payload)
            if isinstance(payload, dict) and payload.get('csrf'):
                self.csrf = payload['csrf']
        return response['status'], payload, response['headers']


class HTTPWorkflows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = patch.multiple(app, DB_PATH=str(Path(self.tmp.name) / 'http.sqlite3'),
                                       DATABASE_URL='', MODE='development')
        self.settings.start()
        self.environment = patch.dict(os.environ, {
            'EMAIL_PROVIDER': 'disabled', 'RESEND_API_KEY': '', 'EMAIL_API_KEY': '',
            'PAYMENT_PROVIDER': 'sandbox', 'MARKETPLACE_INTERNAL_TESTING_ENABLED': 'false',
            'DELIVERY_ENCRYPTION_KEY': base64.urlsafe_b64encode(b'0123456789abcdef0123456789abcdef').decode(),
        })
        self.environment.start()
        app.migrate()
        self.db = app.connect()
        self.seller_id, self.admin_id = app.ident(), app.ident()
        for uid, email in ((self.seller_id, 'seller@http.test'), (self.admin_id, 'admin@http.test')):
            self.db.execute('INSERT INTO users(id,email,password_hash,display_name,email_verified) VALUES(?,?,?,?,1)',
                            (uid, email, app.password_hash('HTTP-test-password-123'), email.split('@')[0]))
        self.db.execute("INSERT INTO seller_profiles(user_id,shop_name,verification_status,selling_enabled,identity_status,identity_provider) VALUES(?,'HTTP Test Shop','verified',1,'verified','didit')", (self.seller_id,))
        self.db.execute('INSERT INTO admin_accounts(user_id) VALUES(?)', (self.admin_id,))
        self.application = app.VercelWSGIApplication()
        self.application._startup_complete = True
        self.guest = BrowserClient(self.application)
        self.seller = self.signed_client(self.seller_id)
        self.admin = self.signed_client(self.admin_id)

    def tearDown(self):
        self.db.close()
        self.environment.stop()
        self.settings.stop()
        self.tmp.cleanup()

    def signed_client(self, uid):
        client = BrowserClient(self.application)
        cookie, client.csrf = app.session_create(self.db, uid)
        client.cookie = app.COOKIE_NAME + '=' + cookie
        return client

    def registered_buyer(self):
        client = BrowserClient(self.application)
        status, result, _ = client.request('POST', '/api/register', {
            'name': 'HTTP Buyer', 'email': 'buyer@http.test', 'password': 'HTTP-buyer-password-123',
            'country': 'UZ', 'accept_terms': True})
        self.assertEqual(status, 201, result)
        status, result, headers = client.request('POST', '/api/verify', {'token': result['verification_token']})
        self.assertEqual(status, 200, result)
        self.assertTrue(result['user']['email_verified'])
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Lax', headers['Set-Cookie'])
        return client

    def published_item(self):
        status, result, _ = self.seller.request('POST', '/api/listings', {
            'game_name': 'Counter-Strike 2', 'category_id': 'items', 'title': 'HTTP workflow test item',
            'description': 'An isolated item for a complete local purchase test.', 'price_minor': 45000,
            'stock': 2, 'platform': 'PC', 'region': 'Global', 'delivery_eta': '5 minutes',
            'attributes': {'item_name': 'Test skin', 'item_variant': 'Factory New', 'transfer_method': 'In-game trade'},
            'submit_for_review': True})
        self.assertEqual(status, 201, result)
        lid = result['id']
        status, result, _ = self.admin.request('POST', '/api/admin/listings/' + lid, {'action': 'approve', 'note': 'Local HTTP test review'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['status'], 'published')
        return lid

    def test_complete_item_purchase_messages_delivery_and_review_through_http(self):
        buyer = self.registered_buyer()
        lid = self.published_item()
        status, listing, _ = buyer.request('GET', '/api/listings/' + lid)
        self.assertEqual(status, 200)
        self.assertFalse(listing['is_owner'])
        self.assertNotIn('moderation_note', listing)
        self.db.execute('UPDATE listings SET moderation_note=? WHERE id=?', ('Internal moderator note', lid))
        self.assertNotIn('moderation_note', self.guest.request('GET', '/api/listings/' + lid)[1])
        self.assertEqual(self.seller.request('GET', '/api/listings/' + lid)[1]['moderation_note'], 'Internal moderator note')
        status, _, _ = buyer.request('POST', '/api/favorites/' + lid, {})
        self.assertEqual(status, 200)
        status, favorites, _ = buyer.request('GET', '/api/favorites')
        self.assertEqual((status, favorites[0]['id']), (200, lid))
        status, conversation, _ = buyer.request('POST', '/api/conversations', {'listing_id': lid})
        self.assertEqual(status, 200, conversation)
        cid = conversation['id']
        status, _, _ = buyer.request('POST', f'/api/conversations/{cid}/messages', {'body': 'Is delivery available?'})
        self.assertEqual(status, 200)
        status, messages, _ = self.seller.request('GET', '/api/conversations/' + cid)
        self.assertEqual((status, messages['messages'][0]['body']), (200, 'Is delivery available?'))
        status, _, _ = buyer.request('POST', '/api/cart', {'listing_id': lid, 'quantity': 1})
        self.assertEqual(status, 200)
        status, order, _ = buyer.request('POST', '/api/checkout', {'accept_terms': True})
        self.assertEqual(status, 201, order)
        self.assertEqual(order['mode'], 'sandbox')
        oid = order['id']
        status, payment, _ = buyer.request('POST', f'/api/orders/{oid}/sandbox-complete', {})
        self.assertEqual((status, payment['status']), (200, 'paid'))
        status, order, _ = self.seller.request('GET', '/api/orders/' + oid)
        self.assertEqual(status, 200)
        item = order['items'][0]['id']
        status, result, _ = self.seller.request('POST', f'/api/orders/{oid}/deliver', {'item_id': item, 'delivery': 'Private local test delivery code'})
        self.assertEqual(status, 200, result)
        status, order, _ = buyer.request('GET', '/api/orders/' + oid)
        self.assertEqual(order['items'][0]['delivery']['protected_payload'], 'Private local test delivery code')
        self.assertTrue(self.db.execute('SELECT protected_payload FROM deliveries WHERE order_item_id=?', (item,)).fetchone()['protected_payload'].startswith('enc:v1:'))
        status, result, _ = buyer.request('POST', f'/api/orders/{oid}/complete', {})
        self.assertEqual((status, result['status']), (200, 'completed'))
        status, _, _ = buyer.request('POST', '/api/reviews', {'item_id': item, 'rating': 5, 'body': 'Delivery verified in a local test.'})
        self.assertEqual(status, 201)
        status, listing, _ = self.guest.request('GET', '/api/listings/' + lid)
        self.assertEqual((status, listing['review_count'], listing['seller']['total_sales']), (200, 1, 1))
        self.assertNotIn('Private local test delivery code', json.dumps(listing))
        status, _, _ = self.guest.request('GET', '/api/orders/' + oid)
        self.assertEqual(status, 401)

    def test_session_csrf_admin_and_logout_guards_through_http(self):
        buyer = self.registered_buyer()
        self.assertEqual(buyer.request('POST', '/api/logout', {}, csrf=False)[0], 403)
        self.assertEqual(buyer.request('GET', '/api/admin/users')[0], 403)
        self.assertEqual(self.guest.request('GET', '/api/messages')[0], 404)
        self.assertEqual(self.guest.request('GET', '/api/conversations')[0], 401)
        self.assertEqual(buyer.request('POST', '/api/logout', {})[0], 200)
        self.assertIsNone(buyer.request('GET', '/api/me')[1]['user'])
        self.assertEqual(buyer.request('POST', '/api/login', {'email': 'buyer@http.test', 'password': 'wrong'})[0], 401)
        status, result, _ = buyer.request('POST', '/api/login', {'email': 'buyer@http.test', 'password': 'HTTP-buyer-password-123'})
        self.assertEqual(status, 200, result)
        self.assertTrue(buyer.request('GET', '/api/me')[1]['user']['email_verified'])

    def test_malformed_request_bodies_are_client_errors_not_server_errors(self):
        for raw in (b'[]', b'null', b'false', b'123', b'"text"', b'{invalid', b'\xff'):
            with self.subTest(raw=raw):
                self.assertEqual(self.guest.request('POST', '/api/login', raw=raw)[0], 400)
        for length, expected in (('-1', 400), ('invalid', 400), ('1000', 400), (str(app.MAX_BODY + 1), 413)):
            with self.subTest(length=length):
                self.assertEqual(self.guest.request('POST', '/api/login', raw=b'{}', length=length)[0], expected)
        for password in (None, 123, [], {}):
            status, _, _ = self.guest.request('POST', '/api/register', {'email': 'invalid@http.test', 'name': 'Invalid User', 'password': password, 'accept_terms': True})
            self.assertEqual(status, 400)

    def test_invalid_profile_language_and_boolean_quantity_are_rejected(self):
        buyer = self.registered_buyer()
        for language in ([], {}, None, 123):
            with self.subTest(language=language):
                self.assertEqual(buyer.request('POST', '/api/profile', {'language': language})[0], 400)
        lid = self.published_item()
        self.assertEqual(buyer.request('POST', '/api/cart', {'listing_id': lid, 'quantity': True})[0], 400)

    def test_public_pages_static_assets_and_account_deep_links(self):
        for path in ('/', '/browse', '/blog', '/selling', '/guide', '/fees', '/policies', '/support', '/help/orders', '/help/payments', '/help/refunds', '/help/chat', '/terms', '/refunds', '/seller-policy', '/prohibited-items', '/contact', '/privacy-policy', '/data-deletion', '/top-up', '/robots.txt', '/sitemap.xml', '/healthz'):
            with self.subTest(path=path):
                status, _, _ = self.guest.request('GET', path)
                self.assertEqual(status, 200)
                self.assertEqual(self.guest.request('HEAD', path)[0], 200)
        for route in ('login', 'register', 'password-reset', 'account', 'cart', 'orders', 'seller', 'wallet', 'payout-options', 'my-reviews', 'notifications', 'messages', 'favorites', 'requests', 'compare', 'admin', 'admin-blog', 'top-up-admin', 'order/test-order', 'conversation/test-chat', 'listing-review/test-listing'):
            with self.subTest(route=route):
                status, _, headers = self.guest.request('GET', '/' + route)
                self.assertEqual(status, 302)
                self.assertEqual(headers['Location'], '/#' + route)
        sources = '\n'.join((app.ROOT / 'static' / name).read_text() for name in ('index.html', 'app.js', 'topup.js'))
        urls = set(re.findall(r'''["'](/static/[A-Za-z0-9_./-]+(?:\?[^"']*)?)["']''', sources))
        for path in sorted(urls):
            if Path(urlsplit(path).path).suffix not in ('.js','.css','.svg','.png','.jpg','.webp','.json'): continue
            with self.subTest(asset=path):
                self.assertEqual(self.guest.request('GET', path)[0], 200)
        self.assertEqual(self.guest.request('GET', '/unknown-page')[0], 404)
        self.assertEqual(self.guest.request('GET', '/static/../app.py')[0], 404)


if __name__ == '__main__':
    unittest.main()
