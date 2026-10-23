"""Opt-in PostgreSQL compatibility checks; all queries run in a read-only transaction.

Run with SENTRYLOOT_TEST_POSTGRES_READONLY=1 and a configured DATABASE_URL.
Never print seller identities or modify the configured database.
"""
import os
import unittest

import app
import seller_verification


@unittest.skipUnless(os.environ.get('SENTRYLOOT_TEST_POSTGRES_READONLY') == '1',
                     'Requires an explicitly enabled PostgreSQL read-only check')
class SellerVerificationPostgres(unittest.TestCase):
    def test_queue_filters_chart_and_detail_on_postgres(self):
        self.assertTrue(app.DATABASE_URL, 'Configure DATABASE_URL for PostgreSQL checks')
        db = app.connect()
        try:
            db.execute('BEGIN')
            db.execute('SET TRANSACTION READ ONLY')
            queue = seller_verification.listing(db, {}, vars(app))
            self.assertIn('chart', queue)
            self.assertEqual(queue['stats']['total'], sum(queue['stats'][key]
                             for key in ('pending', 'approved', 'rejected')))
            for filters in ({'status': ['pending']}, {'status': ['approved']},
                            {'status': ['rejected']}, {'days': ['7']},
                            {'q': ['postgres compatibility check'], 'page': ['2']},
                            {'country': ['UZ']}):
                with self.subTest(filters=filters):
                    result = seller_verification.listing(db, filters, vars(app))
                    self.assertIsInstance(result['items'], list)
            if queue['items']:
                uid = queue['items'][0]['user_id']
                detail = seller_verification.detail(db, uid, vars(app))
                self.assertEqual(detail['user_id'], uid)
                self.assertIsInstance(detail['timeline'], list)
        finally:
            try:
                db.execute('ROLLBACK')
            finally:
                db.close()
