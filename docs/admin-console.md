# SentryLoot administrative console

The existing vanilla JavaScript/Python application now has a black administrative console, using the existing brand logo and orange accent. Seller verification and all existing moderation actions are retained. Navigation connects orders, users, listings, payouts, support, reviews, catalogue readiness, content and staff/business settings.

## Accounting definitions

- Reports are separated by currency and by live, sandbox or Stripe test book. No conversion or cross-book addition is performed.
- Marketplace GMV is the merchandise subtotal of successfully paid, non-cancelled/non-refunded orders created in the selected period. Buyer checkout fees are excluded from GMV.
- Revenue is the signed sum of recognized platform commission ledger entries posted in the period. Escrow holds are excluded. Stripe test commission reversals subtract from revenue.
- Expenses are admin-entered journal records, attributed to their incurred UTC date. Void operations retain the original record and an audit event. An idempotency key prevents duplicate expense creation.
- Recorded profit is recognized revenue minus recorded, non-voided expenses. It is not a bank balance or a complete tax statement. Unrecorded costs cannot be deducted automatically.
- Game breakdown allocates order-level recognized commission in proportion to item value and reconciles rounding to the ledger total.
- Top Up supplier margin is excluded; the interface states this explicitly.
- Daily chart values also have an accessible table and a CSV export. The chart does not fabricate missing days: those days are zero.

The server enforces admin authorization and its existing production MFA requirement. Existing CSRF protection applies to expense writes. No browser credentials or payment-provider calls were added. Audit reporting excludes arbitrary freeform audit payloads.

## Database prerequisite before merge/deployment

The migration is `supabase/migrations/20261028000000_admin_finance.sql`. It adds a private expense journal and reporting indexes; it does not modify orders, payments, ledger values or provider configuration. It enables RLS and revokes direct browser-role privileges on the new journal.

**Status: prepared, not applied.** Automatic approval review rejected applying the migration to the connected real project because explicit authorization for that database change was missing. Do not merge/deploy the branch until the owner authorizes and applies this migration. The production startup guard verifies that the journal exists and remains private.

For SQLite development, normal `app.migrate()` creates the journal. Do not run a local seed against production. The QA preview uses only `/tmp/sentryloot-admin-qa.sqlite3` and clearly labeled synthetic sandbox records.

## Verification

- `npm run build` passed.
- `npm test`: 110 Node tests passed; 312 Python tests ran, 311 passed and one optional PostgreSQL integration check skipped.
- Eight new finance tests cover authorization, books/currencies, revenue versus GMV/escrow, reversals, input validation, idempotency, audit-preserving voids, list bounds and MYR units.
- Browser checks: expense save/void/recalculation, CSV download, audit search, seller verification, orders, site-management navigation, mobile drawer, Escape, desktop and 390px mobile layouts.
- Focused fields use one visible border and no secondary focus halo; compound search/configuration controls keep the boundary on the outer control. Native values and select-menu.js remain intact.
- No browser console errors were observed during the final checks.
- Live PostgreSQL financial data and real payment information were not inspected. Production execution remains unverified pending the migration approval.
