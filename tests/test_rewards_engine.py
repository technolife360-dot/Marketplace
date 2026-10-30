import json
import time
import unittest
from unittest.mock import patch
import app
import rewards_engine as rewards
from tests import test_marketplace as fixtures

class RewardsEngineTests(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx
    route=fixtures.MarketplaceFlows.route

    def rates(self):
        return patch.object(app.regional_preferences,'exchange_rates',return_value={
            'base':'USD','rates':{'USD':1,'UZS':12500,'MYR':4},'updated_at':int(time.time())})

    def campaign(self,**changes):
        data={'kind':'voucher','scope':'both','discount_type':'fixed','value':1000,
              'currency':'USD','max_uses':1,'per_user_limit':1,'expires_at':'2099-01-01T00:00:00Z',
              'enabled':True,'code':'GIFT123456789','recipient_id':''}
        data.update(changes)
        with self.rates():return self.route(self.admin,'POST','/api/admin/rewards/campaigns',data)

    def gift(self,**changes):
        self.campaign(**changes)
        with self.rates():return self.route(self.buyer,'POST','/api/rewards/vouchers/claim',{'code':'GIFT123456789'})

    def quote(self,**changes):
        if not self.db.execute('SELECT 1 FROM carts WHERE user_id=?',(self.buyer,)).fetchone():
            self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.buyer,self.listing))
        data={'kind':'account','use_bonus':False};data.update(changes)
        with self.rates():return self.route(self.buyer,'POST','/api/rewards/quote',data)

    def reserve(self,quote):
        lines,currency,subtotal,fee=rewards.context(self.db,self.buyer,{'kind':'account'},vars(app))
        oid=app.ident();self.db.execute('BEGIN IMMEDIATE')
        try:result=rewards.reserve(self.db,self.buyer,quote['id'],'account',oid,lines,currency,subtotal,fee,vars(app))
        except Exception:self.db.execute('ROLLBACK');raise
        self.db.execute('INSERT INTO orders(id,reference,buyer_id,currency,subtotal_minor,commission_minor,total_minor,status,payment_mode) VALUES(?,?,?,?,?,?,?,?,?)',
                        (oid,oid,self.buyer,currency,subtotal,fee,result['total_minor'],'pending_payment','stripe_test'))
        self.db.execute("INSERT INTO payments(id,order_id,provider,amount_minor,currency,status,idempotency_key) VALUES(?,?,?,?,?,'pending',?)",(app.ident(),oid,'stripe_test',result['total_minor'],currency,app.ident()))
        self.db.execute('COMMIT');return oid,result

    def state(self,oid,status,payment):
        self.db.execute('BEGIN IMMEDIATE')
        self.db.execute('UPDATE orders SET status=? WHERE id=?',(status,oid))
        self.db.execute('UPDATE payments SET status=? WHERE order_id=?',(payment,oid))
        rewards.sync_order(self.db,oid,vars(app));rewards.sync_order(self.db,oid,vars(app))
        self.db.execute('COMMIT')

    def wallet(self):
        with self.rates():return self.route(self.buyer,'GET','/api/rewards')

    def test_voucher_is_global_single_use_recipient_bound_and_idempotent(self):
        first=self.gift(recipient_id=self.buyer)
        self.assertEqual(first['available_micro'],10000000)
        with self.rates():
            second=self.route(self.buyer,'POST','/api/rewards/vouchers/claim',{'code':'GIFT123456789'})
            self.assertEqual(second['available_micro'],first['available_micro'])
            with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/rewards/vouchers/claim',{'code':'GIFT123456789'})

    def test_uzs_quote_debits_common_credit_and_keeps_gross_seller_price(self):
        self.gift();q=self.quote(use_bonus=True)
        self.assertEqual(q['gross_total_minor'],55000)
        self.assertEqual(q['bonus_minor'],11000)
        self.assertEqual(q['total_minor'],44000)
        oid,record=self.reserve(q)
        self.assertEqual(record['spent_micro'],880000)
        self.assertEqual(self.wallet()['available_micro'],9120000)
        self.state(oid,'cancelled','expired')
        self.assertEqual(self.wallet()['available_micro'],10000000)

    def test_award_requires_verified_completion_refund_request_does_not_restore(self):
        self.gift();oid,_=self.reserve(self.quote(use_bonus=True))
        self.state(oid,'delivered','succeeded');self.assertEqual(self.wallet()['pending_micro'],31200)
        self.state(oid,'completed','succeeded');self.assertEqual(self.wallet()['available_micro'],9151200)
        self.state(oid,'refunded','refund_pending');self.assertEqual(self.wallet()['available_micro'],9120000)
        self.state(oid,'refunded','refunded');self.assertEqual(self.wallet()['available_micro'],10000000)

    def test_platform_coupon_is_scoped_limited_and_not_stackable(self):
        self.campaign(kind='coupon',code='ACCOUNT10',discount_type='percent',value=1000,scope='account')
        q=self.quote(coupon_code='ACCOUNT10');self.assertEqual(q['discount_minor'],5000)
        self.assertEqual(q['total_minor'],50000)
        with self.assertRaises(app.HttpError):self.quote(coupon_code='ACCOUNT10',use_bonus=True)
        self.reserve(q)
        with self.assertRaises(app.HttpError):self.quote(coupon_code='ACCOUNT10')

    def test_quote_owner_expiry_and_reuse_are_checked(self):
        q=self.quote();self.reserve(q)
        with self.assertRaises(app.HttpError):self.reserve(q)
        q=self.quote()
        key=rewards.PREFIX+'quote:'+q['id'];value=rewards.read(self.db,key);value['expires_at']=int(time.time())-1;rewards.write(self.db,key,value)
        with self.assertRaises(app.HttpError):self.reserve(q)

    def test_fx_failure_invalid_amounts_and_admin_authorization_fail_closed(self):
        with patch.object(app.regional_preferences,'exchange_rates',return_value={'available':False,'rates':{}}):
            with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/rewards/quote',{'kind':'account'})
        for uid in (self.buyer,None):
            with self.assertRaises(app.HttpError):self.route(uid,'POST','/api/admin/rewards/settings',{'account_bps':10000})
        with self.assertRaises(app.HttpError):self.campaign(value=True)
        with self.assertRaises(app.HttpError):self.campaign(kind='voucher',discount_type='percent')

    def test_settings_do_not_retroactively_change_existing_quote_promises(self):
        q=self.quote()
        self.route(self.admin,'POST','/api/admin/rewards/settings',{'account_bps':200})
        oid,_=self.reserve(q);self.state(oid,'completed','succeeded')
        self.assertEqual(self.wallet()['available_micro'],40000)

    def test_voucher_scope_is_enforced_after_claim_not_only_when_the_code_is_entered(self):
        self.gift(scope='account')
        self.db.execute("UPDATE topup_packages SET price_minor=20000 WHERE id='pubg-mobile-60-uc'")
        wallet=self.wallet()
        self.assertEqual(wallet['usable_for']['account'],10000000)
        self.assertEqual(wallet['usable_for']['topup'],0)
        with self.rates():
            with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/rewards/quote',
                {'kind':'topup','package_id':'pubg-mobile-60-uc','quantity':1,'use_bonus':True})
