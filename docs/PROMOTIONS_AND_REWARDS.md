# Coupons, vouchers and purchase rewards

## Administration

Open `/#admin-rewards` while signed in as an administrator. Create percentage/fixed coupons or fixed-value personal vouchers, set product scope, expiry, minimum purchase, maximum discount and usage limits. A voucher is claimable by one buyer once; optionally bind it to a user ID. Blank voucher codes are generated securely. Existing campaign terms are immutable: disable a campaign and create another to change its terms. The overview shows credit issued, used, pending and outstanding; campaign rows show actual usage.

Initial settings are 1% account rewards, 0.5% Top Up rewards, a 20% credit redemption cap, 180-day credit expiry and no coupon/credit stacking. Administrators can change these settings. Platform benefits are separate from legacy seller-funded coupons and legacy non-redeemable points.

## Customer flow

Open `/#rewards` from the account benefits/profile links to claim a voucher and inspect available credit, pending credit, refund adjustments and history. Credit has no withdrawal or transfer facility. Account checkout and Top Up provide platform coupon and credit controls. Changing a benefit invalidates the quote until updated. Quotes expire after five minutes and bind the buyer, payment mode, actual products, quantities, currency and price. FX is checked on the server; when unavailable, benefits fail closed and the customer may explicitly continue without benefits.

Delivery confirmation alone does not issue spendable credit: a matching successful verified payment must also exist. Reward earning uses the product amount actually paid after benefits, excluding the checkout fee. Test balances and campaigns cannot be spent in real mode. Fixed values use cents for USD/MYR and whole units for UZS; UI display follows regional preferences using a validated FX snapshot.

## Refunds and funding

Unpaid cancellation releases reserved credit once. Confirmed cash refunds restore used credits with their original expiry and reverse earned rewards. Refund requests/disputes freeze earnings; they do not pretend that cash has been refunded. Spending an earned reward before its source is refunded produces an adjustment owed, offset against future credits. Unspent expired credit creates no debt.

Seller gross entitlement is preserved. Platform-funded discounts lower the buyer payment, not seller earnings. Stripe test settlement supports platform-balance funding when the seller transfer exceeds the net charge; insufficient funds leave settlement pending for retry. Funded platform balance is a prerequisite for actual subsidized settlements.

## Operations and release limits

Records use the existing private, RLS-protected `platform_config` table under `rewards2:`. No schema migration or public Data API access is required. Back up this table with other financial records. Claims, reservations and reversals run transactionally with a shared lock row to serialize competing claims. Do not delete ledger records to adjust a balance.

The current payment adapter remains Stripe **test**, and live sales are closed. No live payment adapter or Top Up supplier has been activated by this feature. A manually entered real Top Up reference cannot mint rewards. Before commercial launch, connect and verify the real payment receipt/refund/settlement adapter, fund the platform subsidy balance, connect a supplier and verify delivery receipts. End-to-end live cash payments, PostgreSQL load behavior and actual supplier delivery still need checks in their configured environment. Changing test to live must never convert test credits into real credits.

Verification used an isolated synthetic local database, real browser/API interactions, signed webhook fixtures with mocked Stripe SDK calls, and refund/concurrency/accounting regression tests. No real customer payment records were modified.
