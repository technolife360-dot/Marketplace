import concurrent.futures
from datetime import datetime, timezone
import time
import unittest
from unittest.mock import patch
import app
import spin_win as spin
import rewards_engine as rewards
from tests import test_marketplace as fixtures

class SpinWinTests(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx
    route=fixtures.MarketplaceFlows.route

    def fx(self):
        return patch.object(app.regional_preferences,'exchange_rates',return_value={'rates':{'USD':1,'MYR':4,'UZS':12500},'updated_at':int(time.time())})
    def enable(self,**changes):
        data={'enabled':True,'budget_minor':10000,'stock':{'iphone':1,'ps5':1,'tv':1}};data.update(changes)
        return self.route(self.admin,'POST','/api/admin/spin-win/settings',data)
    def roll(self,ticket=0,uid=None):
        with self.fx(),patch.object(spin.secrets,'randbelow',return_value=ticket):
            return self.route(uid or self.buyer,'POST','/api/spin-win/spin',{})

    def test_defaults_require_owner_to_activate_and_do_not_advertise_unstocked_prizes(self):
        state=self.route(self.buyer,'GET','/api/spin-win')
        self.assertFalse(state['enabled']);self.assertFalse(state['can_spin'])
        self.assertEqual(state['prizes'],[dict(spin.PRIZES[-1],weight=100000)])
        with self.assertRaises(app.HttpError):self.roll()

    def test_guest_preview_exposes_prize_labels_without_personal_state(self):
        preview=self.route(None,'GET','/api/spin-win/preview')
        self.assertFalse(preview['enabled'])
        self.assertEqual(preview['prizes'],[])
        self.enable()
        self.roll()
        preview=self.route(None,'GET','/api/spin-win/preview')
        self.assertTrue(preview['enabled'])
        self.assertNotIn('iphone',[prize['id'] for prize in preview['prizes']])
        self.assertEqual(set(preview),{'enabled','test_only','prizes'})

    def test_exhausted_campaign_does_not_consume_another_users_spin(self):
        self.enable(budget_minor=10,stock={'iphone':0,'ps5':0,'tv':0})
        self.roll()
        state=self.route(self.other,'GET','/api/spin-win')
        self.assertFalse(state['enabled'])
        self.assertFalse(state['can_spin'])
        with self.assertRaises(app.HttpError):
            self.roll(uid=self.other)
        self.assertIsNone(self.route(self.other,'GET','/api/spin-win')['today'])

    def test_production_vouchers_are_saved_in_the_real_wallet_during_test_checkout(self):
        with patch.dict(spin.os.environ,{'VERCEL_ENV':'production'}),patch.object(app,'MODE','production'):
            core=vars(app)
            self.assertEqual(spin.campaign_mode(core),'real')
            spin.save_settings(self.db,self.admin,{'enabled':True,'budget_minor':200000,'stock':{'iphone':1,'ps5':1,'tv':2}},core)
            state=spin.state(self.db,self.buyer,core)
            self.assertTrue(state['can_spin'])
            self.assertFalse(state['test_only'])
            self.assertIn('rm10',[prize['id'] for prize in state['prizes']])
            with self.fx(),patch.object(spin.secrets,'randbelow',return_value=5):
                result=spin.spin(self.db,self.buyer,{},core)
            self.assertEqual(result['status'],'saved_for_live_topup')
            self.assertFalse(result['test_only'])
            self.assertEqual(spin.counters(self.db,'real')['spent_minor'],10)
            self.assertEqual(spin.counters(self.db,'test')['spent_minor'],0)
            lot,=rewards.lots(self.db,self.buyer,'real')
            self.assertIsNone(lot['expires_at'])
            self.assertEqual(rewards.wallet_values(self.db,self.buyer,'test','topup')['available_micro'],0)
            self.assertEqual(rewards.wallet_values(self.db,self.buyer,'real','topup')['available_micro'],25000)
            self.assertEqual(rewards.wallet_values(self.db,self.buyer,'real','account')['available_micro'],0)
            with self.fx(),patch.object(rewards,'mode',return_value='test'):
                self.assertEqual(rewards.wallet(self.db,self.buyer,core)['saved_spin_myr_minor'],10)
            self.assertEqual(spin.settings(self.db,'real')['budget_minor'],200000)

    def test_exact_odds_and_daily_result_are_idempotent(self):
        self.enable();state=self.route(self.buyer,'GET','/api/spin-win')
        self.assertEqual(sum(r['weight'] for r in state['prizes']),100000)
        self.assertEqual([r['weight'] for r in state['prizes'][:3]],[1,2,2])
        first=self.roll();second=self.roll(99999)
        self.assertEqual(first,second)
        self.assertFalse(self.route(self.buyer,'GET','/api/spin-win')['can_spin'])
        current=rewards.mode(vars(app))
        self.assertEqual(spin.counters(self.db,current)['awarded']['iphone'],1)

    def test_voucher_automatically_credits_topup_only_and_deducts_budget_once(self):
        self.enable();award=self.roll(5)
        self.assertEqual(award['minor'],10)
        current=rewards.mode(vars(app))
        self.assertEqual(rewards.wallet_values(self.db,self.buyer,current,'topup')['available_micro'],25000)
        self.assertEqual(rewards.wallet_values(self.db,self.buyer,current,'account')['available_micro'],0)
        self.roll(5)
        self.assertEqual(spin.counters(self.db,current)['spent_minor'],10)

    def test_no_prize_consumes_only_daily_spin(self):
        self.enable();award=self.roll(99999)
        self.assertEqual(award['kind'],'none')
        self.assertEqual(rewards.wallet_values(self.db,self.buyer,rewards.mode(vars(app)))['available_micro'],0)
        self.assertEqual(self.roll(0)['id'],award['id'])

    def test_winner_private_queue_notification_and_fulfilment(self):
        self.enable();award=self.roll()
        queue=self.route(self.admin,'GET','/api/admin/spin-win')
        winner=queue['winners'][0]
        self.assertEqual(winner['uid'],self.buyer)
        self.assertEqual(winner['user']['email'],'buyer@test.invalid')
        self.assertNotIn('uid',award)
        notes=self.db.execute("SELECT * FROM notifications WHERE user_id=? AND kind='spin_win'",(self.admin,)).fetchall()
        self.assertEqual(len(notes),1);self.assertIn(award['id'],notes[0]['body'])
        self.route(self.admin,'POST','/api/admin/spin-win/winners/'+award['id'],{'status':'contacted'})
        self.assertEqual(self.route(self.buyer,'GET','/api/spin-win')['today']['status'],'contacted')
        with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/spin-win/winners/'+award['id'],{'status':'new'})

    def test_inventory_and_budget_exhaustion_move_probability_to_none(self):
        self.enable(budget_minor=10);self.roll()
        state=self.route(self.other,'GET','/api/spin-win')
        self.assertNotIn('iphone',[r['id'] for r in state['prizes']])
        self.assertEqual(sum(r['weight'] for r in state['prizes']),100000)
        self.roll(4,uid=self.other) # PS5 + TV are now the first four slots; voucher follows.
        state=self.route(self.admin,'GET','/api/spin-win')
        self.assertFalse(any(r['kind']=='voucher' for r in state['prizes']))

    def test_malaysia_midnight_resets_without_waiting_24_hours(self):
        self.enable()
        with patch.object(spin,'now',return_value=datetime(2026,11,5,15,59,59,tzinfo=timezone.utc)):
            first=self.roll(99999);self.assertEqual(first['day'],'2026-11-05')
        with patch.object(spin,'now',return_value=datetime(2026,11,5,16,0,0,tzinfo=timezone.utc)):
            self.assertTrue(self.route(self.buyer,'GET','/api/spin-win')['can_spin'])
            second=self.roll(99999);self.assertEqual(second['day'],'2026-11-06')

    def test_fx_failure_and_notification_failure_leave_no_spin_or_prize_consumed(self):
        self.enable()
        with patch.object(app.regional_preferences,'exchange_rates',return_value={'available':False}):
            with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/spin-win/spin',{})
        with patch.object(app,'notify',side_effect=RuntimeError('notification write failed')):
            with self.assertRaises(RuntimeError):self.roll()
        self.assertTrue(self.route(self.buyer,'GET','/api/spin-win')['can_spin'])
        self.assertEqual(spin.counters(self.db,rewards.mode(vars(app)))['awarded']['iphone'],0)

    def test_authorization_and_client_selected_prizes_are_rejected(self):
        self.enable()
        for uid in (None,self.buyer):
            with self.assertRaises(app.HttpError):self.route(uid,'GET','/api/admin/spin-win')
        self.db.execute('UPDATE users SET email_verified=0 WHERE id=?',(self.other,))
        with self.assertRaises(app.HttpError):self.roll(uid=self.other)
        with self.fx():
            with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/spin-win/spin',{'prize':'iphone'})
        self.assertTrue(self.route(self.buyer,'GET','/api/spin-win')['can_spin'])

    def test_mode_isolation_and_inventory_cannot_be_reset_below_awards(self):
        with patch.object(rewards,'mode',return_value='test'):
            self.enable();award=self.roll()
            self.assertTrue(award['test_only'])
            with self.assertRaises(app.HttpError):self.enable(stock={'iphone':0,'ps5':1,'tv':1})
        with patch.object(rewards,'mode',return_value='real'):
            self.assertFalse(self.route(self.buyer,'GET','/api/spin-win')['enabled'])
            self.assertEqual(self.route(self.admin,'GET','/api/admin/spin-win')['total'],0)

    def test_parallel_daily_requests_issue_one_award(self):
        self.enable()
        def request():
            db=app.connect()
            try:return spin.spin(db,self.buyer,{},vars(app))
            finally:db.close()
        with self.fx(),patch.object(spin.secrets,'randbelow',return_value=5):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:request(),range(2)))
        self.assertEqual(results[0]['id'],results[1]['id'])
        self.assertEqual(spin.counters(self.db,rewards.mode(vars(app)))['spent_minor'],10)

