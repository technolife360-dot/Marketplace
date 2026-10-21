"""Adversarial role/object tests against the same WSGI boundary used in production."""
import json
import unittest
from unittest.mock import patch

import app
import launch_readiness
from tests import test_marketplace as fixtures
from tests.test_http_workflows import BrowserClient


class AuthorizationBoundaries(unittest.TestCase):
    setUp = fixtures.MarketplaceFlows.setUp
    tearDown = fixtures.MarketplaceFlows.tearDown
    ctx = fixtures.MarketplaceFlows.ctx
    route = fixtures.MarketplaceFlows.route

    def client(self, uid=None):
        application = app.VercelWSGIApplication()
        application._startup_complete = True
        client = BrowserClient(application)
        if uid:
            cookie, client.csrf = app.session_create(self.db, uid)
            client.cookie = app.COOKIE_NAME + '=' + cookie
        return client

    def order(self, multi=False):
        if multi:
            self.db.execute("INSERT INTO seller_profiles(user_id,shop_name,verification_status,selling_enabled,identity_status,identity_provider) VALUES(?,'Other shop','verified',1,'verified','didit')", (self.other,))
            self.db.execute("INSERT INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,stock,status,seller_account_terms_version) VALUES('second-private-line',?,'valorant','accounts','Second seller account','A separate sellers account description.','account',80000,1,'published',?)", (self.other,app.ACCOUNT_SELLER_TERMS_VERSION))
            self.db.execute("INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,'second-private-line',1)", (self.buyer,))
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)', (self.buyer,self.listing))
        order = app.checkout(self.db,self.buyer,True,True)
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete")
        return order['id']

    def test_admin_workflow_does_not_decrypt_customer_delivery_secrets(self):
        oid=self.order()
        iid=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(oid,)).fetchone()['id']
        secret='Customer-only login secret: test-private-value'
        self.route(self.seller,'POST',f'/api/orders/{oid}/deliver',{'item_id':iid,'delivery':secret})
        for uid in (self.buyer,self.seller):
            status,result,_=self.client(uid).request('GET',f'/api/orders/{oid}/workflow')
            self.assertEqual(status,200,result)
            self.assertIn(secret,json.dumps(result))
        with patch.object(app.delivery_crypto,'decrypt_payload',side_effect=AssertionError('Admin must not decrypt delivery secrets')):
            status,result,_=self.client(self.admin).request('GET',f'/api/orders/{oid}/workflow')
        self.assertEqual(status,200,result)
        self.assertNotIn(secret,json.dumps(result))
        self.assertEqual(result['items'][0]['batches'][0]['body'],'')

    def test_multi_seller_order_hides_other_seller_lines_and_full_payment_amount(self):
        oid=self.order(multi=True)
        buyer=self.client(self.buyer).request('GET',f'/api/orders/{oid}')[1]
        self.assertEqual(len(buyer['items']),2)
        for uid,expected in ((self.seller,50000),(self.other,80000)):
            status,result,_=self.client(uid).request('GET',f'/api/orders/{oid}')
            self.assertEqual(status,200,result)
            self.assertEqual(len(result['items']),1)
            self.assertEqual(result['total_minor'],expected)
            self.assertNotIn('amount_minor',result['payment'])
            self.assertIsNone(result['buyer_id'])

    def test_delegated_moderator_cannot_approve_their_own_listing(self):
        launch_readiness.put_config(self.db,'staff_capabilities:'+self.seller,['moderation'])
        self.db.execute("UPDATE listings SET status='pending_review' WHERE id=?",(self.listing,))
        status,result,_=self.client(self.seller).request('POST','/api/admin/listings/'+self.listing,{'action':'approve'})
        self.assertEqual(status,403,result)
        self.assertEqual(self.db.execute('SELECT status FROM listings WHERE id=?',(self.listing,)).fetchone()['status'],'pending_review')
        self.assertEqual(self.client(self.admin).request('POST','/api/admin/listings/'+self.listing,{'action':'approve'})[0],200)

    def test_admin_routes_deny_guests_and_non_admins_before_any_module_runs(self):
        paths=('/api/admin','/api/admin/overview','/api/admin/listings','/api/admin/listings/unknown',
               '/api/admin/top-up','/api/admin/top-up/packages','/api/admin/top-up/packages/unknown',
               '/api/admin/top-up/presentation/unknown','/api/admin/top-up/supplier/check',
               '/api/admin/users','/api/admin/users/unknown','/api/admin/sellers','/api/admin/sellers/unknown',
               '/api/admin/orders','/api/admin/disputes','/api/admin/disputes/unknown',
               '/api/admin/account-reviews','/api/admin/account-reviews/unknown','/api/admin/payouts',
               '/api/admin/payouts/unknown','/api/admin/deletions','/api/admin/deletions/unknown',
               '/api/admin/config','/api/admin/blog','/api/admin/blog/unknown','/api/admin/reports',
               '/api/admin/reports/unknown','/api/admin/staff/unknown','/api/admin/status',
               '/api/admin/launch/profile','/api/admin/operations/cron-runs','/api/admin/future-route')
        with patch.object(app.launch_readiness,'route',side_effect=AssertionError('must deny before module dispatch')):
            for uid,expected in ((None,401),(self.buyer,403),(self.seller,403)):
                client=self.client(uid)
                for path in paths:
                    for method in ('GET','POST','PATCH','DELETE'):
                        with self.subTest(uid=uid,path=path,method=method):
                            status,body,_=client.request(method,path,{} if method!='GET' else None)
                            self.assertEqual(status,expected,body)

    def test_staff_permissions_are_live_scoped_and_cannot_be_spoofed_in_json(self):
        staff=self.client(self.other)
        for capability,path in (('moderation','/api/admin/listings?summary=1'),('content','/api/admin/blog'),('support','/api/support/tickets?queue=1')):
            launch_readiness.put_config(self.db,'staff_capabilities:'+self.other,[capability])
            self.assertEqual(staff.request('GET',path)[0],200,path)
            for private in ('/api/admin/users','/api/admin/orders','/api/admin/payouts','/api/admin/launch/profile','/api/admin/blog-private','/api/admin/blog/internal/keys'):
                self.assertEqual(staff.request('GET',private)[0],403,private)
            status,body,_=staff.request('POST','/api/admin/staff/'+self.buyer,{
                'capabilities':['moderation','content','support'],'required_capability':capability,
                '_admin_scope_checked':[self.other,None],'is_admin':True})
            self.assertEqual(status,403,body)
            launch_readiness.put_config(self.db,'staff_capabilities:'+self.other,[])
            self.assertEqual(staff.request('GET',path)[0],403 if capability!='support' else 200)
        # A successful moderation check must not authorize a nested finance route.
        launch_readiness.put_config(self.db,'staff_capabilities:'+self.other,['moderation'])
        context=self.ctx(self.other);context['required_capability']='moderation'
        app.require_admin(context)
        with self.assertRaises(app.HttpError):self.handler.route(self.db,context,'GET','/api/admin/users',{}, {})

    def test_revoked_unverified_suspended_and_tampered_admin_sessions_are_denied(self):
        admin=self.client(self.admin)
        self.assertEqual(admin.request('GET','/api/admin/overview')[0],200)
        self.db.execute('UPDATE users SET suspended=1 WHERE id=?',(self.admin,))
        self.assertEqual(admin.request('GET','/api/admin/overview')[0],403)
        self.db.execute('UPDATE users SET suspended=0,email_verified=0 WHERE id=?',(self.admin,))
        self.assertEqual(admin.request('GET','/api/admin/overview')[0],403)
        self.db.execute('UPDATE users SET email_verified=1 WHERE id=?',(self.admin,))
        self.db.execute('DELETE FROM admin_accounts WHERE user_id=?',(self.admin,))
        self.assertEqual(admin.request('GET','/api/admin/overview')[0],403)
        guest=self.client();self.assertEqual(guest.request('GET','/api/admin/overview',headers={'X-User-Id':self.admin,'X-Admin':'true'})[0],401)
        admin.cookie=admin.cookie[:-1]+('a' if admin.cookie[-1]!='a' else 'b')
        self.assertEqual(admin.request('GET','/api/admin/overview')[0],401)

    def test_pending_second_factor_cannot_reach_admin_or_private_objects(self):
        admin=self.client(self.admin)
        self.db.execute("INSERT INTO account_security(user_id,enabled) VALUES(?,1)",(self.admin,))
        self.db.execute('UPDATE sessions SET mfa_verified=0 WHERE user_id=?',(self.admin,))
        self.assertTrue(admin.request('GET','/api/me')[1]['mfa_required'])
        for path in ('/api/admin/overview','/api/admin/top-up','/api/orders','/api/conversations','/api/security'):
            self.assertEqual(admin.request('GET',path)[0],403,path)
        context={**self.ctx(self.admin),'mfa_pending':True}
        with self.assertRaises(app.HttpError):self.handler.route(self.db,context,'GET','/api/admin/overview',{}, {})
        self.assertEqual(admin.request('POST','/api/logout',{})[0],200)

    def test_private_chat_files_are_signed_only_after_participant_authorization(self):
        oid=self.order();buyer=self.client(self.buyer);seller=self.client(self.seller)
        status,result,_=buyer.request('POST','/api/conversations',{'order_id':oid,'seller_id':self.seller})
        self.assertEqual(status,200,result);cid=result['id'];mid=app.ident()
        self.db.execute('INSERT INTO messages(id,conversation_id,sender_id,body) VALUES(?,?,?,?)',(mid,cid,self.seller,'Private test chat message'))
        self.db.execute('INSERT INTO message_attachments(message_id,conversation_id,owner_id,object_path) VALUES(?,?,?,?)',(mid,cid,self.seller,'a'*24+'/'+'b'*48+'.webp'))
        with patch.object(app.storage_r2,'evidence_url',return_value='https://private.example.test/short-lived') as sign:
            for client in (buyer,seller):
                status,result,headers=client.request('GET','/api/conversations/'+cid)
                self.assertEqual(status,200,result)
                self.assertEqual(result['messages'][0]['image_url'],'https://private.example.test/short-lived')
                self.assertEqual(headers['Cache-Control'],'no-store')
            sign.reset_mock()
            for uid,expected in ((None,401),(self.other,404),(self.admin,404)):
                client=self.client(uid)
                for method,path,data in (('GET','/api/conversations/'+cid,None),('POST','/api/conversations/'+cid+'/messages',{'body':'Foreign message'})):
                    status,result,_=client.request(method,path,data)
                    self.assertEqual(status,expected,result)
                self.assertEqual(client.request('POST','/api/conversations/'+cid+'/photos',raw=b'invalid-image',content_type='image/png')[0],expected)
            sign.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM messages WHERE conversation_id=?',(cid,)).fetchone()['n'],1)

    def test_foreign_order_files_and_lines_are_not_signed_or_mutated(self):
        oid=self.order(multi=True)
        second=self.db.execute('SELECT id FROM order_items WHERE order_id=? AND seller_id=?',(oid,self.other)).fetchone()['id']
        self.db.execute('INSERT INTO order_artifacts(id,order_id,order_item_id,owner_id,body,object_path) VALUES(?,?,?,?,?,?)',('private-second-artifact',oid,second,self.buyer,'Private second seller evidence','a'*24+'/'+'c'*48+'.webp'))
        with patch.object(app.storage_r2,'evidence_url',return_value='https://private.example.test/second') as sign:
            status,result,_=self.client(self.seller).request('GET',f'/api/orders/{oid}/workflow')
            self.assertEqual(status,200,result);self.assertEqual(result['artifacts'],[]);sign.assert_not_called()
            self.assertEqual(self.client(self.admin).request('GET',f'/api/orders/{oid}/workflow')[0],200)
            sign.assert_called_once();sign.reset_mock()
            stranger=app.ident();self.db.execute('INSERT INTO users(id,email,password_hash,display_name,email_verified) VALUES(?,?,?,?,1)',(stranger,'stranger@auth.test','not-a-password','Stranger'))
            outsider=self.client(stranger)
            for path in (f'/api/orders/{oid}',f'/api/orders/{oid}/workflow',f'/api/disputes/{oid}'):
                self.assertEqual(outsider.request('GET',path)[0],404,path)
            self.assertEqual(outsider.request('POST',f'/api/orders/{oid}/evidence',{'item_id':second,'body':'Cannot attach this evidence'})[0],404)
            sign.assert_not_called()
        status,result,_=self.client(self.seller).request('POST',f'/api/orders/{oid}/deliver',{'item_id':second,'delivery':'Wrong seller attempted delivery'})
        self.assertEqual(status,403,result)
        self.assertEqual(self.db.execute('SELECT delivered_quantity FROM order_items WHERE id=?',(second,)).fetchone()['delivered_quantity'],0)

    def test_seller_cannot_edit_or_bulk_mutate_foreign_listings(self):
        self.db.execute("INSERT INTO seller_profiles(user_id,shop_name,verification_status,selling_enabled,identity_status,identity_provider) VALUES(?,'Other shop','verified',1,'verified','didit')",(self.other,))
        client=self.client(self.other)
        for method,path,body in (
            ('PATCH','/api/listings/'+self.listing,{'title':'Attacker changed title','seller_id':self.other}),
            ('POST','/api/listings/'+self.listing+'/state',{'action':'pause'}),
            ('POST','/api/listings/'+self.listing+'/duplicate',{}),
            ('POST','/api/seller/listings/bulk-pause',{'ids':[self.listing]}),
            ('POST','/api/seller/listings/bulk-update',{'ids':[self.listing],'fields':{'price_minor':1}}),
            ('POST','/api/seller/listings/'+self.listing+'/codes',{'codes':['FOREIGN-CODE']})):
            with self.subTest(path=path):self.assertIn(client.request(method,path,body)[0],(403,404))
        row=self.db.execute('SELECT title,status,price_minor FROM listings WHERE id=?',(self.listing,)).fetchone()
        self.assertEqual(tuple(row),('Valorant account lvl 50','published',50000))
        self.db.execute("UPDATE listings SET status='draft' WHERE id=?",(self.listing,))
        self.assertEqual(client.request('GET','/api/listings/'+self.listing)[0],404)
        self.assertEqual(self.client(self.seller).request('GET','/api/listings/'+self.listing)[0],200)
        self.assertEqual(self.client(self.admin).request('GET','/api/listings/'+self.listing)[0],200)

    def test_financial_review_requires_an_admin_who_is_not_a_party(self):
        oid=self.order();self.db.execute('INSERT INTO admin_accounts(user_id) VALUES(?)',(self.buyer,))
        buyer=self.client(self.buyer)
        self.assertEqual(buyer.request('POST',f'/api/orders/{oid}/dispute',{'details':'A test dispute requiring an independent reviewer.'})[0],200)
        status,result,_=buyer.request('POST',f'/api/admin/disputes/{oid}',{'action':'request_info','note':'I cannot decide my own dispute.'})
        self.assertEqual(status,403,result)
        self.assertEqual(self.db.execute("SELECT status FROM reports WHERE order_id=? AND reason='order_dispute'",(oid,)).fetchone()['status'],'open')
        self.assertEqual(self.client(self.admin).request('POST',f'/api/admin/disputes/{oid}',{'action':'request_info','note':'Independent moderator requests further evidence.'})[0],200)
        self.db.execute("UPDATE orders SET status='under_review' WHERE id=?",(oid,))
        self.db.execute("INSERT INTO account_reviews(order_id,buyer_id,status) VALUES(?,?,'pending')",(oid,self.buyer))
        with patch.object(app,'require_private_evidence_bucket') as bucket:
            self.assertEqual(buyer.request('POST',f'/api/admin/account-reviews/{oid}',{'action':'approve','note':'Cannot approve my own account purchase.'})[0],403)
            bucket.assert_not_called()
        self.db.execute("INSERT INTO payout_requests(id,seller_id,amount_minor,currency) VALUES('self-payout',?,100,'UZS')",(self.admin,))
        self.assertEqual(self.client(self.admin).request('POST','/api/admin/payouts/self-payout',{'action':'approve'})[0],403)
        self.assertEqual(self.db.execute("SELECT status FROM payout_requests WHERE id='self-payout'").fetchone()['status'],'pending')
        self.assertEqual(buyer.request('POST','/api/admin/payouts/self-payout',{'action':'approve'})[0],200)

    def test_private_mutations_require_csrf_even_for_admins(self):
        admin=self.client(self.admin)
        for method,path,body in (('POST','/api/admin/config',{'commission_bps':200}),('POST','/api/admin/status',{'status':'operational'}),('PATCH','/api/admin/top-up/packages/pubg-mobile-60-uc',{'enabled':False})):
            with self.subTest(path=path):self.assertEqual(admin.request(method,path,body,csrf=False)[0],403)
        self.assertEqual(self.db.execute("SELECT value FROM platform_config WHERE key='commission_bps'").fetchone()['value'],'1000')

    def test_support_tickets_and_order_cases_are_not_visible_to_other_customers(self):
        oid=self.order();buyer=self.client(self.buyer);outsider=self.client(self.other)
        status,result,_=buyer.request('POST','/api/support/tickets',{'subject':'Private buyer support case','body':'Private buyer details for support staff only.','order_id':oid})
        self.assertEqual(status,201,result);tid=result['id']
        self.assertEqual(outsider.request('GET','/api/support/tickets/'+tid)[0],404)
        self.assertEqual(outsider.request('POST','/api/support/tickets/'+tid,{'body':'Unauthorized reply'})[0],404)
        self.assertEqual(outsider.request('POST','/api/support/tickets',{'subject':'Foreign linked order','body':'Cannot link an unrelated order to this ticket.','order_id':oid})[0],404)
        launch_readiness.put_config(self.db,'staff_capabilities:'+self.other,['support'])
        self.assertEqual(outsider.request('GET','/api/support/tickets/'+tid)[0],200)
        launch_readiness.put_config(self.db,'staff_capabilities:'+self.other,[])
        self.assertEqual(outsider.request('GET','/api/support/tickets/'+tid)[0],404)
        self.assertEqual(outsider.request('GET','/api/support/tickets?queue=1')[1],[])
        cid='authorization-private-case'
        self.db.execute("INSERT INTO order_cases(id,order_id,requester_id,kind,source_id,reason,details,response_due_at) VALUES(?,?,?,'after_sale','','account_reclaimed','Private customer evidence','2099-01-01T00:00:00+00:00')",(cid,oid,self.buyer))
        for uid in (self.buyer,self.seller,self.admin):self.assertEqual(self.client(uid).request('GET','/api/order-cases/'+cid)[0],200)
        self.assertEqual(outsider.request('GET','/api/order-cases/'+cid)[0],404)
        self.assertEqual(outsider.request('POST','/api/order-cases/'+cid,{'body':'Unauthorized case reply'})[0],404)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM order_case_entries WHERE case_id=?',(cid,)).fetchone()['n'],0)

    def test_static_file_routes_never_expose_server_code_databases_or_secrets(self):
        guest=self.client()
        for path in ('/app.py','/marketplace.sqlite3','/.env','/.git/config','/static/../app.py','/static/%2e%2e/.env','/static/../../marketplace.sqlite3','/static/tests/test_authorization.py'):
            with self.subTest(path=path):self.assertEqual(guest.request('GET',path)[0],404)
