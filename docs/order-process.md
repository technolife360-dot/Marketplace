# Stripe test order flow

The four-stage pages are served by `static/order-process.js` and scoped CSS.
Buy now still sets the chosen cart quantity. The review page collects only the
snapshotted delivery identifiers, shows the server's checkout fee and total,
and creates a payment-pending order. It does not mark a payment successful.

## Payments and delivery

- Configure `PAYMENT_PROVIDER=stripe_test`, `STRIPE_TEST_SECRET_KEY`,
  `STRIPE_TEST_ACCOUNT_ID`, `STRIPE_TEST_WEBHOOK_SECRET` and `PUBLIC_BASE_URL`.
  Production test deployments also need the existing explicit internal-testing
  switch. Live keys/objects are rejected by this adapter.
- The Pay button opens Stripe-hosted test Checkout. Only Stripe test cards may
  be used. A signed webhook verifies the session, payment amount, currency and
  associated order before crediting pending test funds.
- `POST /api/orders/:id/stripe-confirmation` can recover a delayed callback on
  return. It retrieves the registered session from Stripe server-side and uses
  the same validation/transaction as the webhook. Browser success flags are
  ignored. Local testing can use this return path without a public webhook
  tunnel; a private local signing secret does not replace the production secret.
- The new review page requires Stripe test mode. It fails closed rather than
  substituting the old local simulator. Existing sandbox orders remain labeled
  as older simulator orders; they are never retroactively called Stripe payments.
- Checkout request keys recover a lost creation response without another order
  or stock reservation. The browser clears a key after successful creation so
  a later intentional purchase can create its own order. Quote checks prevent
  charging a different total/currency than the buyer reviewed.
- Only a participating seller can start preparing a successfully paid order.
  Delivery remains encrypted, quantity-bounded and idempotent. The confirmation
  screen does not submit until the seller presses Mark as delivered.
- Non-account orders require full delivery and buyer acceptance. Existing
  account orders still require two privacy-redacted screenshots and independent
  moderator approval. Cancellation/dispute pauses and service milestones remain
  enforced by the server. Secondary evidence, appeals and cancellation controls
  live in one accordion rather than the current-step card.
- The owner-authorized exception lets only the email-verified, existing full
  administrator `admin@gamestorehub.com` approve their own paid test account order.
  Production admin MFA, both private screenshots, review state and test-payment
  checks still apply. The audit entry records `test_self_approval: true`. Other
  administrators, live payments, disputes, payouts, seller KYC and non-approval
  review actions retain their independent-review requirements. Email matching
  alone never grants admin access.

## Isolated wallet

`GET /api/seller/test-wallet` reads only `stripe_test_hold` and
`stripe_test_earning` entries belonging to that seller and Stripe test orders.
Each currency is separate; there is no fabricated FX conversion. It never adds
test credits to `seller_earning` or the real `/api/payouts` balance.

On accepted completion, internal test credits move from Pending to Available
once under the order lock. This is an internal test entitlement, not a claim
that Stripe has settled cash or that a bank transfer occurred. The existing
Connect transfer outbox is separate and still requires a linked test Connect
account. Refund/dispute states freeze the displayed available entitlement;
confirmed refunds reverse it. Negative balances after a later reversal remain
visible rather than being hidden.

`POST /api/seller/test-wallet/payouts` reserves available test credits in the
chosen currency. The seller must explicitly send `test_only:true`. Test payout
completion is a bank-leg simulation with explicit success/failure controls.
Failure releases the reservation; success consumes it once. Request keys,
seller locks, exact ownership and terminal-state checks prevent double spending
or changing another seller's payout. These routes never call a real bank.

Test order reviews are private records on the order. They cannot enter public
verified-purchase ratings or sales counts.

## Verification

Automated workflows cover signed test payments, unpaid returns, replayed
events, checkout retry/quote changes, prepare authorization, repeated delivery,
Pending → Available, currency/ownership boundaries, test payouts and refunds.
Real Stripe sandbox Checkout was also exercised using an isolated loopback
database: pay with a Stripe test card → pending credit → seller delivery → buyer
confirmation → available credit → simulated payout failure → credit restored.
No live funds, real supplier fulfillment, production migration or deployment
is part of this local verification.

## Required completion review

Completed Stripe test purchases require an explicit 1–5 rating and a review of
at least five non-whitespace characters before the buyer leaves the order flow.
The server's buyer-scoped `/api/orders/review-required` endpoint restores the
required step after reload; navigation attempts preserve the typed form. Saving
invalid or missing fields is disabled in the UI and rejected by the server.
A successful save replaces the order screen with Home. Test feedback remains
private and does not inflate public ratings. Browser/tab closing is not blocked.

Public catalogue, saved cards, comparison lists and related offers omit listings
with no available stock. Sold listings and their order snapshots remain readable
for purchase history; listings with remaining stock stay available.
