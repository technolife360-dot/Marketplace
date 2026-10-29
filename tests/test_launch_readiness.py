import json
import unittest
from unittest.mock import patch
import app
import launch_readiness as launch
from tests import test_marketplace as fixtures

class LaunchFlows(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx
    route=fixtures.MarketplaceFlows.route

    def profile(self):
        return {'business_name':'Example operator','public_email':'support@example.invalid','public_address':'Public business address','support_owner':'Support manager','support_hours':'Mon–Fri 09:00–18:00','timezone':'Asia/Tashkent','response_target':'Within one business day','protection_scope':'Products not delivered or not as described','protection_exclusions':'Problems outside the agreed coverage','published':True}

    def test_catalogue_readiness_explains_launch_dependencies_without_claiming_live_sales(self):
        with patch.dict(app.os.environ, {'SEAGM_UID':'private-fixture-uid','SEAGM_SECRET_KEY':'private-fixture-secret'}):
            result=self.route(self.admin,'GET','/api/catalog/readiness')
        readiness=result['launch']
        self.assertFalse(readiness['live_sales'])
        self.assertEqual(readiness['payments']['verification'],'not_checked')
        self.assertEqual(readiness['payments']['state'],'local_sandbox')
        self.assertEqual(readiness['business']['state'],'needs_details')
        self.assertIn('support_hours',readiness['business']['missing'])
        self.assertEqual(readiness['topup']['state'],'needs_supplier')
        self.assertTrue(readiness['topup']['credentials_present'])
        self.assertFalse(readiness['topup']['delivery_verified'])
        self.assertGreater(readiness['topup']['unpriced'],0)
        self.assertNotIn('private-fixture',json.dumps(result))
        for uid in (self.buyer,self.seller,None):
            with self.assertRaises(app.HttpError):self.route(uid,'GET','/api/catalog/readiness')

    def test_published_business_profile_does_not_open_sales_or_verify_a_supplier(self):
        self.route(self.admin,'POST','/api/admin/launch/profile',self.profile())
        self.db.execute("UPDATE topup_packages SET price_minor=10000,supplier_type_id='123',supplier_enabled=1")
        result=self.route(self.admin,'GET','/api/catalog/readiness')['launch']
        self.assertEqual(result['business']['state'],'published')
        self.assertFalse(result['live_sales'])
        self.assertEqual(result['topup']['unpriced'],0)
        self.assertEqual(result['topup']['state'],'needs_supplier')
        self.assertFalse(result['topup']['delivery_verified'])

    def test_business_drafts_are_private_and_publish_requires_real_fields(self):
        self.route(self.admin,'POST','/api/admin/launch/profile',{'business_name':'Draft','published':False})
        self.assertEqual(self.route(self.buyer,'GET','/api/launch/profile'),{'published':False})
        with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/launch/profile',{'published':True})
        with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/launch/profile',{**self.profile(),'timezone':'Invalid/Zone'})
        self.route(self.admin,'POST','/api/admin/launch/profile',self.profile())
        self.assertEqual(self.route(self.buyer,'GET','/api/launch/profile')['business_name'],'Example operator')
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/admin/launch/profile',self.profile())

    def test_status_never_invents_uptime_or_enables_payment(self):
        self.assertEqual(self.route(self.buyer,'GET','/api/status')['status'],'not_reported')
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/admin/status',{'status':'operational'})
        with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/status',{'status':'degraded','message':''})
        self.route(self.admin,'POST','/api/admin/status',{'status':'maintenance','message':'Updating the catalogue today.'})
        status=self.route(self.buyer,'GET','/api/status')
        self.assertEqual(status['status'],'maintenance');self.assertFalse(status['live_payments']);self.assertFalse(status['automatic_topup'])

    def test_topup_saved_and_alert_preferences_are_account_scoped_and_idempotent(self):
        package='pubg-mobile-60-uc'
        self.route(self.buyer,'POST','/api/experience/settings',{'email':True})
        for _ in range(2):self.route(self.buyer,'POST','/api/top-up/preferences',{'package_id':package,'kind':'saved','enabled':True})
        self.assertEqual(self.route(self.buyer,'GET','/api/top-up/preferences')['saved'],[package])
        self.assertEqual(self.route(self.other,'GET','/api/top-up/preferences')['saved'],[])
        self.assertTrue(self.route(self.buyer,'GET','/api/experience/settings')['email'])
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/top-up/preferences',{'package_id':package,'kind':'launch_alert','enabled':True})
        self.route(self.buyer,'POST','/api/top-up/preferences',{'package_id':package,'kind':'launch_alert','enabled':True,'consent':True})
        self.assertEqual(self.route(self.buyer,'GET','/api/top-up/preferences')['launch_alert'],[package])
        self.route(self.buyer,'POST','/api/top-up/preferences',{'package_id':package,'kind':'saved','enabled':False})
        self.assertEqual(self.route(self.buyer,'GET','/api/top-up/preferences')['saved'],[])
        self.assertEqual(self.route(self.buyer,'GET','/api/top-up/preferences')['launch_alert'],[package])

    def test_package_editor_has_single_public_source_and_rejects_unsafe_assets(self):
        package='pubg-mobile-weekly-deal-pack-2'
        body={'product_name':'Weekly Deal Pack 2','image_url':'/static/assets/topup-weekly-deal-2.png','contents':[['Premium',2],['Classic',4],['Supply',6],['UC',60]]}
        self.route(self.admin,'POST','/api/admin/top-up/presentation/'+package,body)
        public=self.route(self.buyer,'GET','/api/top-up/packages/pubg-mobile/weekly-deal-pack-2')
        self.assertEqual(public['contents'],body['contents']);self.assertEqual(public['image_url'],body['image_url']);self.assertFalse(public['purchasable'])
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/admin/top-up/presentation/'+package,body)
        with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/top-up/presentation/'+package,{**body,'image_url':'javascript:bad'})
        with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/top-up/presentation/'+package,{**body,'contents':[['UC',True]]})

    def test_test_audience_hides_public_detail_but_keeps_owner_access(self):
        self.route(self.admin,'POST','/api/admin/listings/'+self.listing+'/audience',{'audience':'test'})
        with patch.object(app,'MODE','production'),patch.object(app,'listing_allowed_for_production',return_value=True):
            self.assertIsNone(app.listing_detail(self.db,self.listing,self.buyer))
            self.assertIsNotNone(app.listing_detail(self.db,self.listing,self.seller))
            self.assertIsNotNone(app.listing_detail(self.db,self.listing,self.admin))
        where,args=app.catalogue_predicates(self.db,{},self.buyer)
        self.assertTrue(launch.test_listing(self.db,self.listing))
        self.route(self.admin,'POST','/api/admin/listings/'+self.listing+'/audience',{'audience':'public'})
        self.assertFalse(launch.test_listing(self.db,self.listing))

    def test_legacy_test_listing_is_hidden_without_deleting_history(self):
        self.db.execute("UPDATE listings SET title='ads sdasde ded' WHERE id=?",(self.listing,))
        self.db.execute("UPDATE seller_profiles SET shop_name='SentryLoot Test Seller' WHERE user_id=?",(self.seller,))
        self.assertTrue(launch.test_listing(self.db,self.listing))
        self.assertIsNotNone(self.db.execute('SELECT id FROM listings WHERE id=?',(self.listing,)).fetchone())

    def test_export_requires_reauthentication_and_does_not_include_secrets(self):
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/account/export',{'password':'wrong'})
        result=self.route(self.buyer,'POST','/api/account/export',{'password':'unique-test-password'})
        self.assertEqual(result['profile']['id'],self.buyer)
        encoded=json.dumps(result)
        for secret in ('password_hash','secret_cipher','token_hash','protected_payload','other@test.invalid','seller@test.invalid'):self.assertNotIn(secret,encoded)

    def test_seller_checklist_is_owned_and_catches_numeric_items_and_status_variants(self):
        self.db.execute("UPDATE listings SET product_type='item',attributes_json=? WHERE id=?",(json.dumps({'item_name':'40','item_variant':'active'}),self.listing))
        result=self.route(self.seller,'GET','/api/seller/readiness')
        self.assertTrue(result['identity_verified']);self.assertGreaterEqual(len(result['listings'][0]['issues']),2)
        self.assertEqual(self.route(self.other,'GET','/api/seller/readiness')['listings'],[])

    def test_quantity_price_is_used_by_cart_checkout_and_saved_order(self):
        self.db.execute("UPDATE listings SET stock=100,product_type='currency',min_quantity=1 WHERE id=?",(self.listing,))
        tiers=[{'quantity':10,'unit_price_minor':45000},{'quantity':50,'unit_price_minor':40000}]
        self.route(self.seller,'POST','/api/seller/listings/'+self.listing+'/price-tiers',{'tiers':tiers})
        self.assertEqual(self.db.execute('SELECT status FROM listings WHERE id=?',(self.listing,)).fetchone()['status'],'pending_review')
        self.db.execute("UPDATE listings SET status='published' WHERE id=?",(self.listing,))
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,?)',(self.buyer,self.listing,10))
        cart=self.route(self.buyer,'GET','/api/cart')
        self.assertEqual(cart['subtotal_minor'],450000)
        order=self.route(self.buyer,'POST','/api/checkout',{'accept_terms':True})
        line=self.db.execute('SELECT unit_price_minor FROM order_items WHERE order_id=?',(order['id'],)).fetchone()
        self.assertEqual(line['unit_price_minor'],45000)
        self.assertEqual(order['total_minor'],495000)
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/seller/listings/'+self.listing+'/price-tiers',{'tiers':[]})

    def test_quantity_price_rejects_foreign_listing_and_increasing_prices(self):
        url='/api/seller/listings/'+self.listing+'/price-tiers'
        with self.assertRaises(app.HttpError):self.route(self.other,'POST',url,{'tiers':[]})
        for tiers in ([{'quantity':10,'unit_price_minor':60000}],[{'quantity':10,'unit_price_minor':40000},{'quantity':5,'unit_price_minor':30000}],[{'quantity':True,'unit_price_minor':1}]):
            with self.assertRaises(app.HttpError):self.route(self.seller,'POST',url,{'tiers':tiers})

    def test_scoped_staff_cannot_access_finance_or_grant_permissions(self):
        grant={'capabilities':['moderation'],'password':'unique-test-password'}
        self.route(self.admin,'POST','/api/admin/staff/'+self.other,grant)
        self.route(self.other,'GET','/api/admin/listings')
        for path in ('/api/admin/overview','/api/admin/payouts','/api/admin/users','/api/admin/launch/profile'):
            with self.assertRaises(app.HttpError):self.route(self.other,'GET',path)
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/admin/staff/'+self.buyer,grant)
        self.route(self.admin,'POST','/api/admin/staff/'+self.other,{'capabilities':[],'password':'unique-test-password'})
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/admin/listings')

    def test_sandbox_history_does_not_create_seller_rank(self):
        r=self.route(self.buyer,'GET','/api/stores/'+self.seller+'/reputation')
        self.assertEqual(r['tier'],'new');self.assertEqual(r['real_completed_orders'],0)

    def test_service_milestones_are_snapshotted_and_sequential_without_releasing_funds(self):
        self.db.execute("UPDATE listings SET product_type='service' WHERE id=?",(self.listing,))
        plan=['Agree the coaching session','Deliver the coaching session']
        self.route(self.seller,'POST','/api/seller/listings/'+self.listing+'/service-plan',{'steps':plan})
        self.db.execute("UPDATE listings SET status='published' WHERE id=?",(self.listing,))
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.buyer,self.listing))
        order=app.checkout(self.db,self.buyer,True,True)
        oid=order['id'];iid=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(oid,)).fetchone()['id']
        self.route(self.buyer,'POST','/api/orders/'+oid+'/sandbox-complete',{})
        launch.put_config(self.db,'service_plan:'+self.listing,['A later listing edit'])
        result=self.route(self.buyer,'GET','/api/orders/'+oid+'/milestones')
        self.assertEqual([s['title'] for s in result['items'][0]['steps']],plan)
        base='/api/orders/'+oid+'/milestones/'+iid+'/'
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST',base+'1',{'action':'submit','note':'Full session was delivered.'})
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/orders/'+oid+'/milestones')
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST',base+'0',{'action':'submit','note':'Trying to submit as buyer.'})
        self.assertFalse(self.route(self.seller,'POST',base+'0',{'action':'submit','note':'Coaching time and goals agreed.'})['funds_released'])
        self.route(self.buyer,'POST',base+'0',{'action':'request_changes','note':'Please change the session time.'})
        self.route(self.seller,'POST',base+'0',{'action':'submit','note':'The requested time is confirmed.'})
        self.route(self.buyer,'POST',base+'0',{'action':'accept'})
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/orders/'+oid+'/complete',{})
        self.route(self.seller,'POST',base+'1',{'action':'submit','note':'The agreed coaching session finished.'})
        self.route(self.buyer,'POST',base+'1',{'action':'accept'})
        self.assertTrue(launch.milestones_complete(self.db,oid))
        self.assertNotEqual(self.db.execute('SELECT status FROM orders WHERE id=?',(oid,)).fetchone()['status'],'completed')

    def test_seller_coupon_quote_and_checkout_have_the_same_total_and_usage_limit(self):
        from datetime import datetime,timedelta,timezone
        coupon={'code':'LOCALQA20','listing_id':self.listing,'percent':20,'max_uses':1,'expires_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),'enabled':True}
        self.route(self.seller,'POST','/api/seller/coupons',coupon)
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.buyer,self.listing))
        quote=self.route(self.buyer,'POST','/api/cart/coupon',{'code':coupon['code']})
        self.assertEqual(quote['total_minor'],44000)
        order=self.route(self.buyer,'POST','/api/checkout',{'accept_terms':True,'accept_account_risk':True,'coupon_code':coupon['code']})
        self.assertEqual(order['total_minor'],quote['total_minor'])
        self.assertEqual(self.db.execute('SELECT unit_price_minor FROM order_items WHERE order_id=?',(order['id'],)).fetchone()['unit_price_minor'],40000)
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.other,self.listing))
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/cart/coupon',{'code':coupon['code']})

    def test_coupon_validation_and_referral_attribution_cannot_be_used_for_self_referrals(self):
        from datetime import datetime,timedelta,timezone
        coupon={'code':'LOCALQA20','listing_id':self.listing,'percent':99,'max_uses':1,'expires_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),'enabled':True}
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/seller/coupons',coupon)
        invitation=self.route(self.buyer,'POST','/api/referrals/code',{})['referral_code']
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/referrals/claim',{'code':invitation})
        self.assertTrue(self.route(self.other,'POST','/api/referrals/claim',{'code':invitation})['claimed'])
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/referrals/claim',{'code':invitation})
        points=self.route(self.buyer,'GET','/api/loyalty')
        self.assertEqual(points['qualified_referrals'],0);self.assertEqual(points['loyalty_points'],0)
        self.assertFalse(points['rules']['cash_value']);self.assertFalse(points['rules']['redeemable'])

if __name__=='__main__':unittest.main()
