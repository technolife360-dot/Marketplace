"""Test payment state transitions using real webhook signatures and isolated DBs."""
import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import Mock, patch

import app
import stripe_test_payments as payments
from tests import test_marketplace as fixtures
from tests.test_http_workflows import BrowserClient


class StripeTestFlows(unittest.TestCase):
    setUp = fixtures.MarketplaceFlows.setUp
    tearDown = fixtures.MarketplaceFlows.tearDown
    ctx = fixtures.MarketplaceFlows.ctx
    route = fixtures.MarketplaceFlows.route

    def configure(self):
        env = patch.dict(os.environ, {'PAYMENT_PROVIDER': 'stripe_test',
            'STRIPE_TEST_SECRET_KEY': 'sk_test_fixture_not_a_real_key',
            'STRIPE_TEST_ACCOUNT_ID': 'acct_testfixture',
            'STRIPE_TEST_WEBHOOK_SECRET': 'whsec_fixture_not_a_real_secret',
            'PUBLIC_BASE_URL': 'https://test.example.invalid'})
        env.start(); self.addCleanup(env.stop)
        provider = payments.StripeTestProvider()
        provider.client = Mock()
        provider.client.v1.accounts.retrieve_current.return_value = {'id': 'acct_testfixture'}
        provider.client.v1.accounts.retrieve.return_value = {'id': 'acct_seller', 'controller': {'is_controller': True}, 'capabilities': {'transfers': 'active'}}
        provider.client.v1.transfers.list.return_value = {'data': [], 'has_more': False}
        provider.client.v1.refunds.list.return_value = {'data': [], 'has_more': False}
        provider.client.v1.refunds.create.return_value = {'id': 're_fixture', 'status': 'succeeded'}
        provider.client.v1.transfers.create.return_value = {'id': 'tr_fixture', 'livemode': False}
        patcher = patch.object(app, 'configured_payment_provider', return_value=provider)
        patcher.start(); self.addCleanup(patcher.stop)
        self.provider = provider
        return provider

    def order(self):
        self.db.execute("UPDATE listings SET product_type='item' WHERE id=?", (self.listing,))
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)', (self.buyer, self.listing))
        result = app.checkout(self.db, self.buyer, True, True)
        self.oid = result['id']; self.amount = result['total_minor']
        currency = result['currency'].lower()
        external_amount = self.amount*100 if currency == 'uzs' else self.amount
        item = self.db.execute('SELECT id,snapshot_json FROM order_items WHERE order_id=?', (self.oid,)).fetchone()
        snapshot = json.loads(item['snapshot_json'])
        fields = {field['key']: 'Test fixture' for field in snapshot.get('buyer_fields', [])}
        if fields:
            app.trade_workflows.store_details(self.db, item['id'], fields, vars(app))
        self.provider.client.v1.checkout.sessions.create.return_value = {
            'id': 'cs_test_fixture', 'livemode': False, 'url': 'https://checkout.stripe.com/c/pay/cs_test_fixture',
            'expires_at': int(time.time())+1800}
        payments.start_checkout(self.db, self.oid, self.buyer, vars(app))
        intent = {'id': 'pi_fixture', 'status': 'succeeded', 'livemode': False,
            'amount_received': external_amount, 'currency': currency,
            'latest_charge': {'id': 'ch_fixture', 'livemode': False, 'refunded': False, 'disputed': False, 'amount_refunded': 0}}
        self.session = {'id': 'cs_test_fixture', 'livemode': False, 'client_reference_id': self.oid,
            'metadata': {'sentryloot_mode': 'stripe_test', 'sentryloot_order': self.oid},
            'payment_status': 'paid', 'amount_total': external_amount, 'currency': currency, 'payment_intent': intent}
        self.provider.client.v1.checkout.sessions.retrieve.return_value = self.session
        self.provider.client.v1.payment_intents.retrieve.return_value = intent
        self.provider.client.v1.charges.retrieve.return_value = {'id': 'ch_fixture', 'livemode': False,
            'amount': external_amount, 'currency': currency, 'balance_transaction': {'amount': external_amount, 'currency': currency}}
        return result

    def signed(self, event_id='evt_fixture', kind='checkout.session.completed', session=None):
        body = json.dumps({'id': event_id, 'object': 'event', 'type': kind, 'livemode': False,
                           'data': {'object': session or self.session}}).encode()
        stamp = str(int(time.time()))
        digest = hmac.new(self.provider.secret.encode(), stamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
        return body, {'Stripe-Signature': 't='+stamp+',v1='+digest}

    def pay(self):
        raw, headers = self.signed()
        return payments.webhook(self.db, headers, raw, vars(app))

    def test_live_credentials_and_misbound_accounts_are_rejected(self):
        provider = self.configure()
        with patch.dict(os.environ, {'STRIPE_TEST_SECRET_KEY': 'sk_live_never_allowed'}):
            with self.assertRaises(RuntimeError): payments.StripeTestProvider()
        provider.client.v1.accounts.retrieve_current.return_value = {'id': 'acct_wrong'}
        with self.assertRaises(RuntimeError): provider.session('order', 500, 'USD', 'idem')
        provider.client.v1.checkout.sessions.create.assert_not_called()
        with patch.object(app, 'MODE', 'production'), patch.dict(os.environ, {'MARKETPLACE_SALES_ENABLED': 'true', 'MARKETPLACE_INTERNAL_TESTING_ENABLED': 'true'}):
            self.assertFalse(app.production_marketplace_sales_enabled())
            self.assertTrue(app.internal_testing_enabled())

    def test_checkout_converts_whole_som_but_preserves_ringgit_cents(self):
        provider = self.configure()
        provider.client.v1.checkout.sessions.create.return_value = {
            'id': 'cs_test_units', 'livemode': False, 'url': 'https://checkout.stripe.com/c/pay/cs_test_units'}
        for currency, internal, stripe_amount in [('UZS', 96000, 9600000), ('MYR', 30000, 30000)]:
            with self.subTest(currency=currency):
                provider.session('order', internal, currency, 'units_'+currency)
                price = provider.client.v1.checkout.sessions.create.call_args.args[0]['line_items'][0]['price_data']
                self.assertEqual(price['unit_amount'], stripe_amount)
                self.assertEqual(price['currency'], currency.lower())

    def test_invalid_or_unknown_internal_currency_amounts_fail_before_checkout(self):
        provider = self.configure()
        for amount, currency in [(True, 'UZS'), (False, 'MYR'), (0, 'UZS'), (-1, 'UZS'),
                                 (1.5, 'UZS'), ('96000', 'UZS'), (96000, 'JPY'),
                                 (96000, 'uzs'), (96000, None)]:
            with self.subTest(amount=amount, currency=currency):
                with self.assertRaises(RuntimeError):
                    provider.session('order', amount, currency, 'invalid')
                with self.assertRaises(RuntimeError):
                    provider.create_intent('order', amount, currency, 'invalid')
        provider.client.v1.checkout.sessions.create.assert_not_called()

    def test_old_undercharged_checkout_is_rejected_without_creating_another_charge(self):
        provider = self.configure(); self.order()
        self.session['amount_total'] = self.amount
        self.session['payment_intent']['amount_received'] = self.amount
        provider.client.v1.checkout.sessions.create.reset_mock()
        with self.assertRaises(app.HttpError) as error:
            payments.reconcile_checkout(self.db, self.oid, self.buyer, vars(app))
        self.assertEqual(error.exception.status, 409)
        provider.client.v1.checkout.sessions.create.assert_not_called()
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (self.oid,)).fetchone()['status'], 'pending_payment')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM ledger_entries').fetchone()['n'], 0)

    def test_refund_converts_using_verified_intent_currency(self):
        provider = self.configure()
        for currency, internal, external in [('uzs', 96000, 9600000), ('myr', 30000, 30000)]:
            with self.subTest(currency=currency):
                provider.client.v1.payment_intents.retrieve.return_value = {
                    'id': 'pi_units', 'livemode': False, 'currency': currency, 'amount_received': external}
                provider.refund('pi_units', internal, 'refund_units_'+currency)
                self.assertEqual(provider.client.v1.refunds.create.call_args.args[0]['amount'], external)
                provider.client.v1.refunds.list.return_value = {
                    'data': [{'id': 're_units', 'status': 'succeeded', 'amount': external}], 'has_more': False}
                provider.client.v1.refunds.create.reset_mock()
                self.assertEqual(provider.refund('pi_units', internal, 'refund_units_'+currency)['id'], 're_units')
                provider.client.v1.refunds.create.assert_not_called()
                provider.client.v1.refunds.list.return_value = {'data': [], 'has_more': False}

    def test_refund_rejects_legacy_undercharge_unknown_currency_and_live_intent(self):
        provider = self.configure()
        for overrides in [{'amount_received': 96000}, {'currency': 'jpy'}, {'livemode': True}, {'id': 'pi_wrong'}]:
            provider.client.v1.payment_intents.retrieve.return_value = {
                'id': 'pi_units', 'livemode': False, 'currency': 'uzs', 'amount_received': 9600000, **overrides}
            with self.subTest(overrides=overrides), self.assertRaises(RuntimeError):
                provider.refund('pi_units', 96000, 'refund_units')
        provider.client.v1.refunds.create.assert_not_called()

    def test_uzs_seller_transfer_uses_actual_myr_settlement_ratio(self):
        provider = self.configure()
        provider.client.v1.charges.retrieve.return_value = {
            'id': 'ch_units', 'livemode': False, 'currency': 'uzs', 'amount': 9600000,
            'balance_transaction': {'amount': 3200, 'currency': 'myr'}}
        provider.transfer('order', self.seller, 'acct_seller', 'ch_units', 72000, 'UZS')
        params = provider.client.v1.transfers.create.call_args.args[0]
        self.assertEqual(params['amount'], 2400)
        self.assertEqual(params['currency'], 'myr')

    def test_myr_checkout_webhook_and_refund_keep_the_same_cent_amount(self):
        provider = self.configure()
        self.db.execute("UPDATE listings SET price_minor=30000,currency='MYR' WHERE id=?", (self.listing,))
        self.order()
        self.assertEqual(self.amount, 33000)
        price = provider.client.v1.checkout.sessions.create.call_args.args[0]['line_items'][0]['price_data']
        self.assertEqual(price['unit_amount'], 33000)
        self.pay()
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (self.oid,)).fetchone()['status'], 'paid')
        payments.queue_refund(self.db, self.oid, vars(app))
        self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'succeeded')
        self.assertEqual(provider.client.v1.refunds.create.call_args.args[0]['amount'], 33000)

    def test_payout_amount_is_already_stripe_minor_units_even_for_uzs(self):
        provider = self.configure()
        payments.write(self.db, 'seller:'+self.seller, {'id': 'acct_seller'})
        provider.client.v1.payouts.create.return_value = {
            'id': 'po_units', 'livemode': False, 'status': 'pending', 'amount': 96000, 'currency': 'uzs'}
        self.route(self.seller, 'POST', '/api/seller/stripe-test/payout', {
            'amount_minor': 96000, 'currency': 'UZS', 'request_key': 'payout_units_fixture_0001', 'test_only': True})
        self.assertEqual(provider.client.v1.payouts.create.call_args.args[0]['amount'], 96000)

    def test_checkout_network_is_outside_stock_transaction_and_retry_reuses_order(self):
        provider = self.configure()
        def create(params, options):
            self.assertFalse(self.db.in_transaction)
            return {'id': 'cs_test_fixture', 'livemode': False, 'url': 'https://checkout.stripe.com/c/pay/cs_test_fixture', 'expires_at': int(time.time())+1800}
        self.order()
        provider.client.v1.checkout.sessions.create.reset_mock()
        first = payments.start_checkout(self.db, self.oid, self.buyer, vars(app))
        self.assertIn('checkout.stripe.com', first['checkout_url'])
        provider.client.v1.checkout.sessions.create.assert_not_called()
        with self.assertRaises(app.HttpError) as err: payments.start_checkout(self.db, self.oid, self.other, vars(app))
        self.assertEqual(err.exception.status, 404)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM orders').fetchone()['n'], 1)
        self.db.execute('DELETE FROM platform_config WHERE key=?', (payments.PREFIX+'checkout:'+self.oid,))
        provider.client.v1.checkout.sessions.create.side_effect = create
        payments.start_checkout(self.db, self.oid, self.buyer, vars(app))

    def test_checkout_retry_reuses_identical_stripe_parameters_after_transient_failure(self):
        provider=self.configure();self.order()
        self.db.execute('DELETE FROM platform_config WHERE key IN (?,?)',
            (payments.PREFIX+'checkout:'+self.oid,payments.PREFIX+'checkout_attempt:'+self.oid))
        provider.client.v1.checkout.sessions.create.reset_mock()
        provider.client.v1.checkout.sessions.create.side_effect=[
            TimeoutError('temporary network failure'),
            {'id':'cs_test_retry','livemode':False,
             'url':'https://checkout.stripe.com/c/pay/cs_test_retry',
             'expires_at':int(time.time())+1800}]
        with self.assertRaises(app.HttpError) as error:
            payments.start_checkout(self.db,self.oid,self.buyer,vars(app))
        self.assertEqual(error.exception.status,503)
        first=provider.client.v1.checkout.sessions.create.call_args
        payments.start_checkout(self.db,self.oid,self.buyer,vars(app))
        second=provider.client.v1.checkout.sessions.create.call_args
        self.assertEqual(first.args,second.args)
        self.assertEqual(first.kwargs,second.kwargs)
        self.assertTrue(first.kwargs['options']['idempotency_key'].startswith('checkout:v2:'))

    def test_expired_checkout_releases_stock_restores_cart_once_and_explains_retry(self):
        self.configure(); self.order()
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,2)',(self.buyer,self.listing))
        self.db.execute('UPDATE platform_config SET value=? WHERE key=?',
            (json.dumps({'id':'cs_test_fixture','url':'https://checkout.stripe.com/c/pay/cs_test_fixture','expires_at':int(time.time())-1}),
             payments.PREFIX+'checkout:'+self.oid))
        with self.assertRaises(app.HttpError) as error:
            payments.start_checkout(self.db,self.oid,self.buyer,vars(app))
        self.assertEqual(error.exception.status,409)
        self.assertIn('back in your cart',error.exception.message)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?',(self.oid,)).fetchone()['status'],'cancelled')
        self.assertEqual(self.db.execute('SELECT status FROM payments WHERE order_id=?',(self.oid,)).fetchone()['status'],'expired')
        self.assertEqual(self.db.execute('SELECT reserved FROM listings WHERE id=?',(self.listing,)).fetchone()['reserved'],0)
        self.assertEqual(self.db.execute('SELECT quantity FROM carts WHERE user_id=? AND listing_id=?',(self.buyer,self.listing)).fetchone()['quantity'],2)
        with self.assertRaises(app.HttpError):
            payments.start_checkout(self.db,self.oid,self.buyer,vars(app))
        self.assertEqual(self.db.execute('SELECT quantity FROM carts WHERE user_id=? AND listing_id=?',(self.buyer,self.listing)).fetchone()['quantity'],2)

    def test_stripe_expiry_webhook_restores_order_items_to_the_cart(self):
        self.configure(); self.order()
        expired={'id':'cs_test_fixture','livemode':False,'client_reference_id':self.oid,
            'metadata':{'sentryloot_mode':'stripe_test','sentryloot_order':self.oid},'payment_status':'unpaid'}
        raw,headers=self.signed('evt_checkout_expired','checkout.session.expired',expired)
        self.assertTrue(payments.webhook(self.db,headers,raw,vars(app))['ok'])
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?',(self.oid,)).fetchone()['status'],'cancelled')
        self.assertEqual(self.db.execute('SELECT status FROM payments WHERE order_id=?',(self.oid,)).fetchone()['status'],'expired')
        self.assertEqual(self.db.execute('SELECT quantity FROM carts WHERE user_id=? AND listing_id=?',(self.buyer,self.listing)).fetchone()['quantity'],1)

    def test_reopening_a_previously_expired_order_repairs_legacy_cart_once(self):
        self.configure(); self.order()
        self.db.execute("UPDATE orders SET status='cancelled' WHERE id=?",(self.oid,))
        self.db.execute("UPDATE payments SET status='expired' WHERE order_id=?",(self.oid,))
        with self.assertRaises(app.HttpError) as error:
            payments.start_checkout(self.db,self.oid,self.buyer,vars(app))
        self.assertEqual(error.exception.status,409)
        self.assertEqual(self.db.execute('SELECT quantity FROM carts WHERE user_id=? AND listing_id=?',(self.buyer,self.listing)).fetchone()['quantity'],1)
        with self.assertRaises(app.HttpError):
            payments.start_checkout(self.db,self.oid,self.buyer,vars(app))
        self.assertEqual(self.db.execute('SELECT quantity FROM carts WHERE user_id=? AND listing_id=?',(self.buyer,self.listing)).fetchone()['quantity'],1)

    def test_payment_is_verified_once_and_held_until_delivery(self):
        provider = self.configure(); self.order()
        with self.assertRaises(app.HttpError): self.route(self.buyer, 'POST', '/api/orders/'+self.oid+'/sandbox-complete')
        self.assertTrue(self.pay()['ok'])
        count = self.db.execute('SELECT COUNT(*) n FROM ledger_entries').fetchone()['n']
        self.assertTrue(self.pay()['duplicate'])
        raw, headers = self.signed('evt_same_payment_new_id')
        payments.webhook(self.db, headers, raw, vars(app))
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM ledger_entries').fetchone()['n'], count)
        self.assertEqual(self.db.execute('SELECT stock,reserved FROM listings WHERE id=?', (self.listing,)).fetchone()['stock'], 0)
        held = self.db.execute("SELECT SUM(amount_minor) n FROM ledger_entries WHERE order_id=?", (self.oid,)).fetchone()['n']
        self.assertEqual(held, self.amount)
        provider.client.v1.transfers.create.assert_not_called()
        with self.assertRaises(app.HttpError): self.route(self.buyer, 'POST', '/api/orders/'+self.oid+'/complete')
        self.assertEqual(payments.process(self.db, vars(app))['jobs'], [])

    def test_amount_below_stripe_minimum_cancels_order_and_restores_cart(self):
        provider = self.configure(); self.order()
        self.db.execute('DELETE FROM platform_config WHERE key=?', (payments.PREFIX+'checkout:'+self.oid,))
        class AmountTooSmall(Exception):
            code = 'amount_too_small'
        provider.client.v1.checkout.sessions.create.side_effect = AmountTooSmall('minimum amount')
        with self.assertRaises(app.HttpError) as err:
            payments.start_checkout(self.db, self.oid, self.buyer, vars(app))
        self.assertEqual(err.exception.status, 400)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (self.oid,)).fetchone()['status'], 'cancelled')
        self.assertEqual(self.db.execute('SELECT status FROM payments WHERE order_id=?', (self.oid,)).fetchone()['status'], 'failed')
        self.assertEqual(self.db.execute('SELECT reserved FROM listings WHERE id=?', (self.listing,)).fetchone()['reserved'], 0)
        self.assertEqual(self.db.execute('SELECT quantity FROM carts WHERE user_id=? AND listing_id=?', (self.buyer, self.listing)).fetchone()['quantity'], 1)

    def test_bad_signature_amount_currency_and_live_event_cannot_confirm_payment(self):
        self.configure(); self.order()
        raw, headers = self.signed()
        with self.assertRaises(app.HttpError): payments.webhook(self.db, headers, raw+b' ', vars(app))
        for field, value in (('amount_total', self.amount+1), ('amount_total', float(self.amount*100)), ('amount_total', True), ('currency', 'usd')):
            old = self.session[field]; self.session[field] = value
            raw, headers = self.signed()
            with self.assertRaises(app.HttpError): payments.webhook(self.db, headers, raw, vars(app))
            self.session[field] = old
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (self.oid,)).fetchone()['status'], 'pending_payment')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM ledger_entries').fetchone()['n'], 0)

    def test_complete_transfers_only_to_linked_seller_and_never_to_live_wallet(self):
        provider = self.configure(); self.order(); self.pay()
        item = self.db.execute('SELECT id FROM order_items WHERE order_id=?', (self.oid,)).fetchone()['id']
        self.route(self.seller, 'POST', '/api/orders/'+self.oid+'/deliver', {'item_id': item, 'delivery': 'Test delivery only'})
        self.route(self.buyer, 'POST', '/api/orders/'+self.oid+'/complete')
        self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'retry')
        self.route(self.admin, 'POST', '/api/admin/payments/stripe-test/sellers/'+self.seller, {'account_id': 'acct_seller'})
        self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'succeeded')
        params = provider.client.v1.transfers.create.call_args.args[0]
        self.assertEqual(params['amount'], 4500000)
        self.assertEqual(params['source_transaction'], 'ch_fixture')
        self.assertEqual(params['destination'], 'acct_seller')
        payments.process(self.db, vars(app))
        self.assertEqual(provider.client.v1.transfers.create.call_count, 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM ledger_entries WHERE entry_type='seller_earning'").fetchone()['n'], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM bonus_entries WHERE mode='real'").fetchone()['n'], 0)

    def test_refund_remains_pending_until_confirmed_and_restocks_once(self):
        provider = self.configure(); self.order(); self.pay()
        payments.queue_refund(self.db, self.oid, vars(app))
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (self.oid,)).fetchone()['status'], 'refund_pending')
        provider.client.v1.refunds.create.return_value = {'id': 're_fixture', 'status': 'pending'}
        self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'retry')
        self.assertEqual(self.db.execute('SELECT stock FROM listings WHERE id=?', (self.listing,)).fetchone()['stock'], 0)
        provider.client.v1.refunds.create.return_value = {'id': 're_fixture', 'status': 'succeeded'}
        self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'succeeded')
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (self.oid,)).fetchone()['status'], 'refunded')
        payments.process(self.db, vars(app)); self.pay()
        self.assertEqual(self.db.execute('SELECT stock FROM listings WHERE id=?', (self.listing,)).fetchone()['stock'], 1)
        self.assertEqual(self.db.execute('SELECT SUM(amount_minor) n FROM ledger_entries').fetchone()['n'], 0)

    def test_dashboard_refund_reconciles_without_issuing_a_second_refund(self):
        provider = self.configure(); self.order(); self.pay()
        provider.client.v1.transfers.list.return_value = {'data': [
            {'id': 'tr_refunded_order', 'livemode': False,
             'metadata': {'sentryloot_mode': 'stripe_test'}}], 'has_more': False}
        provider.client.v1.transfers.retrieve.return_value = {'id': 'tr_refunded_order', 'livemode': False,
            'reversed': False, 'amount_reversed': 0}
        charge = {'id': 'ch_fixture', 'livemode': False, 'payment_intent': 'pi_fixture',
            'amount': self.amount*100, 'amount_refunded': self.amount*100, 'currency': 'uzs'}
        body, headers = self.signed('evt_dashboard_refund', 'charge.refunded', charge)
        self.assertTrue(payments.webhook(self.db, headers, body, vars(app))['ok'])
        self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'succeeded')
        provider.client.v1.refunds.create.assert_not_called()
        provider.client.v1.transfers.reversals.create.assert_called_once()
        self.assertEqual(self.db.execute('SELECT status FROM payments WHERE order_id=?', (self.oid,)).fetchone()['status'], 'refunded')
        self.assertEqual(self.db.execute('SELECT stock FROM listings WHERE id=?', (self.listing,)).fetchone()['stock'], 1)

    def test_charge_dispute_enqueues_transfer_reversal(self):
        provider = self.configure(); self.order(); self.pay()
        payment = self.db.execute('SELECT * FROM payments WHERE order_id=?', (self.oid,)).fetchone()
        self.db.execute("UPDATE orders SET status='completed' WHERE id=?", (self.oid,))
        self.db.execute("UPDATE payments SET status='succeeded' WHERE order_id=?", (self.oid,))
        payments.write(self.db, 'paid:'+self.oid, {'intent': 'pi_fixture', 'charge': 'ch_fixture'})
        payments.write(self.db, 'transfer:'+self.oid+':'+self.seller, {'id': 'tr_disputed', 'amount': 45000})
        provider.client.v1.transfers.list.return_value = {'data': [
            {'id': 'tr_disputed', 'livemode': False,
             'metadata': {'sentryloot_mode': 'stripe_test'}}], 'has_more': False}
        provider.client.v1.transfers.retrieve.return_value = {'id': 'tr_disputed', 'livemode': False,
            'reversed': False, 'amount_reversed': 0}
        provider.client.v1.charges.retrieve.return_value = {'id': 'ch_fixture', 'livemode': False,
            'payment_intent': 'pi_fixture', 'amount': payment['amount_minor']*100, 'currency': 'uzs'}
        body, headers = self.signed('evt_charge_dispute', 'charge.dispute.created', {'charge': 'ch_fixture', 'livemode': False})
        payments.webhook(self.db, headers, body, vars(app))
        result = payments.process(self.db, vars(app))
        self.assertEqual(result['jobs'][0]['kind'], 'dispute_reversal')
        self.assertEqual(result['jobs'][0]['status'], 'succeeded')
        provider.client.v1.transfers.reversals.create.assert_called_once()
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (self.oid,)).fetchone()['status'], 'disputed')

    def test_late_payment_is_refunded_without_delivering_or_double_restock(self):
        self.configure(); self.order()
        order = self.db.execute('SELECT * FROM orders WHERE id=?', (self.oid,)).fetchone()
        app.trade_workflows.cancel_settle(self.db, order, vars(app))
        self.pay()
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (self.oid,)).fetchone()['status'], 'refund_pending')
        payments.process(self.db, vars(app))
        self.assertEqual(self.db.execute('SELECT stock,reserved FROM listings WHERE id=?', (self.listing,)).fetchone()['stock'], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM ledger_entries').fetchone()['n'], 0)

    def test_wsgi_accepts_only_signed_raw_webhooks_and_protects_admin_actions(self):
        self.configure(); self.order()
        application = app.VercelWSGIApplication(); application._startup_complete = True
        guest = BrowserClient(application)
        raw, headers = self.signed()
        self.assertEqual(guest.request('POST', '/api/webhooks/stripe-test', raw=raw, headers=headers)[0], 200)
        self.assertEqual(guest.request('POST', '/api/webhooks/stripe-test', raw=raw)[0], 400)
        for path in ('/api/admin/payments/stripe-test/process', '/api/admin/payments/stripe-test/sellers/'+self.seller):
            self.assertEqual(guest.request('POST', path, {})[0], 401)
        self.assertEqual(guest.request('GET', '/api/cron/stripe-test-payments')[0], 401)

    def test_disputed_order_blocks_release_and_refund_reverses_external_transfer(self):
        provider = self.configure(); self.order(); self.pay()
        self.db.execute("UPDATE orders SET status='disputed' WHERE id=?", (self.oid,))
        payments.queue_release(self.db, self.oid)
        self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'blocked')
        provider.client.v1.transfers.create.assert_not_called()
        # Simulate recovery after a crash: Stripe holds a transfer even though
        # the local transfer record was not committed.
        provider.client.v1.transfers.list.return_value = {'data': [
            {'id': 'tr_recovered', 'livemode': False, 'metadata': {'sentryloot_mode': 'stripe_test'}}], 'has_more': False}
        provider.client.v1.transfers.retrieve.return_value = {'id': 'tr_recovered', 'livemode': False, 'reversed': False, 'amount_reversed': 0}
        payments.queue_refund(self.db, self.oid, vars(app))
        payments.process(self.db, vars(app))
        provider.client.v1.transfers.reversals.create.assert_called_once()
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (self.oid,)).fetchone()['status'], 'refunded')

    def topup_order(self):
        self.configure()
        package = self.db.execute("SELECT id FROM topup_packages WHERE game_slug='pubg-mobile' LIMIT 1").fetchone()['id']
        self.db.execute('UPDATE topup_packages SET price_minor=10000,enabled=1 WHERE id=?', (package,))
        data = {'package_id': package, 'player_id': '12345678', 'quantity': 2, 'request_key': 'topup_request_fixture_0001', 'accept_terms': True}
        result = self.route(self.buyer, 'POST', '/api/top-up/test-checkout', data)
        self.oid = result['id']; self.amount = 20000
        self.provider.client.v1.checkout.sessions.create.return_value = {
            'id': 'cs_test_topup', 'livemode': False, 'url': 'https://checkout.stripe.com/c/pay/cs_test_topup', 'expires_at': int(time.time())+1800}
        self.route(self.buyer, 'POST', '/api/top-up/test-orders/'+self.oid+'/checkout')
        intent = {'id': 'pi_topup', 'livemode': False, 'amount_received': 2000000, 'currency': 'uzs', 'status': 'succeeded',
                  'latest_charge': {'id': 'ch_topup', 'livemode': False, 'refunded': False, 'disputed': False}}
        self.session = {'id': 'cs_test_topup', 'livemode': False, 'client_reference_id': self.oid, 'amount_total': 2000000,
            'currency': 'uzs', 'payment_status': 'paid', 'payment_intent': intent,
            'metadata': {'sentryloot_mode': 'stripe_test', 'sentryloot_kind': 'topup', 'sentryloot_order': self.oid}}
        self.provider.client.v1.checkout.sessions.retrieve.return_value = self.session
        self.provider.client.v1.payment_intents.retrieve.return_value = intent
        return data

    def test_topup_purchase_delivery_confirmation_and_refund_are_test_only(self):
        self.topup_order()
        price = self.provider.client.v1.checkout.sessions.create.call_args.args[0]['line_items'][0]['price_data']
        self.assertEqual(price['unit_amount'], 2000000)
        package = self.db.execute('SELECT stock_on_hand,stock_reserved FROM topup_packages WHERE id=(SELECT package_id FROM topup_orders WHERE id=?)', (self.oid,)).fetchone()
        self.pay()
        order = self.route(self.buyer, 'GET', '/api/top-up/test-orders/'+self.oid)
        self.assertEqual(order['status'], 'paid_test'); self.assertFalse(order['real_delivery'])
        self.assertEqual(order['inventory_quantity'], 0); self.assertEqual(order['supplier_quantity'], 0)
        with self.assertRaises(app.HttpError): self.route(self.other, 'GET', '/api/top-up/test-orders/'+self.oid)
        with self.assertRaises(app.HttpError): self.route(self.buyer, 'POST', '/api/admin/payments/stripe-test/topups/'+self.oid+'/deliver')
        self.route(self.admin, 'POST', '/api/admin/payments/stripe-test/topups/'+self.oid+'/deliver')
        self.route(self.buyer, 'POST', '/api/top-up/test-orders/'+self.oid+'/confirm')
        row = self.db.execute('SELECT * FROM topup_orders WHERE id=?', (self.oid,)).fetchone()
        self.assertEqual(row['status'], 'completed'); self.assertIsNotNone(row['completed_at'])
        real = self.db.execute('SELECT COUNT(*) n FROM topup_orders o WHERE '+app.purchase_reviews.TOPUP_REAL).fetchone()['n']
        self.assertEqual(real, 0)
        self.route(self.buyer, 'POST', '/api/top-up/test-orders/'+self.oid+'/cancel')
        self.assertEqual(payments.process(self.db, vars(app))['jobs'][0]['status'], 'succeeded')
        self.assertEqual(self.provider.client.v1.refunds.create.call_args.args[0]['amount'], 2000000)
        self.assertEqual(self.db.execute('SELECT status FROM topup_orders WHERE id=?', (self.oid,)).fetchone()['status'], 'refunded')
        current = self.db.execute('SELECT stock_on_hand,stock_reserved FROM topup_packages WHERE id=(SELECT package_id FROM topup_orders WHERE id=?)', (self.oid,)).fetchone()
        self.assertEqual(tuple(current), tuple(package))

    def test_topup_undercharged_session_does_not_deliver_or_refund_automatically(self):
        self.topup_order()
        self.session['amount_total'] = 20000
        self.session['payment_intent']['amount_received'] = 20000
        with self.assertRaises(app.HttpError) as error:
            self.pay()
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.db.execute('SELECT status FROM topup_orders WHERE id=?', (self.oid,)).fetchone()['status'], 'awaiting_payment')
        self.provider.client.v1.refunds.create.assert_not_called()

    def test_topup_retries_are_idempotent_and_late_payment_auto_refunds(self):
        data = self.topup_order()
        self.assertEqual(self.route(self.buyer, 'POST', '/api/top-up/test-checkout', data)['id'], self.oid)
        with self.assertRaises(app.HttpError): self.route(self.buyer, 'POST', '/api/top-up/test-checkout', {**data, 'quantity': 3})
        self.route(self.buyer, 'POST', '/api/top-up/test-orders/'+self.oid+'/cancel')
        self.pay()
        self.assertEqual(self.db.execute('SELECT status FROM topup_orders WHERE id=?', (self.oid,)).fetchone()['status'], 'refund_pending')
        payments.process(self.db, vars(app))
        self.assertEqual(self.db.execute('SELECT status FROM topup_orders WHERE id=?', (self.oid,)).fetchone()['status'], 'refunded')


if __name__ == '__main__':
    unittest.main()
