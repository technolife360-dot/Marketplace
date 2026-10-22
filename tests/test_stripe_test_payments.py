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
            'amount_received': self.amount, 'currency': 'uzs',
            'latest_charge': {'id': 'ch_fixture', 'livemode': False, 'refunded': False, 'disputed': False, 'amount_refunded': 0}}
        self.session = {'id': 'cs_test_fixture', 'livemode': False, 'client_reference_id': self.oid,
            'metadata': {'sentryloot_mode': 'stripe_test', 'sentryloot_order': self.oid},
            'payment_status': 'paid', 'amount_total': self.amount, 'currency': 'uzs', 'payment_intent': intent}
        self.provider.client.v1.checkout.sessions.retrieve.return_value = self.session
        self.provider.client.v1.charges.retrieve.return_value = {'id': 'ch_fixture', 'livemode': False,
            'amount': self.amount, 'currency': 'uzs', 'balance_transaction': {'amount': self.amount, 'currency': 'uzs'}}
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

    def test_bad_signature_amount_currency_and_live_event_cannot_confirm_payment(self):
        self.configure(); self.order()
        raw, headers = self.signed()
        with self.assertRaises(app.HttpError): payments.webhook(self.db, headers, raw+b' ', vars(app))
        for field, value in (('amount_total', self.amount+1), ('currency', 'usd')):
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
        self.assertEqual(params['amount'], 45000)
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
            'amount': self.amount, 'amount_refunded': self.amount, 'currency': 'uzs'}
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
            'payment_intent': 'pi_fixture', 'amount': payment['amount_minor'], 'currency': 'uzs'}
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
        intent = {'id': 'pi_topup', 'livemode': False, 'amount_received': 20000, 'currency': 'uzs', 'status': 'succeeded',
                  'latest_charge': {'id': 'ch_topup', 'livemode': False, 'refunded': False, 'disputed': False}}
        self.session = {'id': 'cs_test_topup', 'livemode': False, 'client_reference_id': self.oid, 'amount_total': 20000,
            'currency': 'uzs', 'payment_status': 'paid', 'payment_intent': intent,
            'metadata': {'sentryloot_mode': 'stripe_test', 'sentryloot_kind': 'topup', 'sentryloot_order': self.oid}}
        self.provider.client.v1.checkout.sessions.retrieve.return_value = self.session
        return data

    def test_topup_purchase_delivery_confirmation_and_refund_are_test_only(self):
        self.topup_order()
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
        self.assertEqual(self.db.execute('SELECT status FROM topup_orders WHERE id=?', (self.oid,)).fetchone()['status'], 'refunded')
        current = self.db.execute('SELECT stock_on_hand,stock_reserved FROM topup_packages WHERE id=(SELECT package_id FROM topup_orders WHERE id=?)', (self.oid,)).fetchone()
        self.assertEqual(tuple(current), tuple(package))

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
