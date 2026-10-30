"""Behavioral regressions for promotional credit accounting and source binding."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app
import rewards_engine as rewards
from tests import test_rewards_engine as engine_fixtures


class RewardsAccountingRisks(unittest.TestCase):
    setUp = engine_fixtures.RewardsEngineTests.setUp
    tearDown = engine_fixtures.RewardsEngineTests.tearDown
    ctx = engine_fixtures.RewardsEngineTests.ctx
    route = engine_fixtures.RewardsEngineTests.route
    rates = engine_fixtures.RewardsEngineTests.rates
    campaign = engine_fixtures.RewardsEngineTests.campaign
    gift = engine_fixtures.RewardsEngineTests.gift
    quote = engine_fixtures.RewardsEngineTests.quote
    reserve = engine_fixtures.RewardsEngineTests.reserve
    state = engine_fixtures.RewardsEngineTests.state
    wallet = engine_fixtures.RewardsEngineTests.wallet

    def test_actual_public_fx_snapshot_shape_is_accepted(self):
        snapshot = {'base': 'USD', 'rates': {'USD': 1, 'UZS': 12500, 'MYR': 4},
                    'dates': {}, 'updated_at': int(time.time()),
                    'expires_at': int(time.time()) + 21600, 'stale': False, 'estimate_only': True}
        with patch.object(app.regional_preferences, 'exchange_rates', return_value=snapshot):
            self.assertEqual(rewards.rates(vars(app))['rates']['UZS'], '12500')

    def test_topup_units_are_not_used_as_payment_currency(self):
        package = self.db.execute("SELECT id,currency FROM topup_packages WHERE game_slug='pubg-mobile' LIMIT 1").fetchone()
        self.assertNotEqual(package['currency'], 'UZS')
        self.db.execute('UPDATE topup_packages SET price_minor=10000,enabled=1 WHERE id=?', (package['id'],))
        with self.rates():
            quote = self.route(self.buyer, 'POST', '/api/rewards/quote',
                               {'kind': 'topup', 'package_id': package['id'], 'quantity': 2})
        self.assertEqual((quote['currency'], quote['subtotal_minor']), ('UZS', 20000))

    def test_campaign_minimum_is_converted_from_campaign_currency(self):
        # 50,000 UZS = $4.00, so a USD $5 minimum must reject this cart.
        self.campaign(kind='coupon', code='MINIMUM5', value=1000, discount_type='percent', minimum_minor=500)
        with self.assertRaises(app.HttpError):
            self.quote(coupon_code='MINIMUM5')
        self.db.execute('UPDATE listings SET price_minor=62500 WHERE id=?', (self.listing,))
        self.assertEqual(self.quote(coupon_code='MINIMUM5')['discount_minor'], 6250)

    def test_spent_earnings_create_debt_and_new_credit_offsets_it(self):
        earned_order, _ = self.reserve(self.quote())
        self.state(earned_order, 'completed', 'succeeded')
        earned = self.wallet()['available_micro']
        spent_order, spent = self.reserve(self.quote(use_bonus=True))
        self.assertEqual(spent['spent_micro'], earned)
        self.state(earned_order, 'refunded', 'refunded')
        self.assertEqual(self.wallet()['debt_micro'], earned)
        self.gift()
        self.assertEqual(self.wallet()['available_micro'], 10000000 - earned)
        # Releasing the second reservation returns the original earned lot;
        # its revocation still prevents it from becoming purchasing power.
        self.state(spent_order, 'cancelled', 'expired')
        self.assertEqual(self.wallet()['available_micro'], 10000000)
        self.assertEqual(self.wallet()['debt_micro'], 0)

    def test_unused_expired_earnings_do_not_turn_into_refund_debt(self):
        oid, _ = self.reserve(self.quote())
        self.state(oid, 'completed', 'succeeded')
        record = rewards.purchase(self.db, 'account', oid)
        key = rewards.key_for('lot', self.buyer, record['earn_lot_id'])
        lot = rewards.read(self.db, key)
        lot['expires_at'] = int(time.time()) - 1
        rewards.write(self.db, key, lot)
        self.assertEqual(self.wallet()['available_micro'], 0)
        self.state(oid, 'refunded', 'refunded')
        self.assertEqual(self.wallet()['debt_micro'], 0)

    def test_refund_restore_preserves_original_credit_expiry(self):
        self.gift()
        oid, _ = self.reserve(self.quote(use_bonus=True))
        record = rewards.purchase(self.db, 'account', oid)
        allocation = record['allocations'][0]
        key = rewards.key_for('lot', self.buyer, allocation['lot_id'])
        lot = rewards.read(self.db, key)
        lot['expires_at'] = int(time.time()) - 1
        rewards.write(self.db, key, lot)
        self.state(oid, 'refunded', 'refunded')
        self.assertEqual(rewards.read(self.db, key)['expires_at'], lot['expires_at'])
        self.assertEqual(self.wallet()['available_micro'], 0)

    def test_existing_source_cannot_be_overwritten_by_another_quote(self):
        first = self.quote()
        oid, _ = self.reserve(first)
        second = self.quote()
        lines, currency, subtotal, fee = rewards.context(self.db, self.buyer, {'kind': 'account'}, vars(app))
        self.db.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(app.HttpError):
                rewards.reserve(self.db, self.buyer, second['id'], 'account', oid,
                                lines, currency, subtotal, fee, vars(app))
        finally:
            self.db.execute('ROLLBACK')
        self.assertEqual(rewards.purchase(self.db, 'account', oid)['quote_id'], first['id'])

    def test_changed_order_payment_tuple_cannot_award_credits(self):
        oid, _ = self.reserve(self.quote())
        self.db.execute("UPDATE orders SET status='completed',total_minor=1 WHERE id=?", (oid,))
        self.db.execute("UPDATE payments SET status='succeeded' WHERE order_id=?", (oid,))
        self.db.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(app.HttpError):
                rewards.sync_order(self.db, oid, vars(app))
        finally:
            self.db.execute('ROLLBACK')
        self.assertEqual(self.wallet()['available_micro'], 0)

    def make_topup(self):
        package = self.db.execute("SELECT id FROM topup_packages WHERE game_slug='pubg-mobile' LIMIT 1").fetchone()['id']
        self.db.execute('UPDATE topup_packages SET price_minor=10000,enabled=1 WHERE id=?', (package,))
        data = {'kind': 'topup', 'package_id': package, 'quantity': 2}
        with self.rates():
            quote = rewards.quote(self.db, self.buyer, data, vars(app))
        lines, currency, subtotal, fee = rewards.context(self.db, self.buyer, data, vars(app))
        oid = app.ident()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            rewards.reserve(self.db, self.buyer, quote['id'], 'topup', oid,
                            lines, currency, subtotal, fee, vars(app))
            self.db.execute("INSERT INTO topup_orders(id,reference,buyer_id,package_id,player_id,quantity,unit_price_minor,currency,status) VALUES(?,?,?,?,?,2,10000,'UZS','completed')",
                            (oid, oid, self.buyer, package, '12345678'))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        return oid

    def sync_topup(self, oid):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            rewards.sync_topup(self.db, oid, vars(app))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def test_topup_reward_requires_exact_verified_net_payment(self):
        oid = self.make_topup()
        self.db.execute("UPDATE topup_orders SET payment_reference='stripe_test_pi_fixture' WHERE id=?", (oid,))
        rewards.write(self.db, 'stripe_test:topup:' + oid, {})
        rewards.write(self.db, 'stripe_test:paid:' + oid,
                      {'intent': 'pi_fixture', 'amount_minor': 1, 'currency': 'UZS'})
        self.sync_topup(oid)
        self.assertEqual(self.wallet()['available_micro'], 0)
        rewards.write(self.db, 'stripe_test:paid:' + oid,
                      {'intent': 'pi_fixture', 'amount_minor': 20000, 'currency': 'MYR'})
        self.sync_topup(oid)
        self.assertEqual(self.wallet()['available_micro'], 0)
        rewards.write(self.db, 'stripe_test:paid:' + oid,
                      {'intent': 'pi_fixture', 'amount_minor': 20000, 'currency': 'UZS'})
        self.sync_topup(oid)
        self.assertEqual(self.wallet()['available_micro'], 8000)

    def test_manually_entered_live_topup_reference_does_not_mint_credit(self):
        with patch.object(app, 'configured_payment_provider', return_value=SimpleNamespace(name='future_live_provider')):
            oid = self.make_topup()
            self.db.execute("UPDATE topup_orders SET payment_reference='manual_admin_reference' WHERE id=?", (oid,))
            self.sync_topup(oid)
            self.assertEqual(self.wallet()['available_micro'], 0)

    def test_global_voucher_claim_serializes_different_buyers(self):
        with self.rates():
            self.campaign()
        outcomes = []
        barrier = threading.Barrier(2)

        def claim(uid):
            db = app.connect()
            try:
                barrier.wait(timeout=10)
                rewards.claim(db, uid, {'code': 'GIFT123456789'}, vars(app))
                outcomes.append(('success', uid))
            except app.HttpError as error:
                outcomes.append(('rejected', error.status))
            except Exception as error:
                outcomes.append(('unexpected', type(error).__name__))
            finally:
                db.close()

        with self.rates():
            threads = [threading.Thread(target=claim, args=(uid,)) for uid in (self.buyer, self.other)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
        self.assertEqual(sorted(result[0] for result in outcomes), ['rejected', 'success'])
        self.assertEqual(sum(rewards.wallet_values(self.db, uid, 'test')['available_micro']
                             for uid in (self.buyer, self.other)), 10000000)


if __name__ == '__main__':
    unittest.main()
