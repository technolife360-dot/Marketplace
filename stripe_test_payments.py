"""Stripe sandbox checkout and a durable, idempotent settlement outbox.

No live credentials, live objects, supplier fulfillment, or bank payouts are
accepted here. Private integration records use the existing RLS-protected
platform_config store; Stripe's idempotency keys survive worker retries.
"""
import json
import os
import re
import time
from urllib.parse import urlsplit

from payment_providers import PaymentIntent

UNHANDLED = object()
PREFIX = 'stripe_test:'


def stripe_amount(amount, currency):
    """Convert the app's money convention to Stripe integer minor units.

    Existing UZS database amounts are whole som; MYR amounts already are sen.
    Reject other conventions rather than guessing their scale.
    """
    if type(amount) is not int or amount <= 0 or currency not in ('UZS', 'MYR'):
        raise RuntimeError('Invalid checkout amount or unsupported internal currency.')
    return amount*100 if currency == 'UZS' else amount


def matches_amount(amount, internal, currency):
    return type(amount) is int and amount == stripe_amount(internal, currency)


def read(db, key, default=None):
    row = db.execute('SELECT value FROM platform_config WHERE key=?', (PREFIX+key,)).fetchone()
    return json.loads(row['value']) if row else default


def write(db, key, value):
    db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP',
               (PREFIX+key, json.dumps(value, separators=(',', ':'))))


