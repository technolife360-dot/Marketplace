"""Opt-in PostgreSQL reporting regression tests on connection-local TEMP fixtures.

Enable SENTRYLOOT_TEST_POSTGRES_TEMP=1 with DATABASE_URL configured. Every table
used by report() is shadowed by a temporary synthetic fixture. No application
rows are read or changed. ROLLBACK removes all fixtures after every test.
"""
import json
import os
import unittest

import app
import admin_console


@unittest.skipUnless(os.environ.get('SENTRYLOOT_TEST_POSTGRES_TEMP') == '1',
                     'Requires explicitly enabled PostgreSQL TEMP-only fixtures')
class AdminConsolePostgres(unittest.TestCase):
    def setUp(self):
        self.assertTrue(app.DATABASE_URL, 'Configure DATABASE_URL for PostgreSQL tests')
        self.db = app.connect()
        self.db.execute('BEGIN')
        self.addCleanup(self.cleanup_database)
        schema = {
            'orders': 'id TEXT,currency TEXT,payment_mode TEXT,created_at TEXT,status TEXT,subtotal_minor BIGINT,reference TEXT',
            'ledger_entries': 'id TEXT,order_id TEXT,entry_type TEXT,currency TEXT,created_at TEXT,amount_minor BIGINT',
            'order_items': 'order_id TEXT,listing_id TEXT,quantity INTEGER,unit_price_minor BIGINT',
            'payments': 'order_id TEXT,status TEXT,provider TEXT',
            'listings': 'id TEXT,game_id TEXT',
            'games': 'id TEXT,name TEXT,slug TEXT',
            'admin_expenses': 'id TEXT,amount_minor BIGINT,currency TEXT,book TEXT,category TEXT,description TEXT,incurred_on TEXT,created_at TEXT,voided_at TEXT,void_reason TEXT',
        }
        # All report dependencies must resolve to these fixtures in pg_temp,
        # which PostgreSQL searches before public. No public table is modified.
        for table, columns in schema.items():
            self.db.execute(f'CREATE TEMP TABLE {table} ({columns}) ON COMMIT DROP')
        for table in schema:
            relation = self.db.execute('SELECT pg_my_temp_schema()=relnamespace AS temporary FROM pg_class WHERE oid=to_regclass(?)', (table,)).fetchone()
            self.assertTrue(relation['temporary'], table)
        self.core = vars(app)
        self.day = str(admin_console.today())
        self.filters = {'start':[self.day], 'end':[self.day], 'book':['sandbox'], 'currency':['UZS']}

    def cleanup_database(self):
        try:
            self.db.execute('ROLLBACK')
        finally:
            self.db.close()

    def test_empty_postgres_report_has_valid_sql_and_json(self):
        result = admin_console.report(self.db, self.filters, self.core)
        self.assertEqual(result['revenue_minor'], 0)
        self.assertEqual(result['expense_minor'], 0)
        self.assertEqual(len(result['daily']), 1)
        json.dumps(result)

    def test_postgres_aggregates_numeric_values_and_game_shares_serialize(self):
        stamp = self.day+' 12:00:00'
        self.db.execute("INSERT INTO orders VALUES('qa-order','UZS','sandbox',?,'completed',10000,'QA-ONLY')", (stamp,))
        self.db.execute("INSERT INTO ledger_entries VALUES('qa-fee','qa-order','platform_commission','UZS',?,501)", (stamp,))
        self.db.execute("INSERT INTO payments VALUES('qa-order','succeeded','sandbox')")
        self.db.execute("INSERT INTO games VALUES('game-one','QA game one','qa-one'),('game-two','QA game two','qa-two')")
        self.db.execute("INSERT INTO listings VALUES('listing-one','game-one'),('listing-two','game-two')")
        self.db.execute("INSERT INTO order_items VALUES('qa-order','listing-one',1,3333),('qa-order','listing-two',1,6667)")
        self.db.execute("INSERT INTO admin_expenses VALUES('qa-expense',200,'UZS','sandbox','infrastructure','QA only',?,?,NULL,'')", (self.day, stamp))
        result = admin_console.report(self.db, self.filters, self.core)
        self.assertEqual((result['gmv_minor'], result['revenue_minor'], result['expense_minor'], result['profit_minor']), (10000, 501, 200, 301))
        self.assertEqual(sum(row['amount_minor'] for row in result['games']), 501)
        self.assertEqual(result['categories'][0]['amount_minor'], 200)
        self.assertIsInstance(result['categories'][0]['amount_minor'], int)
        json.dumps(result)