class SpinWinTopupTests(unittest.TestCase):
    setUp=SpinWinTests.setUp
    tearDown=SpinWinTests.tearDown
    ctx=SpinWinTests.ctx
    route=SpinWinTests.route
    fx=SpinWinTests.fx
    enable=SpinWinTests.enable
    roll=SpinWinTests.roll

    def test_spin_credit_reduces_supplier_usd_quote_and_is_held_once(self):
        from tests import test_stripe_test_payments as stripe_fixtures
        stripe_fixtures.StripeTestFlows.configure(self)
        self.enable()
        self.roll(5)
        sku=next(iter(app.melostore_catalog.PUBG_TEST_OFFERS))
        with self.fx():
            quote=self.route(self.buyer,'POST','/api/rewards/quote',{'kind':'topup','sku':sku,'quantity':1,'use_bonus':True})
        offer=app.melostore_catalog.test_checkout_offer(sku)
        self.assertEqual(quote['currency'],'USD')
        self.assertGreater(quote['bonus_minor'],0)
        self.assertLess(quote['total_minor'],offer['price_minor'])
        data={'sku':sku,'quantity':1,'player_id':'12345678','server_id':'','request_key':'spin_supplier_fixture_0001','accept_terms':True,'rewards_quote_id':quote['id']}
        first=self.route(self.buyer,'POST','/api/top-up/test-checkout',data)
        second=self.route(self.buyer,'POST','/api/top-up/test-checkout',data)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(self.route(self.buyer,'GET','/api/top-up/test-orders/'+first['id'])['total_minor'],quote['total_minor'])
        self.assertEqual(rewards.wallet_values(self.db,self.buyer,'test','topup')['available_micro'],25000-quote['spent_micro'])

    def test_supplier_quote_cannot_be_applied_to_different_sku(self):
        from tests import test_stripe_test_payments as stripe_fixtures
        stripe_fixtures.StripeTestFlows.configure(self)
        first,second=list(app.melostore_catalog.PUBG_TEST_OFFERS)[:2]
        with self.fx():quote=self.route(self.buyer,'POST','/api/rewards/quote',{'kind':'topup','sku':first,'use_bonus':False})
        with self.assertRaises(app.HttpError):
            self.route(self.buyer,'POST','/api/top-up/test-checkout',{'sku':second,'quantity':1,'player_id':'12345678','server_id':'','request_key':'spin_wrong_sku_fixture_001','accept_terms':True,'rewards_quote_id':quote['id']})

class SpinWinConcurrencyTests(unittest.TestCase):
    setUp=SpinWinTests.setUp
    tearDown=SpinWinTests.tearDown
    ctx=SpinWinTests.ctx
    route=SpinWinTests.route
    fx=SpinWinTests.fx
    enable=SpinWinTests.enable
    def test_different_buyers_cannot_exceed_last_voucher_budget(self):
        self.enable(budget_minor=10,stock={'iphone':0,'ps5':0,'tv':0})
        def request(uid):
            db=app.connect()
            try:return spin.spin(db,uid,{},vars(app))
            except app.HttpError as exc:
                if exc.status!=409:raise
                return None
            finally:db.close()
        with self.fx(),patch.object(spin.secrets,'randbelow',return_value=0):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(request,[self.buyer,self.other]))
        self.assertEqual([r['kind'] for r in results if r],['voucher'])
        self.assertEqual(results.count(None),1)
        self.assertEqual(spin.counters(self.db,rewards.mode(vars(app)))['spent_minor'],10)
