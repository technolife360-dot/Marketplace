# Desktop release work

The current verification environment uses Stripe sandbox. Production credentials will be configured by the owner in Vercel. Do not change the sandbox adapter to accept live credentials: live checkout and settlement need an explicit adapter and separate reconciliation before activation.

## Verified in this change

- Seller dashboard summary reads the same per-currency Stripe sandbox balances as the wallet, including negative available balances after reversals.
- Seller dashboard requests are batched. Stale render responses cannot overwrite a newer seller render or another route.
- Seller enhancements mount once per listing root. The bulk toolbar exists before the secondary tools attach to it.
- Availability, store performance, listing import and bulk edit each have one visible entry.
- Desktop statistics use the full content width. Listing management and store availability have distinct columns.
- Chrome opened hosted Stripe sandbox Checkout with the same MYR total as the order. No charge was submitted in that check.
- Build passed. 89 JavaScript tests passed. 294 server tests completed with one environment-dependent skip.

## Buyer workflow follow-up

- Desktop orders now separate purchases/sales and active/completed/cancelled-or-refunded states, with search, counts, product images and an explicit refresh action.
- Cart quantity changes preserve recipient fields and reapply coupons against a fresh server quote. Stock/minimum bounds remain server-enforced; an in-flight change blocks another quantity change and checkout.
- Buyer payment/refund cards show the payment amount, not seller net earnings. Seller cards describe historical order earnings and direct the user to the wallet for the current balance.
- Dispute GET exposes whether the current buyer can open a dispute. Sellers and completed/unpaid orders do not receive an unusable opening form. The POST endpoint still independently enforces authorization and state.
- Dispute pages have a desktop reason/form column and an evidence/thread/help column; stale responses cannot replace a different route.
- Browser checks covered quantity 5 → 4 with recipient retention, completed-order payment amount, order status filtering, an eligible paid-order dispute and the completed-order restriction. No new payment, refund or dispute was submitted in these visual checks.
- Follow-up checks: 93 JavaScript tests and 52 payment/order/operations tests passed, plus build validation.

## Bounded history and desktop route audit

- Order history now uses server-side role/status/search filters and a keyset cursor with a maximum of 50 rows (desktop requests 20). Cursor scope includes the user and filters. Matching timestamps cannot duplicate or skip rows between pages.
- The list endpoint selects summaries in two queries per page instead of calling `order_view` for every order. It does not decrypt delivery payloads or serialize full snapshots. At most two item previews per order are returned; desktop displays one.
- Desktop order cards are compact rows, with Previous/Next navigation. Search is debounced and cancels stale requests. The server remains the authority for filtering and access.
- Added buyer/date, buyer/status/date, active-buyer/date, order/date and item/order indexes. Production indexes require the explicit `scripts/migrate_database.py` migration; they have not been applied to production during this work.
- Browser route coverage is recorded in `docs/desktop-route-coverage.json`: 60 named route checks across public, buyer, seller and administrator surfaces. This covers rendering and visible structure, not every dynamic record, button, error state or real-world provider integration.
- Fixed personal data-export/push widgets being injected into Stripe administration screens by a broad `.ops-account` selector.
- Unknown application routes now have a useful 404 view instead of silently showing Home.
- Isolated synthetic SQLite measurement: 10,000 orders, 20 returned, 9,793 response bytes, 10 reads with 1.11 ms median and 1.47 ms maximum. This is a local summary-query measurement, not a site-load or concurrent-user capacity result.

## Remaining release scope

- Review every desktop route and its empty, validation, permission, loading and failed-request states with buyer, seller and moderator roles.
- Prepare a live payment adapter, signed webhook routing, environment-isolated records, durable settlement/refund processing and live Connect onboarding/payout reconciliation. The current Stripe adapter is intentionally sandbox-only.
- Confirm the supplier contract/API and implement its exact product mapping, fulfillment, status callbacks or polling, timeout recovery and reconciliation. A generic API key cannot establish a provider-specific delivery contract.
- Publish the owner's actual fee schedule, support hours, refund/protection windows and business identity; do not invent these values in UI.
- Verify delivery, disputes, refunds, stock reservation and financial reconciliation together before enabling production sales.
- Repeat desktop visual and keyboard checks and measure performance under a documented network profile. Mobile redesign is deferred by the owner.

No production environment changes or deployments were made by this change. “Better than competitors” is a design objective, not a verified outcome of these checks.
