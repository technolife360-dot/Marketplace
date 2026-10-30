"""Checkout integration: platform benefits never reduce seller entitlements."""
import time
import unittest
from unittest.mock import patch

import app
import stripe_test_payments as payments
from tests import test_marketplace as fixtures
from tests import test_stripe_test_payments as stripe_fixtures


class RewardsCheckoutIntegration(unittest.TestCase):
    setUp = fixtures.MarketplaceFlows.setUp
    tearDown = fixtures.MarketplaceFlows.tearDown
    ctx = fixtures.MarketplaceFlows.ctx
    route = fixtures.MarketplaceFlows.route
    configure = stripe_fixtures.StripeTestFlows.configure
    signed = stripe_fixtures.StripeTestFlows.signed
    pay = stripe_fixtures.StripeTestFlows.pay

    def cart(self):
        self.db.execute("UPDATE listings SET price_minor=10000,currency='MYR' WHERE id=?", (self.listing,))
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)', (self.buyer, self.listing))

    def test_order_promotion_metadata_excludes_private_ledger_fields(self):
        record = {'quote_id': 'quote_fixture', 'gross_total_minor': 11000, 'total_minor': 8000,
                  'discount_minor': 3000, 'uid': self.buyer, 'allocations': [{'lot_id': 'private_lot'}],
                  'rates': {'MYR': '4'}, 'context': 'private_binding', 'spent_micro': 750000}
        self.assertEqual(payments.promotion_view(record), {'quote_id': 'quote_fixture',
            'gross_total_minor': 11000, 'total_minor': 8000, 'discount_minor': 3000})

    def test_quote_reserves_before_payment_and_preserves_gross_seller_entitlement(self):
        provider = self.configure(); self.cart()
        def reserve(db, uid, quote, kind, oid, lines, currency, subtotal, fee, core):
            self.assertTrue(db.in_transaction)
            self.assertIsNone(db.execute('SELECT id FROM orders WHERE id=?', (oid,)).fetchone())
            self.assertEqual((uid, quote, kind, currency, subtotal, fee),
                             (self.buyer, 'quote_fixture', 'account', 'MYR', 10000, 1000))
            self.assertEqual(lines[0]['price_minor'], 10000)
            return {'total_minor': 8000}
        with patch.object(app.rewards_engine, 'reserve', side_effect=reserve) as reserved:
            result = app.checkout(self.db, self.buyer, True, True, request_key='rewards_checkout_0001',
                                  expected_total_minor=8000, expected_currency='MYR', rewards_quote_id='quote_fixture')
            replay = app.checkout(self.db, self.buyer, True, True, request_key='rewards_checkout_0001',
                                  expected_total_minor=8000, expected_currency='MYR', rewards_quote_id='quote_fixture')
            self.assertEqual(result['id'], replay['id']); reserved.assert_called_once()
        self.assertEqual(result['total_minor'], 8000)
        order = self.db.execute('SELECT * FROM orders WHERE id=?', (result['id'],)).fetchone()
        item = self.db.execute('SELECT * FROM order_items WHERE order_id=?', (result['id'],)).fetchone()
        payment = self.db.execute('SELECT * FROM payments WHERE order_id=?', (result['id'],)).fetchone()
        self.assertEqual((order['subtotal_minor'], order['commission_minor'], order['total_minor']), (10000, 1000, 8000))
        self.assertEqual(payment['amount_minor'], 8000)
        self.assertEqual(item['unit_price_minor']*item['quantity']-item['commission_minor'], 9000)
        with self.assertRaises(app.HttpError) as error:
            app.checkout(self.db, self.buyer, True, True, request_key='rewards_checkout_0001',
                         expected_total_minor=8000, expected_currency='MYR', rewards_quote_id='different_quote')
        self.assertEqual(error.exception.status, 409)
        provider.client.v1.checkout.sessions.create.assert_not_called()

    def test_changed_net_total_rolls_back_quote_and_stock_reservation(self):
        self.configure(); self.cart()
        with patch.object(app.rewards_engine, 'reserve', return_value={'total_minor': 8000}):
            with self.assertRaises(app.HttpError):
                app.checkout(self.db, self.buyer, True, True, expected_total_minor=11000,
                             expected_currency='MYR', rewards_quote_id='quote_fixture')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM orders').fetchone()['n'], 0)
        self.assertEqual(self.db.execute('SELECT reserved FROM listings WHERE id=?', (self.listing,)).fetchone()['reserved'], 0)
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM carts WHERE user_id=?', (self.buyer,)).fetchone())

    def test_subsidy_uses_platform_balance_and_reconciles_transfer_without_source(self):
        provider = self.configure()
        provider.client.v1.charges.retrieve.return_value = {
            'id': 'ch_subsidy', 'livemode': False, 'currency': 'uzs', 'amount': 8000000,
            'balance_transaction': {'amount': 2400, 'currency': 'myr'}}
        provider.transfer('order_subsidy', self.seller, 'acct_seller', 'ch_subsidy', 100000, 'UZS')
        params = provider.client.v1.transfers.create.call_args.args[0]
        self.assertEqual(params['amount'], 3000)
        self.assertEqual(params['currency'], 'myr')
        self.assertNotIn('source_transaction', params)
        provider.client.v1.transfers.create.reset_mock()
        provider.client.v1.transfers.list.return_value = {'has_more': False, 'data': [{
            'id': 'tr_subsidy', 'livemode': False, 'amount': 3000, 'currency': 'myr',
            'destination': 'acct_seller', 'metadata': {'sentryloot_seller': self.seller}}]}
        self.assertEqual(provider.transfer('order_subsidy', self.seller, 'acct_seller', 'ch_subsidy', 100000, 'UZS')['id'], 'tr_subsidy')
        provider.client.v1.transfers.create.assert_not_called()

    def test_insufficient_platform_balance_keeps_settlement_pending(self):
        provider = self.configure(); self.cart()
        with patch.object(app.rewards_engine, 'reserve', return_value={'total_minor': 8000}):
            result = app.checkout(self.db, self.buyer, True, True, rewards_quote_id='quote_fixture')
        oid = result['id']
        self.db.execute("UPDATE orders SET status='completed' WHERE id=?", (oid,))
        self.db.execute("UPDATE payments SET status='succeeded',provider_reference='pi_subsidy' WHERE order_id=?", (oid,))
        payments.write(self.db, 'paid:'+oid, {'intent': 'pi_subsidy', 'charge': 'ch_subsidy'})
        payments.write(self.db, 'seller:'+self.seller, {'id': 'acct_seller'})
        payments.queue_release(self.db, oid)
        provider.client.v1.charges.retrieve.return_value = {'id': 'ch_subsidy', 'livemode': False,
            'amount': 8000, 'currency': 'myr', 'balance_transaction': {'amount': 8000, 'currency': 'myr'}}
        provider.client.v1.transfers.create.side_effect = RuntimeError('insufficient balance')
        result = payments.process(self.db, vars(app))
        self.assertEqual(result['jobs'][0]['status'], 'retry')
        self.assertNotIn('source_transaction', provider.client.v1.transfers.create.call_args.args[0])
        self.assertIsNone(payments.read(self.db, 'ledger_release:'+oid))
        self.assertIsNone(payments.read(self.db, 'transfer:'+oid+':'+self.seller))

    def test_topup_net_is_verified_refunded_and_bound_to_checkout_request(self):
        provider = self.configure()
        pid = self.db.execute("SELECT id FROM topup_packages WHERE game_slug='pubg-mobile' LIMIT 1").fetchone()['id']
        self.db.execute('UPDATE topup_packages SET price_minor=10000,enabled=1 WHERE id=?', (pid,))
        data = {'package_id': pid, 'player_id': '12345678', 'quantity': 2, 'request_key': 'topup_rewards_fixture_0001',
                'accept_terms': True, 'rewards_quote_id': 'topup_quote_fixture'}
        promotion = {'gross_total_minor': 20000, 'discount_minor': 5000, 'bonus_minor': 0, 'total_minor': 15000}
        with patch.object(app.rewards_engine, 'reserve', return_value=promotion) as reserve:
            result = self.route(self.buyer, 'POST', '/api/top-up/test-checkout', data)
        oid = result['id']
        self.assertEqual(reserve.call_args.args[5], [{'package_id': pid, 'quantity': 2, 'price_minor': 10000}])
        with self.assertRaises(app.HttpError) as error:
            self.route(self.buyer, 'POST', '/api/top-up/test-checkout', {**data, 'rewards_quote_id': 'wrong_quote'})
        self.assertEqual(error.exception.status, 409)
        with patch.object(app.rewards_engine, 'purchase', return_value=promotion), patch.object(app.rewards_engine, 'sync_topup'):
            provider.client.v1.checkout.sessions.create.return_value = {'id': 'cs_test_rewards_topup', 'livemode': False,
                'url': 'https://checkout.stripe.com/c/pay/cs_test_rewards_topup', 'expires_at': int(time.time())+1800}
            self.route(self.buyer, 'POST', '/api/top-up/test-orders/'+oid+'/checkout')
            self.assertEqual(provider.client.v1.checkout.sessions.create.call_args.args[0]['line_items'][0]['price_data']['unit_amount'], 1500000)
            intent = {'id': 'pi_rewards_topup', 'livemode': False, 'status': 'succeeded', 'amount_received': 1500000,
                'currency': 'uzs', 'latest_charge': {'id': 'ch_rewards_topup', 'livemode': False, 'refunded': False, 'disputed': False}}
            self.session = {'id': 'cs_test_rewards_topup', 'livemode': False, 'client_reference_id': oid,
                'amount_total': 1500000, 'currency': 'uzs', 'payment_status': 'paid', 'payment_intent': intent,
                'metadata': {'sentryloot_mode': 'stripe_test', 'sentryloot_kind': 'topup', 'sentryloot_order': oid}}
            provider.client.v1.checkout.sessions.retrieve.return_value = self.session
            provider.client.v1.payment_intents.retrieve.return_value = intent
            self.pay()
            self.assertEqual(self.route(self.buyer, 'GET', '/api/top-up/test-orders/'+oid)['total_minor'], 15000)
            self.route(self.buyer, 'POST', '/api/top-up/test-orders/'+oid+'/cancel')
            self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'succeeded')
            self.assertEqual(provider.client.v1.refunds.create.call_args.args[0]['amount'], 1500000)
            self.assertEqual(self.db.execute('SELECT status FROM topup_orders WHERE id=?', (oid,)).fetchone()['status'], 'refunded')

    def test_engine_quote_awards_only_after_verified_completion_and_reverses_confirmed_refund(self):
        provider = self.configure(); self.cart()
        fx = {'available': True, 'updated_at': time.time(), 'rates': {'USD': 1, 'MYR': 4, 'UZS': 10000}}
        with patch.object(app.regional_preferences, 'exchange_rates', return_value=fx):
            self.route(self.admin, 'POST', '/api/admin/rewards/campaigns', {
                'code': 'CHECKOUTHALF', 'kind': 'coupon', 'scope': 'account', 'discount_type': 'percent',
                'value': 5000, 'currency': 'MYR', 'expires_at': '2099-01-01T00:00:00Z'})
            quote = self.route(self.buyer, 'POST', '/api/rewards/quote', {'kind': 'account', 'coupon_code': 'CHECKOUTHALF'})
            self.assertEqual((quote['subtotal_minor'], quote['fee_minor'], quote['discount_minor'], quote['total_minor']),
                             (10000, 1000, 5000, 6000))
            result = app.checkout(self.db, self.buyer, True, True, expected_total_minor=6000,
                                  expected_currency='MYR', rewards_quote_id=quote['id'])
            oid = result['id']
            public = app.order_view(self.db, oid, self.buyer)['promotions']
            self.assertEqual(public['quote_id'], quote['id'])
            self.assertNotIn('allocations', public)
            self.assertNotIn('uid', public)
            self.assertNotIn('rates', public)
            wallet = self.route(self.buyer, 'GET', '/api/rewards')
            self.assertEqual((wallet['available_micro'], wallet['pending_micro']), (0, 125000))
            provider.client.v1.checkout.sessions.create.return_value = {'id': 'cs_test_real_rewards', 'livemode': False,
                'url': 'https://checkout.stripe.com/c/pay/cs_test_real_rewards', 'expires_at': int(time.time())+1800}
            payments.start_checkout(self.db, oid, self.buyer, vars(app))
            intent = {'id': 'pi_real_rewards', 'livemode': False, 'status': 'succeeded', 'amount_received': 6000,
                'currency': 'myr', 'latest_charge': {'id': 'ch_real_rewards', 'livemode': False, 'refunded': False, 'disputed': False}}
            self.session = {'id': 'cs_test_real_rewards', 'livemode': False, 'client_reference_id': oid,
                'amount_total': 6000, 'currency': 'myr', 'payment_status': 'paid', 'payment_intent': intent,
                'metadata': {'sentryloot_mode': 'stripe_test', 'sentryloot_order': oid}}
            provider.client.v1.checkout.sessions.retrieve.return_value = self.session
            provider.client.v1.payment_intents.retrieve.return_value = intent
            self.pay()
            self.assertEqual(self.route(self.buyer, 'GET', '/api/rewards')['available_micro'], 0)
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute("UPDATE orders SET status='completed' WHERE id=?", (oid,))
            app.event(self.db, oid, self.buyer, 'paid', 'completed', 'Fixture delivery confirmed')
            app.rewards_engine.sync_order(self.db, oid, vars(app))
            self.db.execute('COMMIT')
            wallet = self.route(self.buyer, 'GET', '/api/rewards')
            self.assertEqual(wallet['available_micro'], 125000)
            self.assertEqual(sum(entry['type']=='earned' for entry in wallet['history']), 1)
            self.assertEqual(wallet['mode'], 'test')
            self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM bonus_entries WHERE mode='real'").fetchone()['n'], 0)
            self.db.execute('BEGIN IMMEDIATE')
            payments.queue_refund(self.db, oid, vars(app))
            self.db.execute('COMMIT')
            self.assertEqual(self.route(self.buyer, 'GET', '/api/rewards')['available_micro'], 0)
            provider.client.v1.refunds.create.return_value = {'id': 're_real_rewards', 'status': 'pending'}
            self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'retry')
            self.assertEqual(app.rewards_engine.purchase(self.db, 'account', oid)['state'], 'refund_pending')
            provider.client.v1.refunds.create.return_value = {'id': 're_real_rewards', 'status': 'succeeded'}
            self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'succeeded')
            self.assertEqual(provider.client.v1.refunds.create.call_args.args[0]['amount'], 6000)
            self.assertEqual(app.rewards_engine.purchase(self.db, 'account', oid)['state'], 'refunded')
            self.assertEqual(self.route(self.buyer, 'GET', '/api/rewards')['available_micro'], 0)

    def test_topup_credit_reservation_cancel_and_late_refund_restore_once(self):
        provider = self.configure()
        pid = self.db.execute("SELECT id FROM topup_packages WHERE game_slug='pubg-mobile' LIMIT 1").fetchone()['id']
        self.db.execute('UPDATE topup_packages SET price_minor=10000,enabled=1 WHERE id=?', (pid,))
        fx = {'available': True, 'updated_at': time.time(), 'rates': {'USD': 1, 'MYR': 4, 'UZS': 10000}}
        with patch.object(app.regional_preferences, 'exchange_rates', return_value=fx):
            self.route(self.admin, 'POST', '/api/admin/rewards/campaigns', {'code': 'TOPUPGIFT', 'kind': 'voucher',
                'scope': 'both', 'discount_type': 'fixed', 'value': 100, 'currency': 'USD', 'expires_at': '2099-01-01T00:00:00Z'})
            self.route(self.buyer, 'POST', '/api/rewards/vouchers/claim', {'code': 'TOPUPGIFT'})
            quote = self.route(self.buyer, 'POST', '/api/rewards/quote', {'kind': 'topup', 'package_id': pid, 'quantity': 2, 'use_bonus': True})
            self.assertEqual((quote['gross_total_minor'], quote['bonus_minor'], quote['total_minor'], quote['earn_micro']),
                             (20000, 4000, 16000, 8000))
            with patch.object(app, 'configured_payment_provider', return_value=type('DisabledProvider', (), {'name': 'disabled'})()):
                self.db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(app.HttpError):
                    app.rewards_engine.reserve(self.db, self.buyer, quote['id'], 'topup', 'wrong_mode_source',
                        [{'package_id': pid, 'quantity': 2, 'price_minor': 10000}], 'UZS', 20000, 0, vars(app))
                self.db.execute('ROLLBACK')
            data = {'package_id': pid, 'player_id': '12345678', 'quantity': 2, 'request_key': 'credit_topup_fixture_0001',
                    'accept_terms': True, 'rewards_quote_id': quote['id']}
            self.oid = self.route(self.buyer, 'POST', '/api/top-up/test-checkout', data)['id']
            self.assertNotIn('allocations', self.route(self.buyer, 'GET', '/api/top-up/test-orders/'+self.oid)['promotions'])
            self.assertEqual(self.route(self.buyer, 'GET', '/api/rewards')['available_micro'], 600000)
            provider.client.v1.checkout.sessions.create.return_value = {'id': 'cs_test_credit_topup', 'livemode': False,
                'url': 'https://checkout.stripe.com/c/pay/cs_test_credit_topup', 'expires_at': int(time.time())+1800}
            self.route(self.buyer, 'POST', '/api/top-up/test-orders/'+self.oid+'/checkout')
            self.route(self.buyer, 'POST', '/api/top-up/test-orders/'+self.oid+'/cancel')
            self.db.execute('BEGIN IMMEDIATE')
            app.rewards_engine.sync_topup(self.db, self.oid, vars(app))
            self.db.execute('COMMIT')
            self.assertEqual(self.route(self.buyer, 'GET', '/api/rewards')['available_micro'], 1000000)
            intent = {'id': 'pi_credit_topup', 'livemode': False, 'status': 'succeeded', 'amount_received': 1600000,
                'currency': 'uzs', 'latest_charge': {'id': 'ch_credit_topup', 'livemode': False, 'refunded': False, 'disputed': False}}
            self.session = {'id': 'cs_test_credit_topup', 'livemode': False, 'client_reference_id': self.oid,
                'amount_total': 1600000, 'currency': 'uzs', 'payment_status': 'paid', 'payment_intent': intent,
                'metadata': {'sentryloot_mode': 'stripe_test', 'sentryloot_kind': 'topup', 'sentryloot_order': self.oid}}
            provider.client.v1.checkout.sessions.retrieve.return_value = self.session
            provider.client.v1.payment_intents.retrieve.return_value = intent
            self.pay()
            self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'succeeded')
            self.assertEqual(provider.client.v1.refunds.create.call_args.args[0]['amount'], 1600000)
            self.assertEqual(self.route(self.buyer, 'GET', '/api/rewards')['available_micro'], 1000000)

    def test_topup_dashboard_refund_and_dispute_reconcile_verified_charged_amount(self):
        stripe_fixtures.StripeTestFlows.topup_order(self)
        # Use an independently specified platform discount: gross remains 20k,
        # while the verified charge and eventual refund are 15k.
        self.session['amount_total'] = 1500000
        self.session['payment_intent']['amount_received'] = 1500000
        promotion = {'gross_total_minor': 20000, 'discount_minor': 5000, 'bonus_minor': 0, 'total_minor': 15000}
        with patch.object(app.rewards_engine, 'purchase', return_value=promotion), patch.object(app.rewards_engine, 'sync_topup') as sync:
            self.pay()
            charge = {'id': 'ch_topup', 'livemode': False, 'payment_intent': 'pi_topup',
                      'currency': 'uzs', 'amount': 1500000, 'amount_refunded': 0}
            self.provider.client.v1.charges.retrieve.return_value = charge
            dispute = {'id': 'dp_rewards', 'livemode': False, 'charge': 'ch_topup'}
            body, headers = self.signed('evt_rewards_dispute', 'charge.dispute.created', dispute)
            payments.webhook(self.db, headers, body, vars(app))
            self.assertEqual(self.db.execute('SELECT status FROM topup_orders WHERE id=?', (self.oid,)).fetchone()['status'], 'disputed')
            self.assertEqual(sync.call_args.args[1], self.oid)
            charge['amount_refunded'] = 1500000
            body, headers = self.signed('evt_rewards_refunded', 'charge.refunded', charge)
            payments.webhook(self.db, headers, body, vars(app))
            self.assertTrue(payments.read(self.db, 'job:'+self.oid+':topup_refund')['external_refund'])
            self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'succeeded')
            self.provider.client.v1.refunds.create.assert_not_called()
            self.assertEqual(self.db.execute('SELECT status FROM topup_orders WHERE id=?', (self.oid,)).fetchone()['status'], 'refunded')
            self.assertTrue(payments.webhook(self.db, headers, body, vars(app))['duplicate'])



if __name__ == '__main__':
    unittest.main()
