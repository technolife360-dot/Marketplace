import base64
import hashlib
import io
import json
import time
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from urllib.parse import parse_qs
from PIL import Image
import app
import marketplace_operations as ops
from tests import test_marketplace as fixtures
from tests import test_http_workflows as http

class OperationsFlows(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx
    def route(self,uid,method,url,data=None):
        path,_,q=url.partition('?')
        self.handler.headers={}
        result=self.handler.route(self.db,self.ctx(uid),method,path,parse_qs(q),data or {})
        return result[1] if isinstance(result,tuple) else result
    def test_rfc6238_vectors(self):
        secret=base64.b32encode(b'12345678901234567890').decode()
        for timestamp,expected in [(59,'94287082'),(1111111109,'07081804'),(1111111111,'14050471'),(1234567890,'89005924'),(2000000000,'69279037'),(20000000000,'65353130')]:
            self.assertEqual(ops.totp(secret,timestamp//30,digits=8),expected)
    def setup_mfa(self):
        result=self.route(self.buyer,'POST','/api/security/mfa/setup',{'password':'unique-test-password'})
        with patch.object(ops.time,'time',return_value=1800000000):
            enabled=self.route(self.buyer,'POST','/api/security/mfa/enable',{'otp':ops.totp(result['secret'],1800000000//30)})
        return result['secret'],enabled['recovery_codes']
    def test_mfa_secrets_encrypted_enrollment_replay_and_recovery_single_use(self):
        secret,codes=self.setup_mfa();row=self.db.execute('SELECT * FROM account_security WHERE user_id=?',(self.buyer,)).fetchone()
        self.assertNotIn(secret,row['secret_cipher']);self.assertTrue(row['secret_cipher'].startswith('enc:v1:'))
        with patch.object(ops.time,'time',return_value=1800000030):
            otp=ops.totp(secret,1800000030//30)
            self.assertTrue(ops.consume_otp(self.db,self.buyer,otp,vars(app)));self.assertFalse(ops.consume_otp(self.db,self.buyer,otp,vars(app)))
        self.assertTrue(ops.consume_otp(self.db,self.buyer,codes[0],vars(app)));self.assertFalse(ops.consume_otp(self.db,self.buyer,codes[0],vars(app)))
        self.assertEqual(len(codes),10)
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/security/password',{'password':'unique-test-password','new_password':'Other-unique-test-password','otp':'bad'})
    def test_mfa_enrollment_requires_password_and_real_code(self):
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/security/mfa/setup',{'password':'bad'})
        self.route(self.buyer,'POST','/api/security/mfa/setup',{'password':'unique-test-password'})
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/security/mfa/enable',{'otp':'not valid'})
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/security/mfa/enable',{'otp':'１２３４５６'})
        self.assertFalse(ops.enabled(self.db,self.buyer))
    def test_mfa_qr_contains_pending_enrollment_and_requires_confirmation(self):
        import qrcode
        original=qrcode.QRCode.add_data
        with patch.object(qrcode.QRCode,'add_data',autospec=True) as add_data:
            # Spy on the exact payload while letting the generator build a real QR.
            add_data.side_effect=lambda qr,data:original(qr,data)
            setup=self.route(self.buyer,'POST','/api/security/mfa/setup',{'password':'unique-test-password'})
        add_data.assert_called_once()
        self.assertEqual(add_data.call_args.args[1],setup['uri'])
        self.assertEqual(parse_qs(setup['uri'].split('?',1)[1])['secret'],[setup['secret']])
        prefix,payload=setup['qr_image'].split(',',1)
        self.assertEqual(prefix,'data:image/png;base64')
        with Image.open(io.BytesIO(base64.b64decode(payload,validate=True))) as image:
            self.assertEqual(image.format,'PNG')
            self.assertEqual(image.width,image.height)
            self.assertGreaterEqual(image.width,240)
            self.assertEqual(image.convert('RGB').getpixel((0,0)),(255,255,255))
            self.assertEqual(image.convert('RGB').getpixel((24,24)),(0,0,0))
        row=self.db.execute('SELECT * FROM account_security WHERE user_id=?',(self.buyer,)).fetchone()
        self.assertFalse(row['enabled'])
        self.assertNotIn(setup['secret'],row['pending_cipher'])
        with patch.object(ops.time,'time',return_value=1800000000):
            result=self.route(self.buyer,'POST','/api/security/mfa/enable',{'otp':ops.totp(setup['secret'],1800000000//30)})
        self.assertTrue(result['enabled'])
    def test_email_changes_are_owned_expire_and_consume_only_once(self):
        r=self.route(self.buyer,'POST','/api/security/email',{'password':'unique-test-password','email':'new-address@test.invalid'})
        token=r['confirmation_token']
        self.assertEqual(self.db.execute('SELECT email FROM users WHERE id=?',(self.buyer,)).fetchone()['email'],'buyer@test.invalid')
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/security/email/confirm',{'token':token})
        self.assertEqual(self.route(self.buyer,'POST','/api/security/email/confirm',{'token':token})['user']['email'],'new-address@test.invalid')
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/security/email/confirm',{'token':token})
    def test_password_change_revokes_all_sessions(self):
        app.session_create(self.db,self.buyer);app.session_create(self.db,self.buyer)
        self.route(self.buyer,'POST','/api/security/password',{'password':'unique-test-password','new_password':'A-new-local-password'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM sessions WHERE user_id=?',(self.buyer,)).fetchone()['n'],0)
        self.assertTrue(app.password_ok('A-new-local-password',self.db.execute('SELECT password_hash FROM users WHERE id=?',(self.buyer,)).fetchone()['password_hash']))
    def test_ticket_privacy_replies_and_resolution(self):
        r=self.route(self.buyer,'POST','/api/support/tickets',{'subject':'Order delivery question','category':'delivery','body':'Please explain delivery information.'});tid=r['id']
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/support/tickets/'+tid)
        self.assertEqual(len(self.route(self.admin,'GET','/api/support/tickets?queue=1')),1)
        self.route(self.admin,'POST','/api/support/tickets/'+tid,{'body':'Please share the order reference.','status':'waiting_customer'})
        self.assertEqual(self.route(self.buyer,'GET','/api/support/tickets/'+tid)['ticket']['status'],'waiting_customer')
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/support/tickets/'+tid,{'body':'Pretend status','status':'waiting_customer'})
        self.route(self.buyer,'POST','/api/support/tickets/'+tid,{'body':'This is resolved now.','status':'resolved'})
        self.assertEqual(self.route(self.admin,'GET','/api/support/tickets/'+tid)['ticket']['status'],'resolved')
    def test_blocking_prevents_new_trade_and_messages_but_preserves_history(self):
        cid=self.route(self.buyer,'POST','/api/conversations',{'listing_id':self.listing})['id']
        self.route(self.buyer,'POST','/api/blocks/'+self.seller)
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/conversations/'+cid+'/messages',{'body':'Cannot send this'})
        self.assertFalse(self.route(self.buyer,'GET','/api/conversations/'+cid)['can_message'])
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/conversations',{'listing_id':self.listing})
        self.route(self.buyer,'DELETE','/api/blocks/'+self.seller)
        self.assertTrue(self.route(self.buyer,'GET','/api/conversations/'+cid)['can_message'])
        self.route(self.buyer,'POST','/api/conversations/'+cid+'/messages',{'body':'Unblocked message'})
    def make_order(self):
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.buyer,self.listing))
        return self.route(self.buyer,'POST','/api/checkout',{'accept_terms':True,'accept_account_risk':True})['id']
    def test_immutable_snapshot_deadline_and_idempotent_server_notices(self):
        self.db.execute("UPDATE listings SET delivery_eta='1 hour',delivery_minutes=60,requirements='Original terms',description='Original product description' WHERE id=?",(self.listing,))
        oid=self.make_order();self.route(self.buyer,'POST','/api/orders/'+oid+'/sandbox-complete',{})
        self.db.execute("UPDATE listings SET delivery_eta='7 days',delivery_minutes=10080,requirements='Changed later',description='Changed product description' WHERE id=?",(self.listing,))
        order=self.route(self.buyer,'GET','/api/orders/'+oid);item=order['items'][0]
        self.assertEqual(item['snapshot']['description'],'Original product description');self.assertEqual(item['delivery_eta'],'1 hour');self.assertEqual(item['requirements'],'Original terms');self.assertFalse(item['snapshot']['legacy'])
        due=ops.utc(item['delivery_due_at']);r=ops.deadline_run(self.db,vars(app),due+timedelta(minutes=1));self.assertEqual(r['notices'],1)
        self.assertEqual(ops.deadline_run(self.db,vars(app),due+timedelta(minutes=2))['notices'],0)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?',(oid,)).fetchone()['status'],'paid')
    def test_blocks_do_not_silence_active_order_disputes(self):
        oid=self.make_order();self.route(self.buyer,'POST','/api/orders/'+oid+'/sandbox-complete',{})
        cid=self.route(self.buyer,'POST','/api/conversations',{'order_id':oid,'seller_id':self.seller})['id']
        self.route(self.seller,'POST','/api/blocks/'+self.buyer)
        self.route(self.buyer,'POST','/api/conversations/'+cid+'/messages',{'body':'Please clarify this active order.'})
        self.assertTrue(self.route(self.buyer,'GET','/api/conversations/'+cid)['can_message'])
    def test_availability_validation_vacation_and_next_open(self):
        data={'timezone':'Asia/Tashkent','vacation':False,'hours':[{'day':0,'start':'09:00','end':'18:00'}]}
        self.route(self.seller,'POST','/api/seller/availability',data)
        moment=datetime(2026,10,19,1,0,tzinfo=timezone.utc) # Monday 06:00 local
        self.assertEqual(ops.next_open(data,moment),datetime(2026,10,19,4,0,tzinfo=timezone.utc))
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/seller/availability',{**data,'hours':[{'day':False,'start':'09:00','end':'18:00'}]})
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/seller/availability',{**data,'timezone':'not-a-zone'})
        self.route(self.seller,'POST','/api/seller/availability',{**data,'vacation':True})
        with self.assertRaises(app.HttpError):self.make_order()
    def test_bulk_update_atomicity_and_authorization(self):
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/seller/listings/bulk-update',{'ids':[self.listing,'other-listing'],'fields':{'price_minor':60000}})
        self.assertEqual(self.db.execute('SELECT price_minor FROM listings WHERE id=?',(self.listing,)).fetchone()['price_minor'],50000)
        result=self.route(self.seller,'POST','/api/seller/listings/bulk-update',{'ids':[self.listing],'fields':{'price_minor':60000,'delivery_eta':'2 hours'}})
        self.assertEqual(result['updated'],1)
        row=self.db.execute('SELECT status,price_minor,delivery_minutes FROM listings WHERE id=?',(self.listing,)).fetchone();self.assertEqual(tuple(row),('pending_review',60000,120))
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/seller/listings/bulk-update',{'ids':[self.listing],'fields':{'stock':1}})
    def test_dispute_open_capability_matches_buyer_role_and_order_stage(self):
        oid=self.make_order()
        for user in (self.buyer,self.seller,self.admin):
            self.assertFalse(self.route(user,'GET','/api/disputes/'+oid)['can_open'])
        self.route(self.buyer,'POST','/api/orders/'+oid+'/sandbox-complete',{})
        self.assertTrue(self.route(self.buyer,'GET','/api/disputes/'+oid)['can_open'])
        for user in (self.seller,self.admin):
            self.assertFalse(self.route(user,'GET','/api/disputes/'+oid)['can_open'])
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/disputes/'+oid)
        self.route(self.buyer,'POST','/api/orders/'+oid+'/dispute',{'details':'The received delivery does not match the listing.'})
        self.assertFalse(self.route(self.buyer,'GET','/api/disputes/'+oid)['can_open'])
        self.assertTrue(self.route(self.buyer,'GET','/api/disputes/'+oid)['can_reply'])
        self.route(self.admin,'POST','/api/admin/disputes/'+oid,{'action':'refund_buyer','note':'Reviewed evidence and approved the refund.'})
        self.assertFalse(self.route(self.buyer,'GET','/api/disputes/'+oid)['can_open'])
        self.assertFalse(self.route(self.buyer,'GET','/api/disputes/'+oid)['can_reply'])

    def test_dispute_case_is_private_and_resolved_records_are_read_only(self):
        oid=self.make_order();self.route(self.buyer,'POST','/api/orders/'+oid+'/sandbox-complete',{})
        self.route(self.buyer,'POST','/api/orders/'+oid+'/dispute',{'details':'This delivery needs a moderator investigation.'})
        self.route(self.seller,'POST','/api/disputes/'+oid,{'body':'Here are the delivery details for review.'})
        r=self.route(self.buyer,'GET','/api/disputes/'+oid)
        self.assertIsNotNone(r['report']['response_due_at']);self.assertEqual(len(r['entries']),1)
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/disputes/'+oid)
        self.route(self.admin,'POST','/api/admin/disputes/'+oid,{'action':'refund_buyer','note':'Local test evidence reviewed.'})
        self.assertFalse(self.route(self.buyer,'GET','/api/disputes/'+oid)['can_reply'])
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/disputes/'+oid,{'body':'Cannot alter closed decision'})
    def test_readiness_only_admin_and_no_fabricated_listing(self):
        count=self.db.execute('SELECT COUNT(*) n FROM listings').fetchone()['n']
        r=self.route(self.admin,'GET','/api/catalog/readiness');self.assertTrue(r['items'][0]['issues'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM listings').fetchone()['n'],count)
        with self.assertRaises(app.HttpError):self.route(self.buyer,'GET','/api/catalog/readiness')

    def test_expired_enrollment_and_email_tokens_are_rejected(self):
        result=self.route(self.buyer,'POST','/api/security/mfa/setup',{'password':'unique-test-password'})
        self.db.execute("UPDATE account_security SET pending_expires='2000-01-01T00:00:00+00:00' WHERE user_id=?",(self.buyer,))
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/security/mfa/enable',{'otp':ops.totp(result['secret'],int(time.time())//30)})
        r=self.route(self.buyer,'POST','/api/security/email',{'password':'unique-test-password','email':'expired@test.invalid'})
        self.db.execute("UPDATE pending_email_changes SET expires_at='2000-01-01T00:00:00+00:00'")
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/security/email/confirm',{'token':r['confirmation_token']})
    def test_production_quality_requires_complete_fields_and_moderator_confirmation(self):
        fixtures.MarketplaceFlows.enable_admin_mfa(self)
        with patch.object(app,'MODE','production'),patch.dict(app.os.environ,{'MARKETPLACE_INTERNAL_TESTING_ENABLED':'false'}):
            with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/listings/'+self.listing,{'action':'approve','quality_confirmed':True})
            self.db.execute("UPDATE listings SET description=?,platform='PC',region='Global',requirements='Delivered to your order.',image_url='https://example.test/fixture.webp',attributes_json=? WHERE id=?",('A clearly described real product with complete delivery instructions and restrictions.',json.dumps({'item_name':'Specific item name'}),self.listing))
            with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/listings/'+self.listing,{'action':'approve'})
            self.assertIn(self.route(self.admin,'POST','/api/admin/listings/'+self.listing,{'action':'approve','quality_confirmed':True})['status'],('approved_private','published'))
    def test_legacy_snapshots_are_marked_and_never_get_invented_deadlines(self):
        oid=self.make_order();self.route(self.buyer,'POST','/api/orders/'+oid+'/sandbox-complete',{})
        self.db.execute("UPDATE order_items SET snapshot_json='{}',delivery_due_at=NULL WHERE order_id=?",(oid,))
        ops.migrate(self.db)
        ops.deadline_setup(self.db,oid)
        row=self.db.execute('SELECT snapshot_json,delivery_due_at FROM order_items WHERE order_id=?',(oid,)).fetchone()
        self.assertTrue(json.loads(row['snapshot_json'])['legacy']);self.assertIsNone(row['delivery_due_at'])
    def test_dispute_photo_authorization_and_owner_moderator_only_storage(self):
        oid=self.make_order();self.route(self.buyer,'POST','/api/orders/'+oid+'/sandbox-complete',{})
        self.route(self.buyer,'POST','/api/orders/'+oid+'/dispute',{'details':'Evidence requires a moderator investigation.'})
        with patch.object(app,'require_private_evidence_bucket'),patch.object(app,'normalize_account_evidence',return_value=b'webp'),patch.object(app.storage_r2,'put_evidence') as put,patch.object(app.storage_r2,'evidence_url',return_value='https://private.test/short-lived'):
            self.handler.headers={'Content-Type':'image/png'}
            with self.assertRaises(app.HttpError):self.handler.route(self.db,self.ctx(self.other),'POST','/api/disputes/'+oid+'/photos',{}, {},b'image')
            put.assert_not_called()
            result=self.handler.route(self.db,self.ctx(self.buyer),'POST','/api/disputes/'+oid+'/photos',{}, {},b'image')
            self.assertEqual(result[0],201)
            put.assert_called_once();key=put.call_args.args[0]
            self.assertNotIn(oid,key);self.assertNotIn(self.buyer,key)
            hidden=self.route(self.seller,'GET','/api/disputes/'+oid)['entries'][0]
            self.assertTrue(hidden['image_private']);self.assertNotIn('image_url',hidden)
            entry=self.route(self.buyer,'GET','/api/disputes/'+oid)['entries'][0]
            self.assertEqual(entry['image_url'],'https://private.test/short-lived');self.assertNotIn('object_path',entry)

class SecurityHTTP(unittest.TestCase):
    setUp=http.HTTPWorkflows.setUp
    tearDown=http.HTTPWorkflows.tearDown
    signed_client=http.HTTPWorkflows.signed_client
    registered_buyer=http.HTTPWorkflows.registered_buyer
    def test_mfa_login_oauth_style_session_gate_and_session_revocation(self):
        buyer=self.registered_buyer();uid=buyer.request('GET','/api/me')[1]['user']['id']
        self.assertEqual(self.guest.request('POST','/api/security/mfa/setup',{'password':'HTTP-buyer-password-123'})[0],401)
        self.assertEqual(buyer.request('POST','/api/security/mfa/setup',{'password':'HTTP-buyer-password-123'},csrf=False)[0],403)
        status,setup,headers=buyer.request('POST','/api/security/mfa/setup',{'password':'HTTP-buyer-password-123'});self.assertEqual(status,200,setup)
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(headers['Pragma'],'no-cache')
        self.assertTrue(setup['qr_image'].startswith('data:image/png;base64,'))
        with patch.object(ops.time,'time',return_value=time.time()):
            otp=ops.totp(setup['secret'],int(time.time())//30)
            status,result,_=buyer.request('POST','/api/security/mfa/enable',{'otp':otp});self.assertEqual(status,200,result)
        code=result['recovery_codes'][0]
        client=http.BrowserClient(self.application)
        status,r,_=client.request('POST','/api/login',{'email':'buyer@http.test','password':'HTTP-buyer-password-123'});self.assertEqual((status,r['mfa_required']),(200,True));self.assertFalse(client.cookie)
        self.assertEqual(client.request('POST','/api/login',{'email':'buyer@http.test','password':'HTTP-buyer-password-123','otp':'wrong'})[0],403)
        self.assertEqual(client.request('POST','/api/login',{'email':'buyer@http.test','password':'HTTP-buyer-password-123','otp':code})[0],200)
        self.assertEqual(client.request('GET','/api/orders')[0],200)
        pending=self.signed_client(uid) # equivalent to OAuth or email-verification first factor
        self.assertTrue(pending.request('GET','/api/me')[1]['mfa_required'])
        self.assertEqual(pending.request('GET','/api/orders')[0],403)
        self.assertEqual(pending.request('POST','/api/security/unlock',{'otp':result['recovery_codes'][1]})[0],200)
        self.assertEqual(pending.request('GET','/api/orders')[0],200)
        status,security,_=pending.request('GET','/api/security');self.assertEqual(status,200)
        self.assertTrue(any(s['current'] for s in security['sessions']))
        self.assertEqual(pending.request('DELETE','/api/security/sessions/others')[0],200)
        self.assertIsNone(client.request('GET','/api/me')[1]['user'])
    def test_new_deep_links_and_private_apis(self):
        for url in ('/account','/support-tickets','/admin-support','/catalog-readiness','/dispute/test-order','/support-ticket/test-case','/security-unlock'):
            self.assertEqual(self.guest.request('GET',url)[0],302,url)
        for url in ('/api/security','/api/support/tickets','/api/disputes/test-order'):
            self.assertEqual(self.guest.request('GET',url)[0],401,url)
        for asset in ('/static/account-operations.js','/static/account-operations.css'):
            self.assertEqual(self.guest.request('GET',asset)[0],200,asset)