class StripeTestProvider:
    name = 'stripe_test'

    def __init__(self):
        key = os.environ.get('STRIPE_TEST_SECRET_KEY', '').strip()
        self.account = os.environ.get('STRIPE_TEST_ACCOUNT_ID', '').strip()
        self.secret = os.environ.get('STRIPE_TEST_WEBHOOK_SECRET', '').strip()
        self.base = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
        parsed = urlsplit(self.base)
        if not key.startswith(('sk_test_', 'rk_test_')) or not re.fullmatch(r'acct_[A-Za-z0-9]+', self.account):
            raise RuntimeError('Configure a Stripe test key and the sandbox account ID.')
        if not self.secret.startswith('whsec_'):
            raise RuntimeError('Configure the Stripe test webhook signing secret.')
        if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1'))) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise RuntimeError('PUBLIC_BASE_URL must be an HTTPS origin (localhost is allowed for testing).')
        import stripe
        self.sdk = stripe
        self.client = stripe.StripeClient(key, max_network_retries=0,
                                         http_client=stripe.RequestsClient(timeout=4))
        self._verified_at = 0

    def assert_account(self):
        if self._verified_at and time.monotonic()-self._verified_at < 60:
            return
        if self.client.v1.accounts.retrieve_current()['id'] != self.account:
            raise RuntimeError('Stripe test key belongs to a different sandbox account.')
        self._verified_at = time.monotonic()

    def create_intent(self, order_id, amount_minor, currency, idempotency_key):
        # Deliberately no network inside the stock-reservation transaction.
        stripe_amount(amount_minor, currency)
        return PaymentIntent(self.name, amount_minor, currency, idempotency_key)

    def session(self, oid, amount, currency, idem, kind='marketplace', expires_at=None):
        external_amount = stripe_amount(amount, currency)
        self.assert_account()
        result = self.client.v1.checkout.sessions.create({
            'mode': 'payment',
            'client_reference_id': oid,
            'metadata': {'sentryloot_order': oid, 'sentryloot_mode': self.name, 'sentryloot_kind': kind},
            'payment_intent_data': {'transfer_group': 'sentryloot_test_'+oid,
                                    'metadata': {'sentryloot_order': oid, 'sentryloot_mode': self.name}},
            'line_items': [{'quantity': 1, 'price_data': {'currency': currency.lower(),
                'unit_amount': external_amount, 'product_data': {'name': 'SentryLoot TEST order'}}}],
            # Callers pin this value before the network request so retries with
            # the same idempotency key send byte-for-byte equivalent parameters.
            'expires_at': expires_at if expires_at is not None else int(time.time())+1800,
            'success_url': self.base+('/#topup-order/' if kind=='topup' else '/#order/')+oid,
            'cancel_url': self.base+('/#topup-order/' if kind=='topup' else '/#order/')+oid,
        }, options={'idempotency_key': 'checkout:'+idem})
        self.test_object(result)
        if not result['id'].startswith('cs_test_') or urlsplit(result.get('url') or '').hostname != 'checkout.stripe.com':
            raise RuntimeError('Invalid Stripe test checkout session.')
        return dict(result)

    @staticmethod
    def test_object(value):
        if value.get('livemode') is not False:
            raise RuntimeError('Live or unclassified Stripe objects are rejected.')
        return value

    def verify_webhook(self, headers, raw_body):
        event = self.sdk.Webhook.construct_event(raw_body, headers.get('Stripe-Signature', ''), self.secret, tolerance=300)
        self.test_object(event)
        if event.get('account') not in (None, self.account):
            raise ValueError('Unexpected connected-account event.')
        return event

    def paid_session(self, sid):
        self.assert_account()
        session = self.client.v1.checkout.sessions.retrieve(sid, {'expand': ['payment_intent.latest_charge']})
        self.test_object(session)
        intent = session.get('payment_intent')
        if session.get('payment_status') != 'paid' or not isinstance(intent, dict):
            raise ValueError('Checkout has not been paid.')
        self.test_object(intent)
        charge = intent.get('latest_charge')
        if intent.get('status') != 'succeeded' or not isinstance(charge, dict):
            raise ValueError('Payment is not settled.')
        self.test_object(charge)
        if charge.get('refunded') or charge.get('amount_refunded', 0) or charge.get('disputed'):
            raise ValueError('Payment has already been refunded or disputed.')
        return session

    def transfer(self, oid, seller, destination, charge, amount, currency):
        external_amount = stripe_amount(amount, currency)
        self.assert_account()
        source = self.test_object(self.client.v1.charges.retrieve(charge, {'expand': ['balance_transaction']}))
        balance = source.get('balance_transaction')
        if (not isinstance(balance, dict) or type(balance.get('amount')) is not int or balance['amount'] <= 0
                or type(source.get('amount')) is not int or source['amount'] <= 0 or external_amount > source['amount']
                or source.get('currency', '').upper() != currency):
            raise RuntimeError('Stripe settlement balance is not available yet.')
        # Presentment (e.g. UZS) may settle into the platform's MYR balance.
        # Use Stripe's actual settlement amounts, never an invented FX rate.
        settled_amount = external_amount*balance['amount']//source['amount']
        settled_currency = balance['currency']
        if settled_amount <= 0:
            raise RuntimeError('Seller transfer is below the settlement currency minimum.')
        previous = self.client.v1.transfers.list({'transfer_group': 'sentryloot_test_'+oid, 'limit': 100})
        if previous.get('has_more'):
            raise RuntimeError('Transfer history needs reconciliation.')
        matches = [t for t in previous['data'] if t.get('metadata', {}).get('sentryloot_seller') == seller]
        if matches:
            if len(matches) != 1 or matches[0]['amount'] != settled_amount or matches[0]['destination'] != destination or matches[0].get('source_transaction') != charge or matches[0]['currency'] != settled_currency:
                raise RuntimeError('Unexpected existing Stripe test transfer.')
            return self.test_object(matches[0])
        account = self.client.v1.accounts.retrieve(destination)
        # Connect accounts are bound by an admin to an app seller and must be
        # controlled by this test platform with active transfer capability.
        if destination == self.account or account.get('capabilities', {}).get('transfers') != 'active':
            raise RuntimeError('Seller test Connect account cannot receive transfers.')
        result = self.client.v1.transfers.create({'amount': settled_amount, 'currency': settled_currency,
            'destination': destination, 'source_transaction': charge,
            'transfer_group': 'sentryloot_test_'+oid,
            'metadata': {'sentryloot_order': oid, 'sentryloot_seller': seller, 'sentryloot_mode': self.name}},
            options={'idempotency_key': 'sentryloot:test:transfer:'+oid+':'+seller})
        return self.test_object(result)

    def refund(self, provider_reference, amount_minor, idempotency_key):
        self.assert_account()
        intent = self.test_object(self.client.v1.payment_intents.retrieve(provider_reference))
        external_amount = stripe_amount(amount_minor, intent.get('currency', '').upper())
        if (intent.get('id') != provider_reference or type(intent.get('amount_received')) is not int
                or intent['amount_received'] != external_amount):
            raise RuntimeError('Stripe test refund amount requires reconciliation.')
        refunds = self.client.v1.refunds.list({'payment_intent': provider_reference, 'limit': 100})
        existing = [r for r in refunds['data'] if r.get('status') == 'succeeded']
        if existing and not refunds.get('has_more') and sum(r['amount'] for r in existing) == external_amount:
            return {'id': existing[0]['id'], 'status': 'succeeded'}
        if existing or refunds.get('has_more'):
            raise RuntimeError('Partial refund needs reconciliation before continuing.')
        result = self.client.v1.refunds.create({'payment_intent': provider_reference, 'amount': external_amount},
                                             options={'idempotency_key': idempotency_key})
        return dict(result)

    def reverse_transfer(self, transfer_id, oid):
        self.assert_account()
        transfer = self.test_object(self.client.v1.transfers.retrieve(transfer_id))
        if transfer.get('reversed'):
            return
        if transfer.get('amount_reversed', 0):
            raise RuntimeError('Partly reversed transfer requires reconciliation.')
        self.client.v1.transfers.reversals.create(transfer_id, {},
            options={'idempotency_key': 'sentryloot:test:reverse:'+oid+':'+transfer_id})

    def reverse_order_transfers(self, oid):
        self.assert_account()
        transfers = self.client.v1.transfers.list({'transfer_group': 'sentryloot_test_'+oid, 'limit': 100})
        if transfers.get('has_more'):
            raise RuntimeError('Transfer history requires reconciliation.')
        for transfer in transfers['data']:
            self.test_object(transfer)
            if transfer.get('metadata', {}).get('sentryloot_mode') != self.name:
                raise RuntimeError('Unexpected transfer in test group.')
            self.reverse_transfer(transfer['id'], oid)


