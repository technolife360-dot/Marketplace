"""The owner-authorized self-approval exception is limited to one test admin."""
import json
import unittest
from unittest.mock import patch

import app
from tests import test_marketplace as fixtures


class AccountReviewPermissions(unittest.TestCase):
    setUp = fixtures.MarketplaceFlows.setUp
    tearDown = fixtures.MarketplaceFlows.tearDown
    ctx = fixtures.MarketplaceFlows.ctx
    route = fixtures.MarketplaceFlows.route

    def pending_review(self, provider='sandbox'):
        self.db.execute("UPDATE users SET email='admin@gamestorehub.com' WHERE id=?", (self.admin,))
        self.db.execute('UPDATE listings SET stock=1,reserved=0 WHERE id=?', (self.listing,))
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)', (self.admin, self.listing))
        order = app.checkout(self.db, self.admin, True, True)
        oid = order['id']
        self.db.execute("UPDATE orders SET status='under_review',payment_mode=? WHERE id=?", (provider, oid))
        self.db.execute("UPDATE payments SET status='succeeded',provider=? WHERE order_id=?", (provider, oid))
        self.db.execute("INSERT INTO account_reviews(order_id,buyer_id,status) VALUES(?,?,'pending')", (oid, self.admin))
        for slot in (1, 2):
            self.db.execute('INSERT INTO account_review_evidence(order_id,slot,object_path) VALUES(?,?,?)', (oid, slot, f'private/{oid}-{slot}.webp'))
        if provider == 'stripe_test':
            app.stripe_test_payments.ledger(self.db, oid, self.seller, 'stripe_test_hold', 45000, 'UZS', vars(app))
        return oid

    def approve(self, oid, action='approve', **extra):
        with patch.object(app, 'require_private_evidence_bucket'):
            return self.route(self.admin, 'POST', '/api/admin/account-reviews/'+oid,
                              {'action': action, 'note': 'Reviewed both private test screenshots.', **extra})

    def assert_forbidden(self, oid, **data):
        with self.assertRaises(app.HttpError) as caught:
            self.approve(oid, **data)
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (oid,)).fetchone()['status'], 'under_review')

    def test_only_named_verified_admin_can_self_approve_paid_test_orders(self):
        for provider in ('sandbox', 'stripe_test'):
            with self.subTest(provider=provider):
                oid = self.pending_review(provider)
                self.assertEqual(self.approve(oid)['status'], 'completed')
                audit = self.db.execute("SELECT actor_id,details_json FROM audit_logs WHERE entity_id=? AND action='account_review_approve'", (oid,)).fetchone()
                self.assertEqual(audit['actor_id'], self.admin)
                self.assertTrue(json.loads(audit['details_json'])['test_self_approval'])
                if provider == 'stripe_test':
                    balance = app.order_process.wallet(self.db, self.seller)['balances']
                    self.assertEqual(next(b for b in balance if b['currency'] == 'UZS')['available_minor'], 45000)

    def test_other_admin_cannot_claim_exception_in_request_json(self):
        oid = self.pending_review()
        self.db.execute("UPDATE users SET email='another-admin@gamestorehub.com' WHERE id=?", (self.admin,))
        self.assert_forbidden(oid, email='admin@gamestorehub.com', test_self_approval=True)

    def test_email_alone_never_grants_admin_or_bypasses_verification(self):
        oid = self.pending_review()
        self.db.execute('UPDATE users SET email_verified=0 WHERE id=?', (self.admin,))
        self.assert_forbidden(oid)
        self.db.execute('UPDATE users SET email_verified=1 WHERE id=?', (self.admin,))
        self.db.execute('DELETE FROM admin_accounts WHERE user_id=?', (self.admin,))
        self.assert_forbidden(oid)

    def test_live_unpaid_and_mismatched_payment_modes_cannot_use_exception(self):
        oid = self.pending_review()
        for mode, provider, status in [('stripe', 'stripe', 'succeeded'), ('sandbox', 'sandbox', 'pending'), ('stripe_test', 'sandbox', 'succeeded')]:
            with self.subTest(mode=mode, provider=provider, status=status):
                self.db.execute('UPDATE orders SET payment_mode=? WHERE id=?', (mode, oid))
                self.db.execute('UPDATE payments SET provider=?,status=? WHERE order_id=?', (provider, status, oid))
                self.assert_forbidden(oid)

    def test_other_review_actions_and_independence_checks_remain_protected(self):
        oid = self.pending_review()
        for action in ('request_info', 'refund_buyer'):
            self.assert_forbidden(oid, action=action)
        with self.assertRaises(app.HttpError):
            app.require_independent_admin(self.ctx(self.admin), self.admin, (self.seller,))

    def test_production_mfa_is_required_before_exception(self):
        oid = self.pending_review()
        app.MODE = 'production'
        with patch.object(app.marketplace_operations, 'enabled', return_value=False):
            self.assert_forbidden(oid)

    def test_exception_does_not_skip_both_private_evidence_files(self):
        oid = self.pending_review()
        self.db.execute('DELETE FROM account_review_evidence WHERE order_id=? AND slot=2', (oid,))
        with self.assertRaises(app.HttpError) as caught:
            self.approve(oid)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?', (oid,)).fetchone()['status'], 'under_review')
