"""Production startup must not mutate schema or block the public HTML on the DB."""
import io
import unittest
from unittest.mock import Mock, patch

import app


class ProductionStartup(unittest.TestCase):
    def setUp(self):
        self.settings = patch.multiple(app, MODE='production', DATABASE_URL='postgresql://test.invalid/db')
        self.settings.start()
        self.crypto = patch.multiple(app.delivery_crypto, crypto_is_available=lambda: True,
                                     key_is_configured=lambda: True)
        self.crypto.start()
        self.addCleanup(self.crypto.stop)
        self.addCleanup(self.settings.stop)

    def test_api_cold_start_checks_safety_once_without_migrating(self):
        db = Mock()
        db.execute.return_value.fetchone.return_value = None
        application = app.VercelWSGIApplication()
        with patch.object(app, 'connect', return_value=db) as connect, \
             patch.object(app, 'migrate') as migrate, \
             patch.object(app, 'assert_private_postgres_tables') as guard:
            application._startup()
            application._startup()
        migrate.assert_not_called()
        connect.assert_called_once()
        guard.assert_called_once()
        self.assertIn('account_security', guard.call_args.args[1])
        self.assertIn('topup_reviews', guard.call_args.args[1])
        self.assertIn('LIMIT 1', db.execute.call_args.args[0])
        db.close.assert_called_once()

    def test_insecure_schema_still_blocks_api_and_is_not_marked_ready(self):
        db = Mock()
        application = app.VercelWSGIApplication()
        with patch.object(app, 'connect', return_value=db), \
             patch.object(app, 'assert_private_postgres_tables', side_effect=RuntimeError('unsafe RLS')):
            with self.assertRaisesRegex(RuntimeError, 'unsafe RLS'):
                application._startup()
        self.assertFalse(application._startup_complete)
        db.close.assert_called_once()

    def test_unencrypted_deliveries_still_block_api(self):
        db = Mock()
        db.execute.return_value.fetchone.return_value = {'legacy': 1}
        with patch.object(app, 'connect', return_value=db), \
             patch.object(app, 'assert_private_postgres_tables'):
            with self.assertRaisesRegex(RuntimeError, 'Encrypt existing delivery'):
                app.VercelWSGIApplication()._startup()

    def test_home_html_remains_available_when_database_is_unreachable(self):
        application = app.VercelWSGIApplication()
        environ = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/', 'wsgi.input': io.BytesIO()}
        response = {}
        def start_response(status, headers):
            response.update(status=status, headers=dict(headers))
        with patch.object(app, 'connect', side_effect=AssertionError('must not connect')), \
             patch.object(app, 'migrate') as migrate:
            payload = b''.join(application(environ, start_response))
        self.assertTrue(response['status'].startswith('200'), response)
        self.assertIn(b'id="app"', payload)
        migrate.assert_not_called()
        self.assertFalse(application._startup_complete)

    def test_bounded_pool_allows_parallel_borrowers_and_reuses_connections(self):
        pool = app.PostgresConnectionPool()
        connections = [Mock(closed=False) for _ in range(4)]
        with patch.object(pool, '_new_connection', side_effect=connections):
            borrowed = [pool.getconn() for _ in range(4)]
        self.assertEqual(borrowed, connections)
        self.assertEqual(pool.total, 4)
        # Autocommit connections return to the pool only after transaction cleanup.
        connections[0].info.transaction_status = app.psycopg.pq.TransactionStatus.IDLE
        pool.putconn(connections[0])
        self.assertIs(pool.getconn(), connections[0])
        for connection in borrowed:
            pool._discard(connection)
        self.assertEqual(pool.total, 0)

    def test_dynamic_pages_and_apis_cannot_skip_database_safety_checks(self):
        for path in ('/api/me', '/api/top-up/catalog', '/listing/example', '/top-up/pubg-mobile', '/store/seller', '/healthz', '/sitemap.xml'):
            application = app.VercelWSGIApplication()
            with self.subTest(path=path), patch.object(application, '_startup', side_effect=RuntimeError('safety guard')):
                with self.assertRaisesRegex(RuntimeError, 'safety guard'):
                    application({'REQUEST_METHOD': 'GET', 'PATH_INFO': path}, lambda *args: None)