def start_checkout(db, oid, uid, core):
    order = db.execute('SELECT * FROM orders WHERE id=? AND buyer_id=?', (oid, uid)).fetchone()
    if not order or order['payment_mode'] != 'stripe_test':
        raise core['HttpError'](404, 'Test order not found.')
    if order['status'] != 'pending_payment':
        # Older releases expired pending orders without restoring their cart.
        # Repair that one-time gap when the buyer reopens the expired order.
        payment = db.execute("SELECT status FROM payments WHERE order_id=? AND provider='stripe_test'", (oid,)).fetchone()
        if order['status'] == 'cancelled' and payment and payment['status'] == 'expired':
            postgres = bool(core.get('DATABASE_URL'))
            db.execute('BEGIN' if postgres else 'BEGIN IMMEDIATE')
            try:
                core['trade_workflows'].lock_order(db, oid)
                restore_expired_cart(db, oid, uid)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
            raise core['HttpError'](409, 'This order expired. Its items are back in your cart; review availability and start a new checkout.')
        raise core['HttpError'](409, 'This order is no longer awaiting payment.')
    saved = read(db, 'checkout:'+oid)
    if saved:
        if saved['expires_at'] <= time.time():
            if not expire_pending_checkout(db, oid, uid, core):
                raise core['HttpError'](409, 'Order status changed while opening checkout. The order has been refreshed; review its current status.')
            raise core['HttpError'](409, 'This test checkout expired. Its items are back in your cart; review availability and start a new checkout.')
        return {'checkout_url': saved['url'], 'mode': 'stripe_test'}
    payment = db.execute('SELECT * FROM payments WHERE order_id=?', (oid,)).fetchone()
    attempt_key='checkout_attempt:'+oid
    attempt=read(db,attempt_key)
    if attempt is None:
        # Stripe compares every request parameter for a reused idempotency key.
        # Persist a fixed expiry first, then reuse it after timeouts or retries.
        # The v2 key also avoids the old key whose first attempt used a moving
        # expires_at value and became permanently unusable after an idempotency error.
        candidate={'idempotency_key':'v2:'+payment['idempotency_key'],
                   'expires_at':int(time.time())+1800}
        db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO NOTHING',
                   (PREFIX+attempt_key,json.dumps(candidate,separators=(',',':'))))
        attempt=read(db,attempt_key)
    if not attempt or int(attempt.get('expires_at',0))<=int(time.time()):
        if not expire_pending_checkout(db, oid, uid, core):
            raise core['HttpError'](409, 'Order status changed while opening checkout. The order has been refreshed; review its current status.')
        raise core['HttpError'](409,'This test checkout expired. Its items are back in your cart; review availability and start a new checkout.')
    try:
        session = core['configured_payment_provider']().session(
            oid,payment['amount_minor'],payment['currency'],attempt['idempotency_key'],
            expires_at=attempt['expires_at'])
    except Exception as exc:
        error = getattr(exc, 'json_body', None)
        stripe_code = getattr(exc, 'code', None)
        if not stripe_code and isinstance(error, dict):
            stripe_code = (error.get('error') or {}).get('code')
        if stripe_code == 'amount_too_small':
            # Stripe has definitively rejected this amount, so there is no
            # session to retry. Release the reservation and restore the cart.
            postgres = bool(core.get('DATABASE_URL'))
            db.execute('BEGIN' if postgres else 'BEGIN IMMEDIATE')
            try:
                lock = ' FOR UPDATE' if postgres else ''
                current = db.execute('SELECT status FROM orders WHERE id=? AND buyer_id=?'+lock,
                                     (oid, uid)).fetchone()
                if current and current['status'] == 'pending_payment':
                    items = db.execute('SELECT listing_id,quantity FROM order_items WHERE order_id=?'+lock,
                                       (oid,)).fetchall()
                    for item in items:
                        db.execute('UPDATE listings SET reserved=CASE WHEN reserved>? THEN reserved-? ELSE 0 END,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                                   (item['quantity'], item['quantity'], item['listing_id']))
                        db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,?) ON CONFLICT(user_id,listing_id) DO UPDATE SET quantity=carts.quantity+excluded.quantity,updated_at=CURRENT_TIMESTAMP',
                                   (uid, item['listing_id'], item['quantity']))
                    db.execute("UPDATE orders SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending_payment'", (oid,))
                    db.execute("UPDATE payments SET status='failed',updated_at=CURRENT_TIMESTAMP WHERE order_id=? AND status='pending'", (oid,))
                    db.execute("DELETE FROM platform_config WHERE key LIKE 'coupon_use:%' AND value=?", (oid,))
                    core['event'](db, oid, uid, 'pending_payment', 'cancelled',
                                  'Stripe test minimum amount not met; checkout canceled and cart restored.')
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
            raise core['HttpError'](400,
                'Stripe requires at least RM 2.00 after currency conversion. This order was not charged; it was canceled and returned to your cart. Increase the quantity or choose a higher-priced item.') from exc
        # Never put SDK exception messages or response bodies in client output.
        raise core['HttpError'](503, 'Stripe test checkout is temporarily unavailable. Retry from this order.') from exc
    write(db, 'checkout:'+oid, {'id': session['id'], 'url': session['url'], 'expires_at': session['expires_at']})
    return {'checkout_url': session['url'], 'mode': 'stripe_test'}


def restore_expired_cart(db, oid, uid):
    """Restore an expired order's lines once, so the buyer can retry safely."""
    marker = 'expired_cart_restored:'+oid
    if read(db, marker):
        return
    for item in db.execute('SELECT listing_id,quantity FROM order_items WHERE order_id=?', (oid,)).fetchall():
        db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,?) '
                   'ON CONFLICT(user_id,listing_id) DO UPDATE SET '
                   'quantity=CASE WHEN carts.quantity>excluded.quantity THEN carts.quantity ELSE excluded.quantity END,updated_at=CURRENT_TIMESTAMP',
                   (uid, item['listing_id'], item['quantity']))
    write(db, marker, {'restored': True})


