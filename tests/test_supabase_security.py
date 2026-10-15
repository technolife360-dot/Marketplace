import unittest
from unittest.mock import Mock

import app


class SupabaseSecurityTests(unittest.TestCase):
    def test_all_browser_table_privileges_are_checked(self):
        db = Mock()
        db.execute.return_value.fetchall.return_value = [
            {'relname': 'users', 'relrowsecurity': True, 'anon_access': False, 'authenticated_access': True}
        ]
        with self.assertRaisesRegex(RuntimeError, 'users'):
            app.assert_private_postgres_tables(db, ('users',))
        sql, params = db.execute.call_args.args
        self.assertIn('SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER', sql)
        self.assertEqual(params, ('users',))

    def test_missing_or_unprotected_tables_fail_closed(self):
        db = Mock()
        db.execute.return_value.fetchall.return_value = [
            {'relname': 'users', 'relrowsecurity': False, 'anon_access': False, 'authenticated_access': False}
        ]
        with self.assertRaisesRegex(RuntimeError, 'topup_orders'):
            app.assert_private_postgres_tables(db, ('users', 'topup_orders'))
        with self.assertRaisesRegex(RuntimeError, 'users'):
            app.assert_private_postgres_tables(db, ('users',))


if __name__ == '__main__':
    unittest.main()
