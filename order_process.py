"""Order preparation and isolated, currency-correct Stripe test wallet accounting.

Test payouts here simulate the bank leg only. They never call a live payout
provider or create entries consumable by the real /api/payouts endpoint.
"""
import hashlib
import json
import re

UNHANDLED = object()
PAYOUT_PREFIX = 'stripe_test:wallet_payout:'


def wallet(db, uid):
    rows = db.execute("""SELECT e.order_id,e.currency,e.entry_type,SUM(e.amount_minor) amount,
        o.reference,o.status,o.created_at,p.status payment_status
        FROM ledger_entries e JOIN orders o ON o.id=e.order_id
        JOIN payments p ON p.order_id=o.id AND p.provider='stripe_test'
        WHERE e.user_id=? AND e.entry_type IN ('stripe_test_hold','stripe_test_earning')
        GROUP BY e.order_id,e.currency,e.entry_type,o.reference,o.status,o.created_at,p.status""", (uid,)).fetchall()
    orders = {}
    currencies = {}
    def balance(currency):
        return currencies.setdefault(currency, {'currency': currency, 'pending_minor': 0,
            'available_minor': 0, 'payout_processing_minor': 0, 'paid_out_minor': 0})
    for row in rows:
        key = row['order_id']
        item = orders.setdefault(key, {'order_id': key, 'reference': row['reference'],
            'currency': row['currency'], 'status': row['status'], 'created_at': row['created_at'],
            'pending_minor': 0, 'available_minor': 0, 'net_minor': 0})
        amount = int(row['amount'] or 0)
        item['net_minor'] += amount
        # A later dispute/refund request freezes previously available earnings.
        available = row['entry_type'] == 'stripe_test_earning' and row['status'] == 'completed' and row['payment_status'] == 'succeeded'
        field = 'available_minor' if available else 'pending_minor'
        item[field] += amount
        balance(row['currency'])[field] += amount
    payouts = []
    for row in db.execute('SELECT value FROM platform_config WHERE key LIKE ?', (PAYOUT_PREFIX+uid+':%',)):
        payout = json.loads(row['value'])
        # User IDs may contain '_' (a SQL LIKE wildcard). Check ownership again
        # before returning a record or including it in this user's balance.
        if payout.get('seller_id') != uid:
            continue
        payouts.append(payout)
        b = balance(payout['currency'])
        if payout['status'] == 'processing':
            b['available_minor'] -= payout['amount_minor']
            b['payout_processing_minor'] += payout['amount_minor']
        elif payout['status'] == 'paid':
            b['available_minor'] -= payout['amount_minor']
            b['paid_out_minor'] += payout['amount_minor']
    # Preserve a negative available balance after a later reversal; never hide debt
    # with max(0, balance), and never offset one currency with another currency.
    if not currencies:
        balance('MYR')
    return {'mode': 'stripe_test', 'real_money_moved': False,
        'payout_mode': 'simulation', 'balances': sorted(currencies.values(), key=lambda b: b['currency']),
        'orders': sorted(orders.values(), key=lambda o: o['created_at'], reverse=True),
        'payouts': sorted(payouts, key=lambda p: p['created_at'], reverse=True)}