def expire_pending_checkout(db, oid, uid, core):
    """Expire the order and release its reservation before offering a retry."""
    postgres = bool(core.get('DATABASE_URL'))
    db.execute('BEGIN' if postgres else 'BEGIN IMMEDIATE')
    try:
        core['trade_workflows'].lock_order(db, oid)
        order = db.execute('SELECT status FROM orders WHERE id=? AND buyer_id=?', (oid, uid)).fetchone()
        payment = db.execute("SELECT status FROM payments WHERE order_id=? AND provider='stripe_test'", (oid,)).fetchone()
        if order and order['status'] == 'pending_payment' and payment and payment['status'] == 'pending':
            items = db.execute('SELECT listing_id,quantity FROM order_items WHERE order_id=?', (oid,)).fetchall()
            for item in items:
                db.execute('UPDATE listings SET reserved=CASE WHEN reserved>=? THEN reserved-? ELSE 0 END,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                           (item['quantity'], item['quantity'], item['listing_id']))
            db.execute("UPDATE payments SET status='expired',updated_at=CURRENT_TIMESTAMP WHERE order_id=? AND status='pending'", (oid,))
            db.execute("UPDATE orders SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending_payment'", (oid,))
            db.execute("DELETE FROM platform_config WHERE key LIKE 'coupon_use:%' AND value=?", (oid,))
            restore_expired_cart(db, oid, uid)
            core['event'](db, oid, uid, 'pending_payment', 'cancelled', 'Stripe test checkout expired; cart restored for retry.')
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise
    order = db.execute('SELECT status FROM orders WHERE id=? AND buyer_id=?', (oid, uid)).fetchone()
    payment = db.execute("SELECT status FROM payments WHERE order_id=? AND provider='stripe_test'", (oid,)).fetchone()
    return bool(order and order['status'] == 'cancelled' and payment and payment['status'] == 'expired')


def enqueue(db, oid, kind):
    key = 'job:'+oid+':'+kind
    if not read(db, key):
        write(db, key, {'order_id': oid, 'kind': kind, 'status': 'pending', 'attempts': 0})


def queue_release(db, oid):
    enqueue(db, oid, 'transfer')


def queue_refund(db, oid, core):
    payment = db.execute("SELECT * FROM payments WHERE order_id=? AND provider='stripe_test'", (oid,)).fetchone()
    if not payment or payment['status'] not in ('succeeded', 'refund_pending'):
        raise core['HttpError'](409, 'This test payment cannot be refunded.')
    enqueue(db, oid, 'refund')
    db.execute("UPDATE payments SET status='refund_pending',updated_at=CURRENT_TIMESTAMP WHERE order_id=?", (oid,))
    db.execute("UPDATE orders SET status='refund_pending',updated_at=CURRENT_TIMESTAMP WHERE id=?", (oid,))


def ledger(db, oid, user, kind, amount, currency, core):
    db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',
               (core['ident'](), oid, user, kind, amount, currency, 'Stripe TEST accounting only; not withdrawable cash.'))


def release_test_ledger(db, oid, core):
    if read(db, 'ledger_release:'+oid):
        return
    rows = db.execute("SELECT user_id,entry_type,SUM(amount_minor) amount,currency FROM ledger_entries WHERE order_id=? AND entry_type IN ('stripe_test_hold','stripe_test_fee_hold') GROUP BY user_id,entry_type,currency", (oid,)).fetchall()
    for row in rows:
        ledger(db, oid, row['user_id'], row['entry_type'], -row['amount'], row['currency'], core)
        ledger(db, oid, row['user_id'], 'stripe_test_earning' if row['user_id'] else 'stripe_test_commission', row['amount'], row['currency'], core)
    write(db, 'ledger_release:'+oid, True)


def reverse_test_ledger(db, oid, core):
    if read(db, 'ledger_refund:'+oid):
        return
    rows = db.execute("SELECT user_id,entry_type,SUM(amount_minor) amount,currency FROM ledger_entries WHERE order_id=? AND entry_type IN ('stripe_test_hold','stripe_test_fee_hold','stripe_test_earning','stripe_test_commission') GROUP BY user_id,entry_type,currency", (oid,)).fetchall()
    for row in rows:
        if row['amount']:
            ledger(db, oid, row['user_id'], row['entry_type'], -row['amount'], row['currency'], core)
    write(db, 'ledger_refund:'+oid, True)


def webhook(db, headers, raw, core):
    try:
        provider = core['configured_payment_provider']()
        if provider.name != 'stripe_test':
            raise RuntimeError('Test payments are disabled.')
        event = provider.verify_webhook(headers, raw)
    except Exception as exc:
        raise core['HttpError'](400, 'Invalid Stripe test webhook signature or environment.') from exc
    return receive_event(db, provider, event, core)


