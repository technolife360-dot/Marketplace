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

    def request(self, method, url, data=None, *, csrf=True, raw=None, length=None, content_type="application/json", headers=None):
        parsed = urlsplit(url)
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else b''
        environ = {'REQUEST_METHOD': method, 'PATH_INFO': parsed.path, 'QUERY_STRING': parsed.query,
                   'REMOTE_ADDR': '127.0.0.1', 'wsgi.input': io.BytesIO(body), 'HTTP_COOKIE': self.cookie}
        if method in ('POST', 'PATCH', 'DELETE'):
            environ.update(CONTENT_TYPE=content_type, CONTENT_LENGTH=str(len(body)) if length is None else length)
            if csrf and self.csrf:
                environ['HTTP_X_CSRF_TOKEN'] = self.csrf
        for key,value in (headers or {}).items():environ['HTTP_'+key.upper().replace('-','_')]=value
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

    def test_login_and_verification_reuse_the_request_database_connection(self):
        original_connect=app.connect
        leased=False
        borrows=0
        class Lease:
            def __init__(self, db): self.db=db
            def execute(self, *args): return self.db.execute(*args)
            def close(self):
                nonlocal leased
                self.db.close()
                leased=False
        def borrow():
            nonlocal leased,borrows
            if leased:
                raise AssertionError('The request cannot borrow a second pooled connection.')
            leased=True
            borrows+=1
            return Lease(original_connect())
        with patch.object(app,'connect',side_effect=borrow):
            buyer=self.registered_buyer()
            self.assertFalse(leased)
            self.assertEqual(buyer.request('POST','/api/logout',{})[0],200)
            status,result,headers=buyer.request('POST','/api/login',{
                'email':'buyer@http.test','password':'HTTP-buyer-password-123'})
            self.assertEqual(status,200,result)
            self.assertIn('HttpOnly',headers['Set-Cookie'])
            self.assertFalse(leased)
            self.assertEqual(borrows,4)
            status,security,_=buyer.request('GET','/api/security')
            self.assertEqual(status,200,security)
            current=next(s for s in security['sessions'] if s['current'])
            self.assertEqual(current['network_label'],'127.0.0.0/24')
            self.assertTrue(current['created_at'])
            self.assertTrue(current['last_seen_at'])

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
        status, order, _ = buyer.request('POST', '/api/checkout', {'accept_terms': True,'buyer_details':{lid:{'player_id':'HTTP-Recipient#42'}}})
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
        status,evidence,_=self.seller.request('POST',f'/api/orders/{oid}/evidence',{'item_id':item,'body':'Transfer completed; reference HTTP-1234.'})
        self.assertEqual(status,201,evidence)
        with patch.object(app,'require_private_evidence_bucket'),patch.object(app,'normalize_account_evidence',return_value=b'webp'),patch.object(app.storage_r2,'put_evidence') as put:
            status,evidence,_=self.seller.request('POST',f'/api/orders/{oid}/evidence?item_id={item}',raw=b'photo',content_type='image/png')
            self.assertEqual(status,201,evidence);put.assert_called_once()
        self.assertEqual(self.guest.request('GET',f'/api/orders/{oid}/workflow')[0],401)
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

    def test_store_follow_discovery_and_private_photo_guards_through_http(self):
        buyer=self.registered_buyer();lid=self.published_item()
        status,listing,_=buyer.request('GET','/api/listings/'+lid)
        sid=listing['store_id']
        self.assertEqual(self.guest.request('GET','/api/stores/'+sid)[0],200)
        self.assertEqual(buyer.request('POST','/api/stores/'+sid+'/follow',{},csrf=False)[0],403)
        self.assertEqual(buyer.request('POST','/api/stores/'+sid+'/follow',{})[0],200)
        self.assertEqual(buyer.request('GET','/api/following')[1][0]['id'],sid)
        self.assertEqual(self.guest.request('GET','/api/listings?delivery=5&seller='+sid)[1]['items'][0]['id'],lid)
        self.assertEqual(self.guest.request('GET','/api/search/suggestions?q=CSGO')[1]['games'][0]['slug'],'counter-strike-2')
        cid=buyer.request('POST','/api/conversations',{'listing_id':lid})[1]['id']
        self.assertEqual(buyer.request('POST','/api/conversations/'+cid+'/photos',raw=b'not-png',content_type='image/png')[0],400)
        self.assertEqual(self.guest.request('POST','/api/conversations/'+cid+'/photos',raw=b'not-png',content_type='image/png')[0],401)
        self.assertEqual(buyer.request('POST','/api/conversations/'+cid+'/photos',raw=b'',length=str(app.MAX_IMAGE_BODY+1),content_type='image/png')[0],413)
        self.assertEqual(self.seller.request('POST','/api/listings/'+lid+'/duplicate',{})[0],201)
        self.assertEqual(self.seller.request('POST','/api/seller/listings/bulk-pause',{'ids':[lid]})[0],200)

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
        sources = '\n'.join((app.ROOT / 'static' / name).read_text() for name in ('index.html', 'app.js', 'topup.js', 'topup-detail.js'))
        urls = set(re.findall(r'''["'](/static/[A-Za-z0-9_./-]+(?:\?[^"']*)?)["']''', sources))
        for path in sorted(urls):
            if Path(urlsplit(path).path).suffix not in ('.js','.css','.svg','.png','.jpg','.webp','.json'): continue
            with self.subTest(asset=path):
                self.assertEqual(self.guest.request('GET', path)[0], 200)
        self.assertEqual(self.guest.request('GET', '/unknown-page')[0], 404)
        self.assertEqual(self.guest.request('GET', '/static/../app.py')[0], 404)


    def test_experience_raw_import_and_store_routes_at_wsgi_boundary(self):
        import csv
        out=io.StringIO();writer=csv.DictWriter(out,fieldnames=['game_name','category_id','title','description','price_minor','stock','item_name'])
        writer.writeheader();writer.writerow({'game_name':'Counter-Strike 2','category_id':'items','title':'HTTP import preview item','description':'A complete listing description for preview boundary validation.','price_minor':'10000','stock':'2','item_name':'Karambit'})
        status,result,_=self.seller.request('POST','/api/seller/import/preview?format=csv',raw=out.getvalue().encode(),content_type='text/csv')
        self.assertEqual(status,200,result);self.assertEqual(len(result['rows']),1)
        self.assertEqual(self.guest.request('POST','/api/seller/import/preview?format=csv',raw=out.getvalue().encode(),content_type='text/csv')[0],401)
        status,body,_=self.guest.request('GET','/store/'+self.seller_id)
        self.assertEqual(status,200);self.assertIn(b'HTTP Test Shop',body)
        self.assertEqual(self.guest.request('GET','/store/not-present')[0],404)
        self.assertEqual(self.guest.request('GET','/games/counter-strike-2/items')[0],200)


    def test_static_compression_preserves_content_and_respects_opt_out(self):
        import gzip
        status,plain,_=self.guest.request('GET','/static/experience.js')
        self.assertEqual(status,200)
        status,encoded,headers=self.guest.request('GET','/static/experience.js',headers={'Accept-Encoding':'gzip, br'})
        self.assertEqual(status,200);self.assertEqual(headers['Content-Encoding'],'gzip')
        self.assertEqual(gzip.decompress(encoded),plain);self.assertLess(len(encoded),len(plain)//2)
        self.assertEqual(headers['Vary'],'Accept-Encoding')
        status,opted_out,headers=self.guest.request('GET','/static/experience.js',headers={'Accept-Encoding':'gzip;q=0, br'})
        self.assertNotIn('Content-Encoding',headers);self.assertEqual(opted_out,plain)


    def test_topup_currency_passes_and_weekly_packs_are_real_catalogue_rows(self):
        status,games,_=self.guest.request('GET','/api/top-up/catalog')
        self.assertEqual(status,200)
        packages=next(game for game in games if game['slug']=='pubg-mobile')['packages']
        self.assertEqual([p['amount'] for p in packages if p['product_kind']=='currency'],[60,325,660,1800,3850,8100])
        self.assertEqual({p['url_slug'] for p in packages if p['product_kind']!='currency'},set(app.TOPUP_NAMED_PACKAGES))
        count=self.db.execute('SELECT COUNT(*) n FROM topup_orders').fetchone()['n']
        for package in packages:
            with self.subTest(package=package['url_slug']):
                path='/top-up/pubg-mobile/'+package['url_slug']
                detail=self.guest.request('GET','/api'+path.replace('/top-up/','/top-up/packages/'))
                self.assertEqual(detail[0],200)
                self.assertEqual(detail[1]['product_name'],package['product_name'])
                self.assertFalse(detail[1]['purchasable']);self.assertFalse(detail[1]['payment_ready'])
                page=self.guest.request('GET',path)
                self.assertEqual(page[0],200)
                self.assertIn(package['product_name'],page[1].decode() if isinstance(page[1],bytes) else page[1])
        admin=self.admin.request('GET','/api/admin/top-up')
        self.assertEqual(admin[0],200)
        self.assertEqual({p['product_name'] for p in admin[1]['packages'] if p.get('product_kind')=='pass'},{'ELITE PASS (LV1-100)','ELITE PASS PLUS (LV1-100)'})
        named=next(p for p in packages if p['product_kind']=='pass')
        self.db.execute('UPDATE topup_packages SET price_minor=125000,stock_on_hand=3 WHERE id=?',(named['id'],))
        refreshed=self.guest.request('GET','/api/top-up/catalog')[1]
        saved=next(p for game in refreshed for p in game['packages'] if p['id']==named['id'])
        self.assertEqual(saved['price_minor'],125000);self.assertTrue(saved['available']);self.assertFalse(saved['purchasable'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM topup_orders').fetchone()['n'],count)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM topup_packages WHERE id=?',(named['id'],)).fetchone()['n'],1)

    def test_sold_out_listing_remains_readable_without_allowing_another_purchase(self):
        lid=self.published_item();buyer=self.registered_buyer()
        self.db.execute("UPDATE listings SET status='sold_out',stock=0,reserved=0 WHERE id=?",(lid,))
        status,item,_=self.guest.request('GET','/api/listings/'+lid)
        self.assertEqual(status,200,item);self.assertEqual(item['status'],'sold_out');self.assertEqual(item['available'],0);self.assertIsNone(item['estimated_delivery_at'])
        self.assertEqual(self.guest.request('GET','/listing/'+lid)[0],200)
        self.assertNotIn(lid,[i['id'] for i in self.guest.request('GET','/api/listings')[1]['items']])
        self.assertEqual(self.guest.request('GET','/api/catalogue/offers/'+lid)[0],200)
        self.assertEqual(buyer.request('POST','/api/cart',{'listing_id':lid,'quantity':1})[0],404)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM carts WHERE listing_id=?',(lid,)).fetchone()['n'],0)
        self.assertEqual(buyer.request('POST','/api/favorites/'+lid,{})[0],200)
        self.assertEqual(buyer.request('POST','/api/collections/recent',{'ids':[lid]})[1]['ids'],[lid])
        with patch.object(app,'listing_allowed_for_production',return_value=False):
            for path in ('/api/listings/'+lid,'/listing/'+lid,'/api/catalogue/offers/'+lid):
                self.assertEqual(self.guest.request('GET',path)[0],404,path)
        for private in ('draft','pending_review','rejected','paused','archived'):
            self.db.execute('UPDATE listings SET status=? WHERE id=?',(private,lid))
            for path in ('/api/listings/'+lid,'/listing/'+lid,'/api/catalogue/offers/'+lid):
                self.assertEqual(self.guest.request('GET',path)[0],404,(private,path))
        self.assertEqual(self.guest.request('GET','/api/listings/actually-missing')[0],404)


if __name__ == '__main__':
    unittest.main()
