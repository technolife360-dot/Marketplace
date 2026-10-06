import tempfile
import unittest
import base64
import os
import runpy
from unittest.mock import patch
from pathlib import Path

import app

class MarketplaceFlows(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_path,self.old_mode,self.old_database_url=app.DB_PATH,app.MODE,app.DATABASE_URL
        self.old_delivery_key=os.environ.get('DELIVERY_ENCRYPTION_KEY')
        self.old_email_env={k:os.environ.get(k) for k in ('EMAIL_PROVIDER','RESEND_API_KEY','EMAIL_API_KEY','EMAIL_FROM')}
        os.environ['EMAIL_PROVIDER']='disabled'
        os.environ['DELIVERY_ENCRYPTION_KEY']=base64.urlsafe_b64encode(b'0123456789abcdef0123456789abcdef').decode('ascii')
        # Marketplace tests own an isolated SQLite database. Never let developer
        # .env or CI secrets redirect them to a live Supabase instance.
        app.DATABASE_URL=''; app.DB_PATH=str(Path(self.tmp.name)/'test.sqlite3'); app.MODE='development'; app.migrate()
        self.db=app.connect()
        self.admin=app.ident(); self.seller=app.ident(); self.buyer=app.ident(); self.other=app.ident()
        for uid,email in ((self.admin,'admin@test.invalid'),(self.seller,'seller@test.invalid'),(self.buyer,'buyer@test.invalid'),(self.other,'other@test.invalid')):
            self.db.execute('INSERT INTO users(id,email,password_hash,display_name,email_verified) VALUES(?,?,?,?,1)',(uid,email,app.password_hash('unique-test-password'),'Test '+email.split('@')[0]))
        self.db.execute('INSERT INTO admin_accounts(user_id) VALUES(?)',(self.admin,))
        self.db.execute("INSERT INTO seller_profiles(user_id,shop_name,verification_status,selling_enabled,identity_status,identity_provider) VALUES(?,?,'verified',1,'verified','didit')",(self.seller,'Seller Shop'))
        self.db.execute("UPDATE platform_config SET value='1000' WHERE key='commission_bps'")
        self.listing=app.ident()
        self.db.execute("INSERT INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,stock,status) VALUES(?,?,?,?,?,?,?,?,?, 'published')",(self.listing,self.seller,'valorant','accounts','Valorant account lvl 50','A test listing with enough descriptive text.','account',50000,1))
        self.handler=app.Handler.__new__(app.Handler); self.handler.client_address=('127.0.0.1',12345)
    def tearDown(self):
        self.db.close();app.DB_PATH,app.MODE,app.DATABASE_URL=self.old_path,self.old_mode,self.old_database_url
        if self.old_delivery_key is None: os.environ.pop('DELIVERY_ENCRYPTION_KEY',None)
        else: os.environ['DELIVERY_ENCRYPTION_KEY']=self.old_delivery_key
        for key,value in self.old_email_env.items():
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value
        self.tmp.cleanup()
    def ctx(self,uid): return {'db':self.db,'uid':uid,'user':app.user_view(self.db,uid),'csrf':'test-csrf'}
    def route(self,uid,method,path,data=None):
        result=self.handler.route(self.db,self.ctx(uid),method,path,{},data or {})
        return result[1] if isinstance(result,tuple) else result
    def add_cart(self,uid,qty=1): self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,?)',(uid,self.listing,qty))
    def test_registration_requires_verified_email_and_creates_session(self):
        with self.assertRaises(app.HttpError): self.route(None,'POST','/api/register',{'email':'no-terms@test.invalid','name':'No Terms','password':'correct horse battery staple','accept_terms':False})
        result=self.route(None,'POST','/api/register',{'email':'new@test.invalid','name':'New User','password':'correct horse battery staple','accept_terms':True})
        self.assertIsNotNone(result['verification_token'])
        verify=self.route(None,'POST','/api/verify',{'token':result['verification_token']})
        self.assertTrue(verify['user']['email_verified']);self.assertTrue(verify['csrf'])
        self.assertTrue(getattr(self.handler,'_set_cookie','').startswith(app.COOKIE_NAME+'='))
    def test_my_reviews_are_private_and_list_only_reviews_written_by_the_user(self):
        self.add_cart(self.buyer); order=app.checkout(self.db,self.buyer,True)
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
        item=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(order['id'],)).fetchone()['id']
        self.route(self.seller,'POST',f"/api/orders/{order['id']}/deliver",{'item_id':item,'delivery':'test delivery'})
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/complete",{})
        self.route(self.buyer,'POST','/api/reviews',{'item_id':item,'rating':5,'body':'Fast and as described.'})
        rows=self.route(self.buyer,'GET','/api/reviews/mine')
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['rating'],rows[0]['listing_title'],rows[0]['seller_name']),(5,'Valorant account lvl 50','Seller Shop'))
        self.assertEqual(self.route(self.other,'GET','/api/reviews/mine'),[])
        with self.assertRaises(app.HttpError): self.route(None,'GET','/api/reviews/mine')
    def test_blog_posts_require_admin_and_only_published_posts_are_public(self):
        post={'slug':'safe-account-buying','status':'draft','category':['XAVFSIZ XARID','БЕЗОПАСНАЯ ПОКУПКА','SAFE BUYING'],
              'title':['Hisobni xavfsiz xarid qilish','Безопасная покупка аккаунта','Buying an account safely'],
              'summary':['Xarid oldidan nimalarni tekshirish kerak.','Что проверить перед покупкой аккаунта.','What to check before buying an account.'],
              'body':[['Platforma va hududni diqqat bilan tekshiring.'],['Проверьте платформу и регион внимательно.'],['Check the platform and region carefully.']]}
        with self.assertRaises(app.HttpError): self.route(self.other,'POST','/api/admin/blog',post)
        with self.assertRaises(app.HttpError): self.route(None,'GET','/api/admin/blog')
        draft=self.route(self.admin,'POST','/api/admin/blog',post)
        self.assertEqual(draft['status'],'draft');self.assertNotIn('safe-account-buying',[p['slug'] for p in self.route(None,'GET','/api/blog')])
        post['status']='published'
        self.route(self.admin,'POST',f"/api/admin/blog/{draft['id']}",post)
        public=self.route(None,'GET','/api/blog')
        created=next(p for p in public if p['slug']=='safe-account-buying')
        self.assertEqual(created['body'][2],['Check the platform and region carefully.'])
        with self.assertRaises(app.HttpError):
            self.route(self.admin,'POST',f"/api/admin/blog/{draft['id']}",{**post,'slug':'not valid'})
    def test_order_status_emails_go_to_the_relevant_party_without_delivery_secret(self):
        self.add_cart(self.buyer); order=app.checkout(self.db,self.buyer,True)
        item=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(order['id'],)).fetchone()['id']
        with patch.object(app.email_service,'is_configured',return_value=True), patch.object(app.email_service,'send_order_update') as send:
            self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
            self.route(self.seller,'POST',f"/api/orders/{order['id']}/deliver",{'item_id':item,'delivery':'Never include this secret'})
            self.route(self.buyer,'POST',f"/api/orders/{order['id']}/complete",{})
        messages=[call.args for call in send.call_args_list]
        self.assertEqual([(x[0],x[3]) for x in messages],[("seller@test.invalid",'paid'),("buyer@test.invalid",'awaiting_delivery'),("seller@test.invalid",'completed')])
        self.assertNotIn('Never include this secret',repr(messages))
    def test_listing_moderation_requires_admin_and_publishes(self):
        draft=self.route(self.seller,'POST','/api/listings',{'game_id':'valorant','category_id':'accounts','title':'New account listing','description':'A sufficiently long listing description.','price_minor':23000,'stock':2})
        self.route(self.seller,'POST',f"/api/listings/{draft['id']}/submit",{})
        with self.assertRaises(app.HttpError): self.route(self.other,'POST',f"/api/admin/listings/{draft['id']}",{'action':'approve'})
        self.route(self.admin,'POST',f"/api/admin/listings/{draft['id']}",{'action':'approve','note':'Checked'})
        self.assertEqual(self.db.execute('SELECT status FROM listings WHERE id=?',(draft['id'],)).fetchone()['status'],'published')
    def test_checkout_reserves_inventory_and_sandbox_webhook_action_is_idempotent(self):
        self.add_cart(self.buyer)
        order=app.checkout(self.db,self.buyer,True)
        stock=self.db.execute('SELECT stock,reserved FROM listings WHERE id=?',(self.listing,)).fetchone()
        self.assertEqual((stock['stock'],stock['reserved']),(1,1))
        terms=self.db.execute('SELECT accepted_checkout_terms_version,accepted_checkout_terms_at FROM orders WHERE id=?',(order['id'],)).fetchone()
        self.assertTrue(terms['accepted_checkout_terms_version']);self.assertTrue(terms['accepted_checkout_terms_at'])
        # A second buyer cannot reserve already-reserved stock.
        self.add_cart(self.other)
        with self.assertRaises(app.HttpError): app.checkout(self.db,self.other,True)
        out=self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
        self.assertEqual(out['status'],'paid')
        again=self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
        self.assertTrue(again['idempotent'])
        stock=self.db.execute('SELECT stock,reserved FROM listings WHERE id=?',(self.listing,)).fetchone()
        self.assertEqual((stock['stock'],stock['reserved']),(0,0))
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM ledger_entries WHERE order_id=?',(order['id'],)).fetchone()['n'],2)
    def test_delivery_visible_to_buyer_after_payment_but_not_other_user_or_seller(self):
        self.add_cart(self.buyer); order=app.checkout(self.db,self.buyer,True)
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
        item=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(order['id'],)).fetchone()['id']
        self.route(self.seller,'POST',f"/api/orders/{order['id']}/deliver",{'item_id':item,'delivery':'One-time delivery code'})
        stored=self.db.execute('SELECT protected_payload FROM deliveries WHERE order_item_id=?',(item,)).fetchone()['protected_payload']
        self.assertTrue(stored.startswith('enc:v1:'))
        self.assertNotIn('One-time delivery code',stored)
        buyer_view=app.order_view(self.db,order['id'],self.buyer)
        self.assertEqual(buyer_view['items'][0]['delivery']['protected_payload'],'One-time delivery code')
        seller_view=app.order_view(self.db,order['id'],self.seller)
        self.assertNotIn('protected_payload',seller_view['items'][0]['delivery'])
        self.assertIsNone(seller_view['buyer_id'])
        with self.assertRaises(app.HttpError): app.order_view(self.db,order['id'],self.other)

    def test_tampered_delivery_ciphertext_is_rejected(self):
        self.add_cart(self.buyer); order=app.checkout(self.db,self.buyer,True)
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
        item=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(order['id'],)).fetchone()['id']
        self.route(self.seller,'POST',f"/api/orders/{order['id']}/deliver",{'item_id':item,'delivery':'test delivery'})
        payload=self.db.execute('SELECT protected_payload FROM deliveries WHERE order_item_id=?',(item,)).fetchone()['protected_payload']
        replacement=payload[:-1]+('A' if payload[-1]!='A' else 'B')
        self.db.execute('UPDATE deliveries SET protected_payload=? WHERE order_item_id=?',(replacement,item))
        with self.assertRaises(app.HttpError) as error: app.order_view(self.db,order['id'],self.buyer)
        self.assertEqual(error.exception.status,503)

    def test_legacy_delivery_migration_encrypts_rows_in_place(self):
        self.add_cart(self.buyer); order=app.checkout(self.db,self.buyer,True)
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
        item=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(order['id'],)).fetchone()['id']
        self.route(self.seller,'POST',f"/api/orders/{order['id']}/deliver",{'item_id':item,'delivery':'temporary'})
        self.db.execute('UPDATE deliveries SET protected_payload=? WHERE order_item_id=?',('legacy account secret',item))
        runpy.run_path(str(Path(app.ROOT)/'scripts/encrypt_delivery_payloads.py'),run_name='__main__')
        stored=self.db.execute('SELECT protected_payload FROM deliveries WHERE order_item_id=?',(item,)).fetchone()['protected_payload']
        self.assertTrue(stored.startswith('enc:v1:'))
        self.assertEqual(app.delivery_crypto.decrypt_payload(stored,item),'legacy account secret')

    def test_production_startup_fails_while_legacy_delivery_rows_remain(self):
        self.add_cart(self.buyer); order=app.checkout(self.db,self.buyer,True)
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
        item=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(order['id'],)).fetchone()['id']
        self.route(self.seller,'POST',f"/api/orders/{order['id']}/deliver",{'item_id':item,'delivery':'temporary'})
        self.db.execute('UPDATE deliveries SET protected_payload=? WHERE order_item_id=?',('legacy account secret',item))
        app.MODE='production'
        try:
            with self.assertRaisesRegex(RuntimeError,'Encrypt existing delivery records'):
                app.main()
        finally:
            app.MODE='development'

    def test_delivery_submission_fails_closed_without_encryption_key(self):
        self.add_cart(self.buyer); order=app.checkout(self.db,self.buyer,True)
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
        item=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(order['id'],)).fetchone()['id']
        os.environ.pop('DELIVERY_ENCRYPTION_KEY',None)
        with self.assertRaises(app.HttpError) as error:
            self.route(self.seller,'POST',f"/api/orders/{order['id']}/deliver",{'item_id':item,'delivery':'test delivery'})
        self.assertEqual(error.exception.status,503)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM deliveries WHERE order_item_id=?',(item,)).fetchone()['n'],0)

    def test_wallet_escrow_release_and_manual_payout_are_distinct_and_idempotent(self):
        self.add_cart(self.buyer)
        order=app.checkout(self.db,self.buyer,True)
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete",{})
        held=self.route(self.seller,'GET','/api/seller/summary')
        self.assertEqual(held['wallet']['held_minor'],45000)
        self.assertEqual(held['wallet']['available_minor'],0)
        with self.assertRaises(app.HttpError):
            self.route(self.seller,'POST','/api/payouts',{'amount_minor':1,'currency':'UZS'})
        item=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(order['id'],)).fetchone()['id']
        self.route(self.seller,'POST',f"/api/orders/{order['id']}/deliver",{'item_id':item,'delivery':'test delivery'})
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/complete",{})
        available=self.route(self.seller,'GET','/api/seller/summary')
        self.assertEqual(available['wallet']['held_minor'],0)
        self.assertEqual(available['wallet']['available_minor'],45000)
        self.assertFalse(available['wallet']['automated_withdrawals_enabled'])
        payout=self.route(self.seller,'POST','/api/payouts',{'amount_minor':45000,'currency':'UZS'})
        self.assertEqual(payout['status'],'pending')
        reserved=self.route(self.seller,'GET','/api/seller/summary')
        self.assertEqual(reserved['wallet']['pending_payout_minor'],45000)
        self.assertEqual(reserved['wallet']['available_minor'],0)
        with self.assertRaises(app.HttpError):
            self.route(self.seller,'POST','/api/payouts',{'amount_minor':1,'currency':'UZS'})
        self.route(self.admin,'POST',f"/api/admin/payouts/{payout['id']}",{'action':'approve'})
        with self.assertRaises(app.HttpError):
            self.route(self.admin,'POST',f"/api/admin/payouts/{payout['id']}",{'action':'mark_paid'})
        paid=self.route(self.admin,'POST',f"/api/admin/payouts/{payout['id']}",{'action':'mark_paid','external_reference':'bank-transfer-123'})
        self.assertEqual(paid['status'],'paid')
        self.assertFalse(paid['funds_transferred'])
        final=self.route(self.seller,'GET','/api/seller/summary')
        self.assertEqual(final['wallet']['paid_out_minor'],45000)
        self.assertEqual(final['wallet']['available_minor'],0)
    def test_server_production_checkout_is_closed_without_provider(self):
        app.MODE='production';self.add_cart(self.buyer)
        with self.assertRaises(app.HttpError) as ctx: app.checkout(self.db,self.buyer,True)
        self.assertEqual(ctx.exception.status,503)

    def test_database_backed_search_finds_published_listing(self):
        result=self.handler.route(self.db,{'db':self.db,'uid':None,'user':None,'csrf':None},'GET','/api/listings',{'q':['Valorant account']},{})
        self.assertTrue(any(x['id']==self.listing for x in result['items']))
    def test_commission_rounding_is_allocated_exactly_across_order_items(self):
        self.db.execute("UPDATE platform_config SET value='1500' WHERE key='commission_bps'")
        self.db.execute('UPDATE listings SET price_minor=3 WHERE id=?',(self.listing,))
        second=app.ident();self.db.execute("INSERT INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,stock,status) VALUES(?,?,?,?,?,?,?,?,?, 'published')",(second,self.seller,'valorant','accounts','Second test account','Another description long enough for schema.','account',4,1))
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.buyer,self.listing));self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.buyer,second))
        order=app.checkout(self.db,self.buyer,True)
        result=self.db.execute('SELECT o.commission_minor,COALESCE(SUM(i.commission_minor),0) line_fees FROM orders o JOIN order_items i ON i.order_id=o.id WHERE o.id=? GROUP BY o.id',(order['id'],)).fetchone()
        self.assertEqual(result['commission_minor'],1);self.assertEqual(result['line_fees'],1)
    def test_password_reset_is_single_use_and_revokes_existing_sessions(self):
        cookie,csrf=app.session_create(self.db,self.buyer)
        raw=app.decode_session(cookie)
        issued=self.route(self.buyer,'POST','/api/password-reset',{'email':'buyer@test.invalid'})
        changed=self.route(self.buyer,'POST','/api/password-reset/confirm',{'token':issued['reset_token'],'password':'another secure password'})
        self.assertIn('yangilandi',changed['message'])
        with self.assertRaises(app.HttpError): self.route(self.buyer,'POST','/api/password-reset/confirm',{'token':issued['reset_token'],'password':'third secure password'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM sessions WHERE token_hash=?',(app.hash_token(raw),)).fetchone()['n'],0)


    def test_wanted_request_replies_are_private_and_requester_can_start_conversation(self):
        request=self.route(self.buyer,'POST','/api/requests',{'game_id':'valorant','category_id':'accounts','title':'Looking for ranked account','description':'Need a ranked account in the Asia region.','budget_minor':100000})
        self.route(self.seller,'POST',f"/api/requests/{request['id']}/respond",{'message':'I can help; please message me for details.'})
        replies=self.handler.route(self.db,self.ctx(self.buyer),'GET',f"/api/requests/{request['id']}/responses",{}, {})
        self.assertEqual(replies[0]['seller_id'],self.seller)
        with self.assertRaises(app.HttpError): self.handler.route(self.db,self.ctx(self.other),'GET',f"/api/requests/{request['id']}/responses",{}, {})
        conv=self.route(self.buyer,'POST','/api/conversations',{'request_id':request['id'],'seller_id':self.seller})
        self.route(self.buyer,'POST',f"/api/conversations/{conv['id']}/messages",{'body':'Hello from the requester'})
        msg=self.db.execute('SELECT body FROM messages WHERE conversation_id=?',(conv['id'],)).fetchone()
        self.assertEqual(msg['body'],'Hello from the requester')

    def test_password_storage_is_salted_and_verifies(self):
        a=app.password_hash('a sufficiently long password');b=app.password_hash('a sufficiently long password')
        self.assertNotEqual(a,b);self.assertTrue(app.password_ok('a sufficiently long password',a));self.assertFalse(app.password_ok('wrong password',a))
        cookie=app.encode_session('session-token');self.assertEqual(app.decode_session(cookie),'session-token');self.assertIsNone(app.decode_session(cookie+'x'))

if __name__=='__main__': unittest.main()