def receive_event(db, provider, event, core):
    """Only signed webhooks or server-retrieved Checkout sessions enter here."""
    if event['type'] in ('charge.refunded', 'charge.dispute.created'):
        return charge_event(db, provider, event, core)
    if event['type'] not in ('checkout.session.completed', 'checkout.session.async_payment_succeeded', 'checkout.session.expired', 'checkout.session.async_payment_failed'):
        return {'ok': True, 'ignored': True}
    obj = event['data']['object']
    provider.test_object(obj)
    if obj.get('metadata', {}).get('sentryloot_kind') == 'topup':
        import stripe_test_topups
        return stripe_test_topups.receive(db, provider, event, core)
    oid = obj.get('client_reference_id', '')
    if obj.get('metadata', {}).get('sentryloot_mode') != 'stripe_test':
        return {'ok': True, 'ignored': True}
    saved = read(db, 'checkout:'+oid)
    if not saved or saved['id'] != obj.get('id'):
        raise core['HttpError'](409, 'Stripe test checkout is not registered yet.')
    if read(db, 'event:'+event['id']):
        return {'ok': True, 'duplicate': True}
    current = db.execute('SELECT status FROM payments WHERE order_id=?', (oid,)).fetchone()
    if current and current['status'] in ('succeeded', 'refund_pending', 'refunded'):
        return {'ok': True, 'duplicate': True}
    paid = event['type'] in ('checkout.session.completed', 'checkout.session.async_payment_succeeded')
    if paid and obj.get('payment_status') != 'paid':
        return {'ok': True, 'awaiting_payment': True}
    session = provider.paid_session(saved['id']) if paid else obj
    db.execute('BEGIN IMMEDIATE')
    try:
        core['trade_workflows'].lock_order(db, oid)
        order = db.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
        payment = db.execute("SELECT * FROM payments WHERE order_id=? AND provider='stripe_test'", (oid,)).fetchone()
        if not order or not payment:
            raise core['HttpError'](404, 'Test order not found.')
        if read(db, 'event:'+event['id']):
            db.execute('COMMIT'); return {'ok': True, 'duplicate': True}
        if paid:
            intent = session['payment_intent']
            if (session.get('client_reference_id') != oid or session.get('metadata', {}).get('sentryloot_order') != oid
                    or not matches_amount(session.get('amount_total'), payment['amount_minor'], payment['currency']) or session.get('currency', '').upper() != payment['currency']
                    or not matches_amount(intent.get('amount_received'), payment['amount_minor'], payment['currency']) or intent.get('currency', '').upper() != payment['currency']):
                raise core['HttpError'](409, 'Stripe test amount, currency or order mismatch.')
            if payment['status'] == 'pending' and order['status'] == 'pending_payment':
                db.execute("UPDATE payments SET status='succeeded',provider_reference=?,updated_at=CURRENT_TIMESTAMP WHERE order_id=?", (intent['id'], oid))
                db.execute("UPDATE orders SET status='paid',updated_at=CURRENT_TIMESTAMP WHERE id=?", (oid,))
                write(db, 'paid:'+oid, {'intent': intent['id'], 'charge': intent['latest_charge']['id']})
                core['event'](db, oid, None, 'pending_payment', 'paid', 'Stripe TEST payment verified; seller transfer held until completion.')
                for item in db.execute('SELECT * FROM order_items WHERE order_id=?', (oid,)).fetchall():
                    changed = db.execute("UPDATE listings SET stock=stock-?,reserved=reserved-?,status=CASE WHEN stock-?<=0 THEN 'sold_out' ELSE status END WHERE id=? AND stock>=? AND reserved>=?", (item['quantity'], item['quantity'], item['quantity'], item['listing_id'], item['quantity'], item['quantity']))
                    if changed.rowcount != 1:
                        raise core['HttpError'](409, 'Reserved stock is no longer available.')
                    net = item['unit_price_minor']*item['quantity']-item['commission_minor']
                    for user, kind, amount in ((item['seller_id'], 'stripe_test_hold', net), (None, 'stripe_test_fee_hold', item['commission_minor'])):
                        if amount:
                            db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)', (core['ident'](), oid, user, kind, amount, order['currency'], 'Stripe TEST funds; no real money.'))
                    core['notify'](db, item['seller_id'], 'order', 'New test order', order['reference']+' · Stripe TEST payment received.', '/order/'+oid)
                if order['commission_minor']:
                    db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)', (core['ident'](), oid, None, 'stripe_test_fee_hold', order['commission_minor'], order['currency'], 'Stripe TEST buyer checkout fee.'))
                # Do not allocate actual digital codes or call any supplier in test mode.
            elif payment['status'] in ('expired', 'cancelled'):
                # A late success must never fulfill cancelled stock. Refund it.
                db.execute("UPDATE payments SET status='succeeded',provider_reference=? WHERE order_id=?", (intent['id'], oid))
                write(db, 'paid:'+oid, {'intent': intent['id'], 'charge': intent['latest_charge']['id'], 'late': True})
                queue_refund(db, oid, core)
        elif payment['status'] == 'pending' and order['status'] == 'pending_payment':
            for item in db.execute('SELECT * FROM order_items WHERE order_id=?', (oid,)):
                db.execute('UPDATE listings SET reserved=CASE WHEN reserved>=? THEN reserved-? ELSE 0 END WHERE id=?', (item['quantity'], item['quantity'], item['listing_id']))
            db.execute("UPDATE payments SET status='expired' WHERE order_id=?", (oid,))
            db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (oid,))
            restore_expired_cart(db, oid, order['buyer_id'])
        write(db, 'event:'+event['id'], {'processed': True})
        db.execute('COMMIT')
        return {'ok': True}
    except Exception:
        db.execute('ROLLBACK'); raise


def reconcile_checkout(db, oid, uid, core):
    """Recover a delayed webhook on return, without trusting browser success flags."""
    order = db.execute("SELECT status FROM orders WHERE id=? AND buyer_id=? AND payment_mode='stripe_test'", (oid, uid)).fetchone()
    if not order:
        raise core['HttpError'](404, 'Test order not found.')
    if order['status'] != 'pending_payment':
        return {'status': order['status']}
    saved = read(db, 'checkout:'+oid)
    if not saved:
        return {'status': 'pending_payment'}
    provider = core['configured_payment_provider']()
    if provider.name != 'stripe_test':
        raise core['HttpError'](409, 'Stripe test is disabled.')
    try:
        session = provider.paid_session(saved['id'])
    except ValueError:
        return {'status': 'pending_payment'}
    except Exception as exc:
        raise core['HttpError'](503, 'Payment confirmation is temporarily unavailable. Please retry.') from exc
    receive_event(db, provider, {'id': 'reconcile_'+saved['id'], 'type': 'checkout.session.completed',
                                'data': {'object': session}}, core)
    return {'status': db.execute('SELECT status FROM orders WHERE id=?', (oid,)).fetchone()['status']}


