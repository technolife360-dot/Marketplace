"""Buyer/seller progression and test credits use an isolated DB and signed events."""
import json
import unittest

import app
import order_process
import stripe_test_payments as payments
from tests import test_marketplace as fixtures
from tests import test_stripe_test_payments as stripe_fixtures


class OrderProcessFlows(unittest.TestCase):
    setUp = fixtures.MarketplaceFlows.setUp
    tearDown = fixtures.MarketplaceFlows.tearDown
    ctx = fixtures.MarketplaceFlows.ctx
    route = fixtures.MarketplaceFlows.route
    configure = stripe_fixtures.StripeTestFlows.configure
    order = stripe_fixtures.StripeTestFlows.order
    signed = stripe_fixtures.StripeTestFlows.signed
    pay = stripe_fixtures.StripeTestFlows.pay

    def start(self):
        self.configure()
        self.db.execute("UPDATE listings SET currency='MYR',price_minor=12990 WHERE id=?", (self.listing,))
        self.order()
        self.session['currency'] = 'myr'
        self.session['payment_intent']['currency'] = 'myr'
        self.provider.client.v1.charges.retrieve.return_value.update(currency='myr')
        return self.oid

    def balance(self):
        return next(b for b in self.route(self.seller, 'GET', '/api/seller/test-wallet')['balances'] if b['currency'] == 'MYR')

    def finish(self):
        self.route(self.seller, 'POST', '/api/orders/'+self.oid+'/prepare')
        item = self.db.execute('SELECT id FROM order_items WHERE order_id=?', (self.oid,)).fetchone()['id']
        payload = {'item_id': item, 'delivery': 'Only a test delivery.', 'request_key': 'delivery_same_request'}
        self.route(self.seller, 'POST', '/api/orders/'+self.oid+'/deliver', payload)
        self.route(self.seller, 'POST', '/api/orders/'+self.oid+'/deliver', payload)
        self.route(self.buyer, 'POST', '/api/orders/'+self.oid+'/complete')

    def test_verified_stripe_payment_moves_pending_to_available_exactly_once(self):
        self.start()
        self.assertEqual(self.balance()['available_minor'], 0)
        self.assertEqual(self.balance()['pending_minor'], 0)
        with self.assertRaises(app.HttpError):
            self.route(self.seller, 'POST', '/api/orders/'+self.oid+'/prepare')
        self.pay(); self.pay()
        self.assertEqual(self.balance()['pending_minor'], 11691)
        self.assertEqual(self.balance()['available_minor'], 0)
        self.finish()
        self.assertEqual(self.balance()['pending_minor'], 0)
        self.assertEqual(self.balance()['available_minor'], 11691)
        self.assertEqual(self.route(self.seller, 'GET', '/api/seller/summary')['wallet']['available_minor'], 0)
        order = self.route(self.seller, 'GET', '/api/orders/'+self.oid)
        self.assertEqual(order['funds']['state'], 'available')
        self.assertEqual(order['funds']['seller_net_minor'], 11691)
        self.assertTrue(order['funds']['test_only'])
        with self.assertRaises(app.HttpError):
            self.route(self.buyer, 'POST', '/api/orders/'+self.oid+'/complete')
        self.assertEqual(self.balance()['available_minor'], 11691)
        self.provider.client.v1.transfers.create.assert_not_called()

    def test_payout_reserves_once_and_failure_returns_only_reserved_test_credit(self):
        self.start(); self.pay(); self.finish()
        request = {'amount_minor': 10000, 'currency': 'MYR', 'request_key': 'wallet_request_00001', 'test_only': True}
        payout = self.route(self.seller, 'POST', '/api/seller/test-wallet/payouts', request)
        self.assertEqual(self.route(self.seller, 'POST', '/api/seller/test-wallet/payouts', request)['id'], payout['id'])
        self.assertEqual(self.balance()['available_minor'], 1691)
        self.assertEqual(self.balance()['payout_processing_minor'], 10000)
        with self.assertRaises(app.HttpError):
            self.route(self.seller, 'POST', '/api/seller/test-wallet/payouts', {**request, 'request_key': 'wallet_request_00002'})
        result_url = '/api/seller/test-wallet/payouts/'+payout['id']
        with self.assertRaises(app.HttpError):
            self.route(self.buyer, 'POST', result_url, {'outcome': 'paid', 'test_only': True})
        self.route(self.seller, 'POST', result_url, {'outcome': 'failed', 'test_only': True})
        self.route(self.seller, 'POST', result_url, {'outcome': 'failed', 'test_only': True})
        self.assertEqual(self.balance()['available_minor'], 11691)
        with self.assertRaises(app.HttpError):
            self.route(self.seller, 'POST', result_url, {'outcome': 'paid', 'test_only': True})
        self.provider.client.v1.payouts.create.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM payout_requests').fetchone()['n'], 0)

    def test_simulated_paid_payout_cannot_spend_same_balance_again(self):
        self.start(); self.pay(); self.finish()
        data = {'amount_minor': 11691, 'currency': 'MYR', 'request_key': 'wallet_request_paid01', 'test_only': True}
        p = self.route(self.seller, 'POST', '/api/seller/test-wallet/payouts', data)
        self.route(self.seller, 'POST', '/api/seller/test-wallet/payouts/'+p['id'], {'outcome': 'paid', 'test_only': True})
        self.assertEqual(self.balance()['available_minor'], 0)
        self.assertEqual(self.balance()['paid_out_minor'], 11691)
        self.assertEqual(self.balance()['payout_processing_minor'], 0)

    def test_refund_request_freezes_available_and_confirmed_refund_reverses_it(self):
        self.start(); self.pay(); self.finish()
        payments.queue_refund(self.db, self.oid, vars(app))
        self.assertEqual(self.balance()['available_minor'], 0)
        self.assertEqual(self.balance()['pending_minor'], 11691)
        payments.process(self.db, vars(app))
        self.assertEqual(self.balance()['available_minor'], 0)
        self.assertEqual(self.balance()['pending_minor'], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM ledger_entries WHERE entry_type=?', ('seller_earning',)).fetchone()['n'], 0)

    def test_dispute_and_currency_boundaries_prevent_test_payouts(self):
        self.start(); self.pay()
        with self.assertRaises(app.HttpError):
            self.route(self.other, 'POST', '/api/orders/'+self.oid+'/prepare')
        self.route(self.buyer, 'POST', '/api/orders/'+self.oid+'/dispute', {'details': 'Test problem with purchased item.'})
        self.assertEqual(self.balance()['available_minor'], 0)
        with self.assertRaises(app.HttpError):
            self.route(self.seller, 'POST', '/api/seller/test-wallet/payouts', {'amount_minor': 1, 'currency': 'UZS', 'request_key': 'currency_request_0001', 'test_only': True})
        with self.assertRaises(app.HttpError):
            self.route(self.seller, 'POST', '/api/payouts', {'amount_minor': 1, 'currency': 'UZS'})

    def test_return_to_order_reconciles_real_server_session_without_browser_paid_flag(self):
        self.start()
        self.route(self.buyer, 'POST', '/api/orders/'+self.oid+'/stripe-confirmation', {'paid': True})
        self.assertEqual(self.balance()['pending_minor'], 11691)
        self.assertEqual(self.provider.client.v1.checkout.sessions.retrieve.call_count, 2)
        self.route(self.buyer, 'POST', '/api/orders/'+self.oid+'/stripe-confirmation')
        self.pay()
        self.assertEqual(self.balance()['pending_minor'], 11691)
        with self.assertRaises(app.HttpError):
            self.route(self.other, 'POST', '/api/orders/'+self.oid+'/stripe-confirmation')

    def test_unpaid_session_never_credits_wallet_on_return(self):
        self.start()
        self.session['payment_status'] = 'unpaid'
        result = self.route(self.buyer, 'POST', '/api/orders/'+self.oid+'/stripe-confirmation', {'paid': True})
        self.assertEqual(result['status'], 'pending_payment')
        self.assertEqual(self.balance()['pending_minor'], 0)

    def test_checkout_retry_and_changed_quote_do_not_create_extra_orders(self):
        self.configure()
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)', (self.buyer, self.listing))
        data = {'accept_terms': True, 'accept_account_risk': True, 'expected_total_minor': 55000,
            'expected_currency': 'UZS', 'request_key': 'checkout_request_0001'}
        first = self.route(self.buyer, 'POST', '/api/checkout', data)
        retry = self.route(self.buyer, 'POST', '/api/checkout', data)
        self.assertEqual(first['id'], retry['id'])
        self.assertTrue(retry['idempotent'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM orders').fetchone()['n'], 1)
        with self.assertRaises(app.HttpError):
            self.route(self.buyer, 'POST', '/api/checkout', {**data, 'expected_total_minor': 50000})

    def test_stripe_review_cannot_fall_back_to_the_local_payment_simulator(self):
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)', (self.buyer, self.listing))
        with self.assertRaises(app.HttpError) as error:
            self.route(self.buyer, 'POST', '/api/checkout', {'accept_terms': True,
                'accept_account_risk': True, 'stripe_test_only': True})
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM orders').fetchone()['n'], 0)

    def test_test_review_stays_out_of_public_reviews(self):
        self.start(); self.pay(); self.finish()
        path = '/api/orders/'+self.oid+'/test-review'
        self.route(self.buyer, 'POST', path, {'rating': 5, 'body': 'This is a private test review.'})
        self.route(self.buyer, 'POST', path, {'rating': 4, 'body': 'Updated test review.'})
        self.assertEqual(self.route(self.buyer, 'GET', path)['rating'], 4)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM reviews').fetchone()['n'], 0)
        with self.assertRaises(app.HttpError):
            self.route(self.other, 'GET', path)

    def test_required_review_is_buyer_scoped_and_clears_only_after_valid_save(self):
        self.start(); self.pay()
        pending = '/api/orders/review-required'
        self.assertIsNone(self.route(self.buyer, 'GET', pending)['order_id'])
        self.finish()
        self.assertEqual(self.route(self.buyer, 'GET', pending)['order_id'], self.oid)
        self.assertIsNone(self.route(self.seller, 'GET', pending)['order_id'])
        self.assertIsNone(self.route(self.other, 'GET', pending)['order_id'])
        with self.assertRaises(app.HttpError):
            self.route(None, 'GET', pending)
        path = '/api/orders/'+self.oid+'/test-review'
        for data in ({'body': 'A clear review.'}, {'rating': 0, 'body': 'A clear review.'}, {'rating': 5, 'body': '   '}, {'rating': 1, 'body': 'bad'}):
            with self.assertRaises(app.HttpError): self.route(self.buyer, 'POST', path, data)
            self.assertEqual(self.route(self.buyer, 'GET', pending)['order_id'], self.oid)
        self.route(self.buyer, 'POST', path, {'rating': 1, 'body': 'Delivery was slower than expected.'})
        self.assertIsNone(self.route(self.buyer, 'GET', pending)['order_id'])
        self.assertEqual(self.route(self.buyer, 'GET', path)['rating'], 1)

    def test_purchased_last_unit_disappears_from_catalogue_saved_and_related_cards(self):
        self.start()
        other = app.ident()
        self.db.execute("""INSERT INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,currency,stock,status)
            SELECT ?,seller_id,game_id,category_id,'Another available item',description,product_type,price_minor,currency,2,'published'
            FROM listings WHERE id=?""", (other, self.listing))
        self.db.execute('INSERT INTO favorites(user_id,listing_id) VALUES(?,?)', (self.buyer, self.listing))
        self.db.execute("INSERT INTO account_collections(user_id,kind,listing_id) VALUES(?,'compare',?)", (self.buyer, self.listing))
        self.pay()
        self.assertNotIn(self.listing, [i['id'] for i in self.route(None, 'GET', '/api/listings')['items']])
        self.assertEqual(self.route(self.buyer, 'GET', '/api/favorites'), [])
        self.assertEqual(self.route(self.buyer, 'GET', '/api/collections/compare')['ids'], [])
        self.assertNotIn(self.listing, [i['id'] for i in self.route(None, 'GET', '/api/listings/'+other)['related']])
        self.assertEqual(self.route(self.buyer, 'GET', '/api/listings/'+self.listing)['status'], 'sold_out')
        self.assertEqual(len(self.route(self.buyer, 'GET', '/api/orders/'+self.oid)['items']), 1)
        # Hidden cards do not delete the listing or the user's saved reference.
        self.db.execute("UPDATE listings SET status='published',stock=2,reserved=0 WHERE id=?", (self.listing,))
        self.assertIn(self.listing, [i['id'] for i in self.route(None, 'GET', '/api/listings')['items']])
        self.assertEqual(self.route(self.buyer, 'GET', '/api/collections/compare')['ids'], [self.listing])

    def test_wallet_ownership_is_exact_even_when_user_id_contains_like_wildcards(self):
        p = {'id': 'a'*32, 'seller_id': 'sellerXtest', 'amount_minor': 10000,
             'currency': 'MYR', 'status': 'processing', 'created_at': app.now_iso()}
        self.db.execute('INSERT INTO platform_config(key,value) VALUES(?,?)',
                        (order_process.PAYOUT_PREFIX+'sellerXtest:request', json.dumps(p)))
        result = order_process.wallet(self.db, 'seller_test')
        self.assertEqual(result['payouts'], [])
        self.assertEqual(result['balances'][0]['available_minor'], 0)


if __name__ == '__main__':
    unittest.main()
