"""Test-only Top Up orders. Never dispatches UC or calls a funded supplier."""
import re
import time

import stripe_test_payments as pay


def enabled(core):
    if core['MODE'] != 'development' and not core['internal_testing_enabled']():
        return False
    try:
        return core['configured_payment_provider']().name == 'stripe_test'
    except RuntimeError:
        return False


def view(db, oid, uid, core):
    row = db.execute('SELECT o.*,p.game_name,p.amount,p.currency package_currency FROM topup_orders o JOIN topup_packages p ON p.id=o.package_id WHERE o.id=? AND o.buyer_id=?', (oid, uid)).fetchone()
    if not row or not pay.read(db, 'topup:'+oid):
        raise core['HttpError'](404, 'Test top-up order not found.')
    order = core['topup_admin_row'](row)
    order.update(mode='stripe_test', total_minor=order['unit_price_minor']*order['quantity'], real_delivery=False)
    return order


def checkout(db, uid, data, core):
    if not enabled(core):
        raise core['HttpError'](503, 'Stripe test Top Up checkout is not configured.')
    if data.get('accept_terms') is not True:
        raise core['HttpError'](400, 'Confirm this is a test order and accept the checkout terms.')
    quantity = data.get('quantity', 1)
    player = data.get('player_id', '')
    server = data.get('server_id', '')
    package_id = data.get('package_id', '')
    request_key = data.get('request_key', '')
    if type(quantity) is not int or not 1 <= quantity <= 99 or not isinstance(player, str) or not re.fullmatch(r'[0-9]{3,40}', player):
        raise core['HttpError'](400, 'Enter a numeric player ID and a quantity from 1 to 99.')
    if not isinstance(server, str) or not re.fullmatch(r'[0-9]{0,10}', server) or not isinstance(request_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', request_key):
        raise core['HttpError'](400, 'Invalid server ID or checkout request key.')
    package = db.execute('SELECT * FROM topup_packages WHERE id=? AND enabled=1', (package_id,)).fetchone()
    if not package or package['price_minor'] <= 0:
        raise core['HttpError'](409, 'This package has no configured test price.')
    if package['game_slug'] in ('mobile-legends',) and not server:
        raise core['HttpError'](400, 'Enter the server ID for this game.')
    request_record = 'topup_request:'+uid+':'+request_key
    db.execute('BEGIN IMMEDIATE')
    try:
        # Lock a stable buyer row so identical requests serialize on PostgreSQL.
        db.execute('UPDATE users SET display_name=display_name WHERE id=?', (uid,))
        prior = pay.read(db, request_record)
        if prior:
            oid = prior['id']
            old = db.execute('SELECT * FROM topup_orders WHERE id=?', (oid,)).fetchone()
            if (old['package_id'], old['quantity'], old['player_id'], old['server_id']) != (package_id, quantity, player, server):
                raise core['HttpError'](409, 'This request key belongs to different top-up details.')
        else:
            oid = core['ident']()
            db.execute('INSERT INTO topup_orders(id,reference,buyer_id,package_id,player_id,server_id,quantity,unit_price_minor,currency,fulfillment_note) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (oid, 'TEST-TU-'+core['secrets'].token_hex(4).upper(), uid, package_id, player, server, quantity, package['price_minor'], 'UZS', 'Stripe TEST only. No UC or supplier delivery.'))
            pay.write(db, request_record, {'id': oid})
            pay.write(db, 'topup:'+oid, {'idempotency_key': core['create_token']()})
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK'); raise
    return {'id': oid, 'mode': 'stripe_test'}


def start(db, oid, uid, core):
    order = view(db, oid, uid, core)
    if order['status'] != 'awaiting_payment':
        raise core['HttpError'](409, 'This test order is no longer awaiting payment.')
    saved = pay.read(db, 'checkout:'+oid)
    if saved:
        if saved['expires_at'] <= time.time():
            raise core['HttpError'](409, 'Test checkout expired. Create a new top-up order.')
        return {'checkout_url': saved['url'], 'mode': 'stripe_test'}
    provider = core['configured_payment_provider']()
    if provider.name != 'stripe_test':
        raise core['HttpError'](503, 'Stripe test is disabled.')
    try:
        result = provider.session(oid, order['total_minor'], order['currency'], pay.read(db, 'topup:'+oid)['idempotency_key'], kind='topup')
    except Exception as exc:
        raise core['HttpError'](503, 'Stripe test checkout is unavailable. Retry from this order.') from exc
    pay.write(db, 'checkout:'+oid, {'id': result['id'], 'url': result['url'], 'expires_at': result['expires_at']})
    return {'checkout_url': result['url'], 'mode': 'stripe_test'}


def receive(db, provider, event, core):
    obj = event['data']['object']; oid = obj.get('client_reference_id', '')
    record = pay.read(db, 'topup:'+oid)
    saved = pay.read(db, 'checkout:'+oid)
    if not record or not saved or saved['id'] != obj.get('id') or obj.get('metadata', {}).get('sentryloot_mode') != 'stripe_test':
        raise core['HttpError'](409, 'Unknown Stripe test top-up checkout.')
    if pay.read(db, 'event:'+event['id']):
        return {'ok': True, 'duplicate': True}
    order = db.execute('SELECT * FROM topup_orders WHERE id=?', (oid,)).fetchone()
    if order['payment_reference']:
        return {'ok': True, 'duplicate': True}
    paid = event['type'] in ('checkout.session.completed', 'checkout.session.async_payment_succeeded')
    if paid and obj.get('payment_status') != 'paid':
        return {'ok': True, 'awaiting_payment': True}
    session = provider.paid_session(saved['id']) if paid else None
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('UPDATE topup_orders SET updated_at=updated_at WHERE id=?', (oid,))
        order = db.execute('SELECT * FROM topup_orders WHERE id=?', (oid,)).fetchone()
        if order['payment_reference']:
            db.execute('COMMIT'); return {'ok': True, 'duplicate': True}
        if paid:
            amount = order['unit_price_minor']*order['quantity']; intent = session['payment_intent']
            if (session.get('client_reference_id') != oid or not pay.matches_amount(session.get('amount_total'), amount, order['currency']) or not pay.matches_amount(intent.get('amount_received'), amount, order['currency'])
                    or session.get('currency', '').upper() != order['currency'] or intent.get('currency', '').upper() != order['currency']
                    or session.get('metadata', {}).get('sentryloot_order') != oid):
                raise core['HttpError'](409, 'Stripe test top-up amount, currency or order mismatch.')
            pay.write(db, 'paid:'+oid, {'intent': intent['id'], 'charge': intent['latest_charge']['id']})
            status = 'paid_test' if order['status'] == 'awaiting_payment' else 'refund_pending'
            db.execute('UPDATE topup_orders SET status=?,payment_reference=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (status, 'stripe_test_'+intent['id'], oid))
            if status == 'refund_pending':
                pay.enqueue(db, oid, 'topup_refund')
            core['notify'](db, order['buyer_id'], 'order', 'Test top-up payment received', 'No UC has been delivered. This is a Stripe test order.', '/topup-order/'+oid)
        else:
            db.execute("UPDATE topup_orders SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='awaiting_payment'", (oid,))
        pay.write(db, 'event:'+event['id'], {'processed': True})
        db.execute('COMMIT'); return {'ok': True}
    except Exception:
        db.execute('ROLLBACK'); raise


def process_refund(db, provider, key, core):
    job = pay.read(db, key); oid = job['order_id']
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('UPDATE topup_orders SET updated_at=updated_at WHERE id=?', (oid,))
        job = pay.read(db, key)
        if job['status'] == 'succeeded':
            db.execute('COMMIT'); return job
        order = db.execute('SELECT * FROM topup_orders WHERE id=?', (oid,)).fetchone()
        result = provider.refund(pay.read(db, 'paid:'+oid)['intent'], order['unit_price_minor']*order['quantity'], 'sentryloot:test:refund:'+oid)
        if result.get('status') != 'succeeded':
            raise RuntimeError('Test refund is pending.')
        db.execute("UPDATE topup_orders SET status='refunded',updated_at=CURRENT_TIMESTAMP WHERE id=?", (oid,))
        job.update(status='succeeded', reference=result['id'])
        pay.write(db, key, job); db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        job.update(status='retry', attempts=job.get('attempts', 0)+1, error='Stripe test refund needs retry.')
        pay.write(db, key, job)
    return {'order_id': oid, 'kind': 'topup_refund', 'status': job['status']}


def route(db, ctx, method, path, data, core):
    if path == '/api/top-up/test-checkout' and method == 'POST':
        uid = core['require_verified'](ctx)
        return checkout(db, uid, data, core)
    match = re.fullmatch(r'/api/top-up/test-orders/([A-Za-z0-9_-]+)(?:/(checkout|cancel|confirm))?', path)
    admin = re.fullmatch(r'/api/admin/payments/stripe-test/topups/([A-Za-z0-9_-]+)/(deliver|refund)', path)
    if not match and not admin:
        return pay.UNHANDLED
    uid = core['require_verified'](ctx)
    if admin:
        core['require_admin'](ctx)
        oid, action = admin.groups()
        row = db.execute('SELECT buyer_id FROM topup_orders WHERE id=?', (oid,)).fetchone()
        if not row:
            raise core['HttpError'](404, 'Test order not found.')
        order = view(db, oid, row['buyer_id'], core)
    else:
        oid, action = match.groups(); order = view(db, oid, uid, core)
    if not action and method == 'GET':
        return order
    if method != 'POST':
        raise core['HttpError'](405, 'Method not allowed.')
    if action == 'checkout':
        return start(db, oid, uid, core)
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('UPDATE topup_orders SET updated_at=updated_at WHERE id=?', (oid,))
        current = db.execute('SELECT status FROM topup_orders WHERE id=?', (oid,)).fetchone()['status']
        if action == 'deliver' and current == 'paid_test':
            status = 'delivered_test'
        elif action == 'confirm' and current == 'delivered_test':
            status = 'completed'
            db.execute('UPDATE topup_orders SET completed_at=? WHERE id=?', (core['now_iso'](), oid))
        elif action in ('cancel', 'refund') and current in ('awaiting_payment', 'paid_test', 'delivered_test', 'completed'):
            status = 'cancelled' if current == 'awaiting_payment' else 'refund_pending'
            if status == 'refund_pending':
                pay.enqueue(db, oid, 'topup_refund')
        else:
            raise core['HttpError'](409, 'This action is unavailable for the current test order state.')
        db.execute('UPDATE topup_orders SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (status, oid))
        core['audit'](db, uid, 'stripe_test_topup_'+action, 'topup_order', oid)
        db.execute('COMMIT'); return {'status': status, 'real_delivery': False}
    except Exception:
        db.execute('ROLLBACK'); raise