def charge_event(db, provider, event, core):
    """Dashboard refunds/chargebacks freeze release even without a site action."""
    if read(db, 'event:'+event['id']):
        return {'ok': True, 'duplicate': True}
    obj = provider.test_object(event['data']['object'])
    charge = obj if event['type'] == 'charge.refunded' else provider.test_object(provider.client.v1.charges.retrieve(obj['charge']))
    intent = charge.get('payment_intent')
    if not isinstance(intent, str):
        return {'ok': True, 'ignored': True}
    payment = db.execute("SELECT * FROM payments WHERE provider='stripe_test' AND provider_reference=?", (intent,)).fetchone()
    if not payment:
        # A charge event can arrive before checkout.session.completed. Stripe
        # retries this response; it must not be permanently acknowledged first.
        raise core['HttpError'](409, 'Checkout payment event must be reconciled first.')
    oid = payment['order_id']
    if charge.get('currency', '').upper() != payment['currency'] or not matches_amount(charge.get('amount'), payment['amount_minor'], payment['currency']):
        raise core['HttpError'](409, 'Stripe charge amount mismatch.')
    db.execute('BEGIN IMMEDIATE')
    try:
        core['trade_workflows'].lock_order(db, oid)
        payment = db.execute('SELECT * FROM payments WHERE order_id=?', (oid,)).fetchone()
        if payment['status'] != 'refunded':
            if event['type'] == 'charge.refunded' and matches_amount(charge.get('amount_refunded'), payment['amount_minor'], payment['currency']):
                queue_refund(db, oid, core)
                # A dashboard/API refund is already complete at Stripe. Reconcile
                # locally without submitting a second refund request.
                refund_job = read(db, 'job:'+oid+':refund')
                refund_job['external_refund'] = True
                refund_job['external_refund_id'] = charge.get('id')
                write(db, 'job:'+oid+':refund', refund_job)
            else:
                db.execute("UPDATE orders SET status='disputed',updated_at=CURRENT_TIMESTAMP WHERE id=?", (oid,))
                core['event'](db, oid, None, None, 'disputed', 'Stripe TEST charge dispute or partial refund. Seller transfer frozen; reconciliation required.')
                enqueue(db, oid, 'dispute_reversal')
                # Route through the existing independent moderator workflow.
                if not db.execute("SELECT 1 FROM reports WHERE order_id=? AND reason='order_dispute' AND status IN ('open','reviewing')", (oid,)).fetchone():
                    buyer = db.execute('SELECT buyer_id FROM orders WHERE id=?', (oid,)).fetchone()['buyer_id']
                    db.execute("INSERT INTO reports(id,reporter_id,order_id,reason,details) VALUES(?,?,?,'order_dispute',?)", (core['ident'](), buyer, oid, 'Stripe TEST charge dispute or partial refund requires reconciliation.'))
        write(db, 'event:'+event['id'], {'processed': True})
        db.execute('COMMIT'); return {'ok': True}
    except Exception:
        db.execute('ROLLBACK'); raise


