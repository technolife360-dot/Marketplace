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

**Status: applied after explicit owner approval on 2026-10-29 (Asia/Kuala_Lumpur).** Supabase confirmed the migration succeeded. A metadata-only check verified the new journal exists, RLS is enabled, anon/authenticated have no direct table privileges, and both reporting indexes exist. The production startup guard verifies that the journal remains private.

For SQLite development, normal `app.migrate()` creates the journal. Do not run a local seed against production. The QA preview uses only `/tmp/sentryloot-admin-qa.sqlite3` and clearly labeled synthetic sandbox records.

## Verification

- `npm run build` passed.
- `npm test`: 110 Node tests passed; 312 Python tests ran, 311 passed and one optional PostgreSQL integration check skipped.
- Eight new finance tests cover authorization, books/currencies, revenue versus GMV/escrow, reversals, input validation, idempotency, audit-preserving voids, list bounds and MYR units.
- Browser checks: expense save/void/recalculation, CSV download, audit search, seller verification, orders, site-management navigation, mobile drawer, Escape, desktop and 390px mobile layouts.
- Focused fields use one visible border and no secondary focus halo; compound search/configuration controls keep the boundary on the outer control. Native values and select-menu.js remain intact.
- No browser console errors were observed during the final checks.
- Live PostgreSQL financial data and real payment information were not inspected. The schema prerequisite is verified; financial values were tested only against isolated local QA records.

## PostgreSQL alias regression

The first production finance request exposed a PostgreSQL-only syntax error: `day` requires an explicit `AS` when used as a column alias. Both income and expense date queries now use `AS day`, matching the existing overview query convention. SQLite had accepted the previous syntax.

Two opt-in PostgreSQL integration tests now execute the real report function against empty and populated connection-local temporary fixtures, including numeric aggregate serialization and game allocation totals. They reproduced the original SyntaxError before the fix and passed afterwards. All report dependencies are shadowed in `pg_temp`, verified before execution, and removed with ROLLBACK. No existing financial rows are read or changed.

Run with a configured database connection:

```sh
SENTRYLOOT_TEST_POSTGRES_TEMP=1 python3 -m unittest tests.test_admin_console_postgres -v
```

Without the opt-in variable, these database integration checks are explicitly skipped by the normal test suite. After the fix, the full suite passed: 110 frontend tests; 314 Python tests ran, 311 passed and three opt-in checks skipped. Both new PostgreSQL TEMP-fixture tests also passed in a separate opt-in run.

## Shared admin background

The admin shell, body, workspace, sidebar, cards, tables and existing specialized admin panels share the same `#000000` canvas. Borders and interactive focus/hover states distinguish controls without introducing a second page background. The finance fix was verified through the owner's signed-in Chrome tab: both charts loaded and no internal-error message remained.
