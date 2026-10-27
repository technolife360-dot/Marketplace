#!/usr/bin/env python3
"""Bounded capacity rehearsal. Local writes are disposable; PostgreSQL is read-only.

No provider calls, migrations, credentials or customer records are emitted by the
PostgreSQL mode. This is a small diagnostic, not a million-user certification.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import statistics
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def metrics(samples, elapsed):
    times = sorted(sample['ms'] for sample in samples)
    percentile = lambda p: round(times[max(0, min(len(times)-1, int(len(times)*p+.999)-1))], 2)
    return {'requests': len(samples), 'seconds': round(elapsed, 3),
            'max_response_bytes': max((sample.get('bytes', 0) for sample in samples), default=0),
            'requests_per_second': round(len(samples)/elapsed, 2),
            'failed': sum(sample['status'] != 200 for sample in samples),
            'status_counts': dict(Counter(str(sample['status']) for sample in samples)),
            'latency_ms': {'p50': round(statistics.median(times), 2),
                           'p95': percentile(.95), 'p99': percentile(.99), 'max': round(max(times), 2)}}


def ramp(worker, levels, requests, *, pause=.2):
    phases = []
    for concurrent in levels:
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            samples = list(executor.map(worker, range(requests)))
        result = {'concurrency': concurrent, **metrics(samples, time.perf_counter()-start)}
        groups = defaultdict(list)
        for sample in samples:
            groups[sample['operation']].append(sample)
        result['operations'] = {name: metrics(group, time.perf_counter()-start) for name, group in groups.items()}
        phases.append(result)
        print(json.dumps({'phase': result}), flush=True)
        if result['failed'] or result['latency_ms']['p95'] > 3000:
            result['stopped_ramp'] = True
            break
        time.sleep(pause)
    return phases


def local(registered_users, soak_seconds):
    # Set these before app/test imports. Never fall back to developer credentials.
    os.environ.update(SENTRYLOOT_ENV_FILE='/dev/null', DATABASE_URL='',
                      MARKETPLACE_MODE='development', PAYMENT_PROVIDER='sandbox', EMAIL_PROVIDER='disabled')
    import app
    from tests.test_order_history import OrderHistory
    fixture = OrderHistory()
    fixture.setUp()
    server = None
    try:
        fixture.db.execute('BEGIN')
        fixture.seed_orders(10000)
        # Users have synthetic identities and unusable passwords. No real login
        # credentials or provider calls are involved, and the DB is deleted later.
        fixture.db.execute('''WITH RECURSIVE numbers(n) AS (
            SELECT 1 UNION ALL SELECT n+1 FROM numbers WHERE n<?
        ) INSERT INTO users(id,email,password_hash,display_name,email_verified)
            SELECT 'capacity_user_'||n,'capacity_'||n||'@example.invalid',
                   'unused','Synthetic capacity user',1 FROM numbers''', (registered_users-4,))
        fixture.db.execute('COMMIT')
        seeded_users = fixture.db.execute('SELECT COUNT(*) n FROM users').fetchone()['n']
        cookies = {'purchases': [], 'sales': []}
        for role, uid in (('purchases', fixture.buyer), ('sales', fixture.seller)):
            for _ in range(32):
                token, _ = app.session_create(fixture.db, uid)
                cookies[role].append(app.COOKIE_NAME+'='+token)

        class QuietHandler(app.Handler):
            def log_message(self, *args):
                pass

        server = app.Server(('127.0.0.1', 0), QuietHandler)
        server_backlog = server.request_queue_size
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:'+str(server.server_address[1])
        paths = ['/api/me', '/api/listings?limit=12',
                 '/api/orders?paged=1&role=purchases&limit=20',
                 '/api/orders?paged=1&role=sales&limit=20', '/api/categories', '/api/catalogue/facets']

        def request(i):
            path = paths[i % len(paths)]
            started = time.perf_counter()
            size = 0
            try:
                sessions = cookies['sales' if 'role=sales' in path else 'purchases']
                req = Request(base+path, headers={'Cookie': sessions[i % len(sessions)], 'Accept': 'application/json'})
                with urlopen(req, timeout=8) as response:
                    body = response.read(1024*1024)
                    size = len(body)
                    value = json.loads(body)
                    status = response.status
                    if path.startswith('/api/orders') and (len(value['items']) > 20 or size > 100000):
                        status = 'invalid_summary'
            except HTTPError as error:
                status = error.code
            except URLError as error:
                status = 'URLError:'+type(error.reason).__name__+':'+str(getattr(error.reason, 'errno', ''))
            except Exception as error:
                status = type(error).__name__
            return {'status': status, 'ms': (time.perf_counter()-started)*1000, 'bytes': size, 'operation': path}

        # Warm each operation once, then measure complete HTTP + auth + DB paths.
        warmup = [request(i) for i in range(len(paths))]
        if any(sample['status'] != 200 for sample in warmup):
            raise RuntimeError('Local warmup failed: '+str([s['status'] for s in warmup]))
        phases = ramp(request, (1, 4, 8, 16, 32), 192)
        soak = None
        if soak_seconds and all(not phase['failed'] for phase in phases):
            stop = threading.Event();started = time.perf_counter();deadline = started+soak_seconds
            def continuous(worker):
                samples=[]
                for i in range(6000):
                    if stop.is_set() or time.perf_counter() >= deadline:
                        break
                    sample=request(worker*6000+i);samples.append(sample)
                    if sample['status'] != 200 or sample['ms'] > 5000:
                        stop.set()
                return samples
            with ThreadPoolExecutor(max_workers=16) as executor:
                samples=[sample for group in executor.map(continuous,range(16)) for sample in group]
            soak={'concurrency':16,'target_seconds':soak_seconds,
                  'stopped_early':stop.is_set(),**metrics(samples,time.perf_counter()-started)}
            print(json.dumps({'soak':soak}),flush=True)
        server.shutdown(); server.server_close(); thread.join(timeout=3); server = None

        # Concurrent writes only against this disposable database. No Stripe SDK.
        buyers = []
        for i in range(8):
            uid = 'race_buyer_'+str(i)
            fixture.db.execute('INSERT INTO users(id,email,password_hash,display_name,email_verified) VALUES(?,?,?,?,1)',
                               (uid, uid+'@example.invalid', 'unused', 'Synthetic buyer'))
            fixture.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)', (uid, fixture.listing))
            buyers.append(uid)
        barrier = threading.Barrier(8)

        def checkout(uid):
            db = app.connect()
            try:
                barrier.wait(timeout=5)
                result = app.checkout(db, uid, True, True)
                return {'status': 'reserved', 'order_id': result['id']}
            except app.HttpError as error:
                return {'status': error.status}
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(checkout, buyers))
        winners = [r for r in results if r['status'] == 'reserved']
        reserved = fixture.db.execute('SELECT reserved FROM listings WHERE id=?', (fixture.listing,)).fetchone()['reserved']
        race = {'buyers': 8, 'available_stock': 1, 'successful_reservations': len(winners),
                'conflict_responses': sum(r['status'] == 409 for r in results), 'reserved_after': reserved}
        race['passed'] = len(winners) == 1 and race['conflict_responses'] == 7 and reserved == 1

        # Same checkout key submitted simultaneously must create only one order.
        fixture.db.execute('UPDATE listings SET stock=2 WHERE id=?', (fixture.listing,))
        uid = buyers[0]
        fixture.db.execute('INSERT OR REPLACE INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)', (uid, fixture.listing))
        barrier = threading.Barrier(8)

        def retry_checkout(_):
            db = app.connect()
            try:
                barrier.wait(timeout=5)
                return app.checkout(db, uid, True, True, request_key='capacity_retry_same_key_1234')['id']
            finally:
                db.close()

        orders_before = fixture.db.execute('SELECT COUNT(*) n FROM orders').fetchone()['n']
        with ThreadPoolExecutor(max_workers=8) as executor:
            ids = list(executor.map(retry_checkout, range(8)))
        orders_after = fixture.db.execute('SELECT COUNT(*) n FROM orders').fetchone()['n']
        retry = {'simultaneous_requests': 8, 'unique_orders': len(set(ids)), 'new_database_orders': orders_after-orders_before}
        retry['passed'] = retry['unique_orders'] == 1 and retry['new_database_orders'] == 1
        return {'scope': 'disposable local SQLite + threaded Python HTTP server, warm requests, no think time',
                'seeded_orders': 10000, 'seeded_registered_users': seeded_users,
                'history_sessions': 'purchases authenticated as the buyer; sales authenticated as the seller',
                'http_listener_backlog': server_backlog, 'phases': phases, 'last_item_race': race,
                'soak':soak, 'idempotency_race': retry,
                'passed': all(not p['failed'] for p in phases) and race['passed'] and retry['passed'] and (not soak or not soak['failed'] and not soak['stopped_early'])}
    finally:
        if server:
            server.shutdown(); server.server_close()
        fixture.tearDown()


def postgres():
    import app
    import order_history
    if not app.DATABASE_URL:
        raise RuntimeError('DATABASE_URL is not configured')
    # Max four connections and at most eight queued callers, never an open ramp.
    pool = app.PostgresConnectionPool(max_size=4)

    def borrow():
        db = app.PostgresConnection(pool.getconn(), pool)
        try:
            db.execute('BEGIN READ ONLY')
            db.execute("SET LOCAL statement_timeout='2000ms'")
            db.execute("SET LOCAL lock_timeout='500ms'")
            if db.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] != 'on':
                raise RuntimeError('Read-only transaction was not enforced')
            return db
        except Exception:
            db.close()
            raise

    started = time.perf_counter()
    db = borrow()
    connect_ms = (time.perf_counter()-started)*1000
    try:
        estimates = {row['relname']: int(row['reltuples']) for row in db.execute(
            "SELECT relname,reltuples FROM pg_class WHERE relnamespace='public'::regnamespace AND relname IN ('users','orders','order_items','listings')")}
        indexes = [row['indexname'] for row in db.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename IN ('orders','order_items') ORDER BY indexname")]
        # IDs stay in memory only; results and snapshots are never printed/saved.
        buyer = db.execute('SELECT buyer_id FROM orders ORDER BY created_at DESC LIMIT 1').fetchone()
        seller = db.execute('SELECT seller_id FROM order_items LIMIT 1').fetchone()
        buyer_id = buyer['buyer_id'] if buyer else 'capacity_nonexistent_buyer'
        seller_id = seller['seller_id'] if seller else 'capacity_nonexistent_seller'
    finally:
        db.execute('ROLLBACK'); db.close()

    operations = ('roundtrip', 'purchases', 'sales', 'search')

    def read(i):
        started = time.perf_counter(); db = None
        operation = operations[i % len(operations)]
        try:
            db = borrow()
            if operation == 'roundtrip':
                db.execute('SELECT 1 AS ok').fetchone()
            else:
                qs = {'role': ['sales' if operation == 'sales' else 'purchases'], 'limit': ['20']}
                if operation == 'search':
                    qs['q'] = ['capacity-no-match']
                value = order_history.page(db, seller_id if operation == 'sales' else buyer_id, qs, vars(app))
                if len(value['items']) > 20:
                    raise RuntimeError('Unbounded history')
            status = 200
        except Exception as error:
            # Never print connection strings, query parameters or driver messages.
            status = type(error).__name__
        finally:
            if db:
                db.execute('ROLLBACK'); db.close()
        return {'operation': operation, 'status': status, 'ms': (time.perf_counter()-started)*1000}

    try:
        phases = ramp(read, (1, 2, 4, 8), 16, pause=.5)
        return {'scope': 'configured PostgreSQL via local client, all transactions READ ONLY; not deployed HTTP throughput',
                'cold_connection_and_readonly_setup_ms': round(connect_ms, 2),
                'pool_connections': 4, 'row_estimates_not_exact_counts': estimates,
                'order_index_names': indexes, 'phases': phases,
                'passed': all(not p['failed'] for p in phases)}
    finally:
        pool.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('local', 'postgres-readonly'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--registered-users', type=int, default=10000)
    parser.add_argument('--soak-seconds', type=int, default=0)
    args = parser.parse_args()
    if not 5 <= args.registered_users <= 1000000:
        parser.error('Use 5–1,000,000 synthetic users.')
    if not 0 <= args.soak_seconds <= 120:
        parser.error('Use 0–120 seconds for the local soak.')
    report = local(args.registered_users,args.soak_seconds) if args.mode == 'local' else postgres()
    report['recorded_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'report': str(args.output), 'passed': report['passed']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