def process(db, core, limit=5):
    """Bounded worker. Locks only its order; idempotency recovers crash gaps.

    This dedicated worker serializes release/refund on the order row, including
    against cancellation/moderation requests. Remote calls are never on page GET.
    """
    provider = core['configured_payment_provider']()
    if provider.name != 'stripe_test':
        raise core['HttpError'](409, 'Stripe test provider is disabled.')
    results = []
    for row in db.execute("""SELECT key FROM platform_config WHERE key LIKE 'stripe_test:job:%'
            AND value NOT LIKE '%"status":"succeeded"%' AND value NOT LIKE '%"status":"cancelled"%'
            ORDER BY updated_at LIMIT 200""").fetchall():
        key = row['key'][len(PREFIX):]
        job = read(db, key)
        if job['status'] in ('succeeded', 'cancelled'):
            continue
        if len(results) >= limit:
            break
        if job['kind'] == 'topup_refund':
            import stripe_test_topups
            results.append(stripe_test_topups.process_refund(db, provider, key, core))
            continue
        oid = job['order_id']
        db.execute('BEGIN IMMEDIATE')
        try:
            core['trade_workflows'].lock_order(db, oid)
            job = read(db, key)
            if job['status'] in ('succeeded', 'cancelled'):
                db.execute('COMMIT'); continue
            order = db.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
            payment = db.execute("SELECT * FROM payments WHERE order_id=? AND provider='stripe_test'", (oid,)).fetchone()
            paid = read(db, 'paid:'+oid)
            if not paid or not payment:
                raise RuntimeError('Missing verified payment.')
            job['attempts'] += 1
            if job['kind'] == 'refund':
                # Separate charges/transfers require explicit reversals before
                # a refund can recover already released seller funds.
                provider.reverse_order_transfers(oid)
                # No money is labelled refunded until Stripe confirms success.
                if job.get('external_refund'):
                    result = {'id': job.get('external_refund_id'), 'status': 'succeeded'}
                else:
                    result = provider.refund(paid['intent'], payment['amount_minor'], 'sentryloot:test:refund:'+oid)
                    if result.get('status') != 'succeeded':
                        raise RuntimeError('Stripe test refund is still pending.')
                db.execute("UPDATE payments SET status='refunded',updated_at=CURRENT_TIMESTAMP WHERE order_id=?", (oid,))
                db.execute("UPDATE orders SET status='refunded',updated_at=CURRENT_TIMESTAMP WHERE id=?", (oid,))
                if not paid.get('late'):
                    # Use the accounting helper only after external confirmation.
                    reverse_test_ledger(db, oid, core)
                    for item in db.execute('SELECT * FROM order_items WHERE order_id=?', (oid,)):
                        if item['delivered_quantity'] == 0:
                            db.execute("UPDATE listings SET stock=stock+?,status=CASE WHEN status='sold_out' THEN 'published' ELSE status END WHERE id=?", (item['quantity'], item['listing_id']))
                job.update(status='succeeded', reference=result['id'])
                core['event'](db, oid, None, order['status'], 'refunded', 'Stripe TEST refund confirmed.')
            elif job['kind'] == 'dispute_reversal':
                # Recover previously released seller proceeds while a Stripe
                # dispute is reviewed. Stripe still determines its outcome.
                provider.reverse_order_transfers(oid)
                job['status'] = 'succeeded'
            elif order['status'] != 'completed' or payment['status'] != 'succeeded':
                # A dispute or refund request freezes release.
                job['status'] = 'cancelled' if payment['status'] in ('refunded', 'refund_pending') else 'blocked'
            else:
                for seller in db.execute('SELECT seller_id,SUM(unit_price_minor*quantity-commission_minor) amount FROM order_items WHERE order_id=? GROUP BY seller_id', (oid,)).fetchall():
                    transfer_key = 'transfer:'+oid+':'+seller['seller_id']
                    if read(db, transfer_key) or seller['amount'] <= 0:
                        continue
                    account = read(db, 'seller:'+seller['seller_id'])
                    if not account:
                        raise RuntimeError('Seller test Connect account has not been linked.')
                    result = provider.transfer(oid, seller['seller_id'], account['id'], paid['charge'], seller['amount'], order['currency'])
                    write(db, transfer_key, {'id': result['id'], 'amount': seller['amount'],
                        'settled_amount': result.get('amount'), 'settled_currency': result.get('currency')})
                release_test_ledger(db, oid, core)
                job['status'] = 'succeeded'
            write(db, key, job)
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            # Keep only a safe error category, never raw SDK errors or keys.
            job = read(db, key)
            job.update(status='retry', attempts=job.get('attempts', 0)+1, error='Stripe test action needs retry or account configuration.')
            write(db, key, job)
        results.append({'order_id': oid, 'kind': job['kind'], 'status': job['status']})
    return {'mode': 'stripe_test', 'jobs': results, 'real_money_moved': False}