def payout(db, uid, data, core):
    if data.get('test_only') is not True:
        raise core['HttpError'](400, 'Confirm that this is a simulated test payout.')
    key = data.get('request_key', '')
    amount, currency = data.get('amount_minor'), data.get('currency')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', key) or type(amount) is not int or amount <= 0 or not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency):
        raise core['HttpError'](400, 'Enter a valid test amount, currency and request key.')
    record_key = PAYOUT_PREFIX+uid+':'+hashlib.sha256(key.encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        # Lock the seller across tabs and all payout requests on PostgreSQL.
        db.execute('SELECT id FROM users WHERE id=?'+(' FOR UPDATE' if core.get('DATABASE_URL') else ''), (uid,)).fetchone()
        existing = db.execute('SELECT value FROM platform_config WHERE key=?', (record_key,)).fetchone()
        if existing:
            result = json.loads(existing['value'])
            if result['amount_minor'] != amount or result['currency'] != currency:
                raise core['HttpError'](409, 'This request key was already used for a different payout.')
        else:
            b = next((b for b in wallet(db, uid)['balances'] if b['currency'] == currency), None)
            if not b or b['available_minor'] < amount:
                raise core['HttpError'](409, 'The test payout exceeds your available balance in this currency.')
            result = {'id': hashlib.sha256((uid+key).encode()).hexdigest()[:32], 'seller_id': uid,
                'amount_minor': amount, 'currency': currency, 'status': 'processing',
                'created_at': core['now_iso'](), 'mode': 'stripe_test', 'simulated': True}
            db.execute('INSERT INTO platform_config(key,value) VALUES(?,?)', (record_key, json.dumps(result)))
            core['audit'](db, uid, 'test_wallet_payout_requested', 'test_payout', result['id'])
        db.execute('COMMIT')
        return result
    except Exception:
        db.execute('ROLLBACK')
        raise


def route(db, ctx, method, path, data, core):
    uid = ctx['uid']
    match = re.fullmatch(r'/api/orders/([A-Za-z0-9_-]+)/test-review', path)
    if match and method in ('GET', 'POST'):
        core['require_verified'](ctx)
        order = db.execute("SELECT status FROM orders WHERE id=? AND buyer_id=? AND payment_mode='stripe_test'", (match[1], uid)).fetchone()
        if not order:
            raise core['HttpError'](404, 'Test order not found.')
        if order['status'] != 'completed':
            raise core['HttpError'](409, 'Complete the test purchase before leaving a test review.')
        key = 'stripe_test:review:'+match[1]
        if method == 'POST':
            rating = data.get('rating')
            if type(rating) is not int or not 1 <= rating <= 5:
                raise core['HttpError'](400, 'Choose a rating from 1 to 5.')
            body = core['clean_text'](data.get('body'), 'Test review', 5, 1500)
            value = {'rating': rating, 'body': body, 'test_only': True, 'updated_at': core['now_iso']()}
            db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP', (key, json.dumps(value)))
            return value
        row = db.execute('SELECT value FROM platform_config WHERE key=?', (key,)).fetchone()
        return json.loads(row['value']) if row else {}
    if path == '/api/seller/test-wallet' and method == 'GET':
        core['require_user'](ctx)
        return wallet(db, uid)
    if path == '/api/seller/test-wallet/payouts' and method == 'POST':
        core['require_verified'](ctx)
        core['seller_ok'](db, uid)
        return payout(db, uid, data, core)
    match = re.fullmatch(r'/api/seller/test-wallet/payouts/([a-f0-9]{32})', path)
    if match and method == 'POST':
        core['require_verified'](ctx)
        core['seller_ok'](db, uid)
        if data.get('test_only') is not True or data.get('outcome') not in ('paid', 'failed'):
            raise core['HttpError'](400, 'Choose a simulated success or failure.')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('SELECT id FROM users WHERE id=?'+(' FOR UPDATE' if core.get('DATABASE_URL') else ''), (uid,)).fetchone()
            row = next((r for r in db.execute('SELECT key,value FROM platform_config WHERE key LIKE ?', (PAYOUT_PREFIX+uid+':%',)) if json.loads(r['value']).get('seller_id') == uid and json.loads(r['value'])['id'] == match[1]), None)
            if not row:
                raise core['HttpError'](404, 'Test payout not found.')
            p = json.loads(row['value'])
            if p['status'] == 'processing':
                # A reversal that arrives after reservation must block success.
                if data['outcome'] == 'paid' and next(b for b in wallet(db, uid)['balances'] if b['currency'] == p['currency'])['available_minor'] < 0:
                    raise core['HttpError'](409, 'An order reversal has frozen this test payout. Simulate failure to return the reservation.')
                p.update(status=data['outcome'], updated_at=core['now_iso']())
                db.execute('UPDATE platform_config SET value=?,updated_at=CURRENT_TIMESTAMP WHERE key=?', (json.dumps(p), row['key']))
                core['audit'](db, uid, 'test_wallet_payout_'+data['outcome'], 'test_payout', p['id'])
            elif p['status'] != data['outcome']:
                raise core['HttpError'](409, 'This test payout already has a final outcome.')
            db.execute('COMMIT')
            return p
        except Exception:
            db.execute('ROLLBACK')
            raise
    match = re.fullmatch(r'/api/orders/([A-Za-z0-9_-]+)/prepare', path)
    if match and method == 'POST':
        core['require_verified'](ctx)
        oid = match[1]
        db.execute('BEGIN IMMEDIATE')
        try:
            core['trade_workflows'].lock_order(db, oid)
            order = db.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
            if not order or not db.execute('SELECT 1 FROM order_items WHERE order_id=? AND seller_id=?', (oid, uid)).fetchone():
                raise core['HttpError'](404, 'Order not found.')
            core['trade_workflows'].guard(db, oid, core)
            if order['status'] not in ('paid', 'awaiting_delivery'):
                raise core['HttpError'](409, 'This order is not ready to prepare.')
            payment = db.execute('SELECT status FROM payments WHERE order_id=?', (oid,)).fetchone()
            if not payment or payment['status'] != 'succeeded':
                raise core['HttpError'](409, 'Payment must be confirmed before preparing delivery.')
            if order['status'] == 'paid':
                db.execute("UPDATE orders SET status='awaiting_delivery',updated_at=CURRENT_TIMESTAMP WHERE id=?", (oid,))
                core['event'](db, oid, uid, 'paid', 'awaiting_delivery', 'The seller started preparing delivery.')
            db.execute('COMMIT')
            return {'status': 'awaiting_delivery'}
        except Exception:
            db.execute('ROLLBACK')
            raise
    return UNHANDLED