def route(handler, db, ctx, method, path, data, raw, core):
    import stripe_test_topups
    result = stripe_test_topups.route(db, ctx, method, path, data, core)
    if result is not UNHANDLED:
        return result
    if path == '/api/seller/stripe-test/connect' and method in ('GET', 'POST'):
        uid = core['require_verified'](ctx)
        seller = db.execute("SELECT 1 FROM seller_profiles WHERE user_id=? AND selling_enabled=1 AND verification_status='verified' AND identity_status='verified'", (uid,)).fetchone()
        if not seller:
            raise core['HttpError'](403, 'Verified seller access required.')
        provider = core['configured_payment_provider']()
        if provider.name != 'stripe_test':
            raise core['HttpError'](409, 'Stripe test is disabled.')
        provider.assert_account()
        linked = read(db, 'seller:'+uid)
        if method == 'GET':
            if not linked:
                return {'mode': 'stripe_test', 'connected': False, 'balances': []}
            account = provider.client.v1.accounts.retrieve(linked['id'])
            balances = provider.client.v1.balance.retrieve(options={'stripe_account': linked['id']})
            return {'mode': 'stripe_test', 'connected': True, 'account_id': linked['id'],
                    'transfers_active': account.get('capabilities', {}).get('transfers') == 'active',
                    'payouts_enabled': account.get('payouts_enabled', False),
                    'balances': [{'amount': entry['amount'], 'currency': entry['currency']} for entry in balances['available']]}
        if data.get('test_only') is not True:
            raise core['HttpError'](400, 'Confirm test-only Connect onboarding.')
        if not linked:
            platform = provider.client.v1.accounts.retrieve_current()
            account = provider.client.v1.accounts.create({'type': 'express', 'country': platform['country'],
                'capabilities': {'transfers': {'requested': True}},
                'settings': {'payouts': {'schedule': {'interval': 'manual'}}},
                'metadata': {'sentryloot_mode': 'stripe_test', 'sentryloot_seller': uid}},
                options={'idempotency_key': 'sentryloot:test:connect:'+uid})
            linked = {'id': account['id']}
            write(db, 'seller:'+uid, linked)
        result = provider.client.v1.account_links.create({'account': linked['id'], 'type': 'account_onboarding',
            'refresh_url': provider.base+'/#stripe-test-connect', 'return_url': provider.base+'/#stripe-test-connect'})
        if urlsplit(result['url']).hostname != 'connect.stripe.com':
            raise RuntimeError('Unexpected Stripe test onboarding URL.')
        core['audit'](db, uid, 'stripe_test_connect_onboarding', 'seller', uid)
        return {'mode': 'stripe_test', 'onboarding_url': result['url']}
    if path == '/api/seller/stripe-test/payout' and method == 'POST':
        uid = core['require_verified'](ctx)
        linked = read(db, 'seller:'+uid)
        if not linked or not db.execute('SELECT 1 FROM seller_profiles WHERE user_id=? AND selling_enabled=1', (uid,)).fetchone():
            raise core['HttpError'](403, 'Link a verified seller test Connect account first.')
        amount, currency, key = data.get('amount_minor'), data.get('currency', ''), data.get('request_key', '')
        if data.get('test_only') is not True or type(amount) is not int or amount <= 0 or not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency) or not isinstance(key, str) or not re.fullmatch('[A-Za-z0-9_-]{16,100}', key):
            raise core['HttpError'](400, 'Enter a valid test payout amount, currency and request key.')
        provider = core['configured_payment_provider']()
        if provider.name != 'stripe_test':
            raise core['HttpError'](409, 'Stripe test is disabled.')
        provider.assert_account()
        result = provider.test_object(provider.client.v1.payouts.create({'amount': amount, 'currency': currency.lower(),
            'metadata': {'sentryloot_mode': 'stripe_test', 'sentryloot_seller': uid}},
            options={'stripe_account': linked['id'], 'idempotency_key': 'sentryloot:test:payout:'+uid+':'+key}))
        write(db, 'payout:'+result['id'], {'seller_id': uid, 'id': result['id'], 'status': result['status'], 'amount': result['amount'], 'currency': result['currency']})
        core['audit'](db, uid, 'stripe_test_payout', 'seller', uid, {'payout_id': result['id']})
        return {'mode': 'stripe_test', 'id': result['id'], 'status': result['status'], 'real_money_moved': False}
    if path == '/api/webhooks/stripe-test' and method == 'POST':
        return webhook(db, handler.headers, raw, core)
    match = re.fullmatch(r'/api/orders/([A-Za-z0-9_-]+)/stripe-checkout', path)
    if match and method == 'POST':
        core['require_verified'](ctx)
        return start_checkout(db, match[1], ctx['uid'], core)
    match = re.fullmatch(r'/api/orders/([A-Za-z0-9_-]+)/stripe-confirmation', path)
    if match and method == 'POST':
        core['require_verified'](ctx)
        core['check_rate'](db, 'stripe_confirmation', ctx['uid'], 30, 300)
        return reconcile_checkout(db, match[1], ctx['uid'], core)
    match = re.fullmatch(r'/api/admin/payments/stripe-test/sellers/([A-Za-z0-9_-]+)', path)
    if match and method == 'POST':
        aid = core['require_admin'](ctx)
        seller = match[1]
        account = data.get('account_id', '')
        if not re.fullmatch(r'acct_[A-Za-z0-9]+', account) or not db.execute('SELECT 1 FROM seller_profiles WHERE user_id=?', (seller,)).fetchone():
            raise core['HttpError'](400, 'Choose an existing seller and a test Connect account.')
        provider = core['configured_payment_provider']()
        if provider.name != 'stripe_test':
            raise core['HttpError'](409, 'Stripe test provider is disabled.')
        provider.assert_account()
        target = provider.client.v1.accounts.retrieve(account)
        if account == provider.account or target.get('controller', {}).get('is_controller') is not True or target.get('capabilities', {}).get('transfers') != 'active':
            raise core['HttpError'](409, 'Use an active test Connect account controlled by this sandbox.')
        existing = read(db, 'seller:'+seller)
        if existing and existing['id'] != account:
            raise core['HttpError'](409, 'A different test Connect account is already linked. Reconcile outstanding transfers first.')
        write(db, 'seller:'+seller, {'id': account})
        core['audit'](db, aid, 'stripe_test_connect_link', 'seller', seller, {'account_id': account})
        return {'mode': 'stripe_test', 'account_id': account}
    if path == '/api/cron/stripe-test-payments' and method == 'GET':
        import hmac
        secret = os.environ.get('CRON_SECRET', '')
        if not secret or not hmac.compare_digest(handler.headers.get('Authorization', ''), 'Bearer '+secret):
            raise core['HttpError'](401, 'Authorization required.')
        return process(db, core, limit=1)
    if path == '/api/admin/payments/stripe-test/process' and method == 'POST':
        core['require_admin'](ctx)
        return process(db, core)
    if path == '/api/admin/payments/stripe-test' and method == 'GET':
        core['require_admin'](ctx)
        rows = db.execute("SELECT key,value FROM platform_config WHERE key LIKE 'stripe_test:job:%' ORDER BY updated_at DESC LIMIT 50").fetchall()
        import stripe_test_topups
        sellers = [dict(row) for row in db.execute('SELECT user_id,shop_name FROM seller_profiles ORDER BY shop_name LIMIT 100')]
        for seller in sellers:
            seller['account_id'] = read(db, 'seller:'+seller['user_id'], {}).get('id', '')
        topups = [core['topup_admin_row'](row) for row in db.execute("SELECT o.id,o.reference,o.status,o.quantity,p.game_name FROM topup_orders o JOIN topup_packages p ON p.id=o.package_id WHERE EXISTS(SELECT 1 FROM platform_config c WHERE c.key='stripe_test:topup:'||o.id) ORDER BY o.created_at DESC LIMIT 50")]
        return {'mode': 'stripe_test', 'configured': stripe_test_topups.enabled(core),
                'jobs': [json.loads(row['value']) for row in rows], 'sellers': sellers,
                'topups': topups, 'real_money_moved': False}
    return UNHANDLED
