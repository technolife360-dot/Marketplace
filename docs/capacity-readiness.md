# Capacity: registered users versus concurrent activity

One million registered accounts is not a measured capacity claim. The relevant inputs are concurrent active sessions, peak requests per second, catalogue/search volume, paid orders per minute, message rate, database size and provider latency. Current production capacity has not been load-tested.

## Implemented protections

- Public static assets are separated from authenticated APIs; private responses are not shared public cache entries.
- PostgreSQL connection pools are bounded to 1–8 connections per process (default 4). Multiple Vercel instances multiply that count; a suitable Supabase pooler and a deployment-wide connection budget are still required.
- Order history responses and their item previews are bounded. Role, status and search filtering run on the server. Cursor pagination avoids increasingly expensive OFFSET pages and unbounded DOM growth.
- List views do not fetch private deliveries, event histories or full payment details. These remain on the authorized detail endpoint.
- Authentication and MFA are checked for every request. Session/user activity heartbeats are written at most once a minute, with compare-and-update conditions for racing requests. Repeated authenticated reads no longer perform unconditional session writes.
- Payment callbacks, stock reservations and settlement/refund operations already have idempotency and authorization tests. These are correctness checks, not a throughput benchmark.

## Before claiming production capacity

1. Choose a target concurrent session count and requests/paid-orders per second. Record the Vercel/Supabase plans, region, pooler limits and maximum connection budget.
2. Apply and verify the order-history indexes with the explicit migration. For an already large production database, schedule index creation appropriately; use PostgreSQL concurrent index creation through an operator-reviewed migration rather than blocking a busy table.
3. Run staging load tests with representative search, catalogue, history, messages and payment-webhook traffic. Use dedicated fixtures and sandbox providers. Never mix test payments into live balances.
4. Measure API p50/p95/p99, error rate, database CPU/IO/connections/lock waits, memory, external-provider latency and queue age. Compare cold and warm requests. Test a gradual ramp, peak spike and longer soak.
5. Validate stock oversell prevention and financial idempotency under concurrent writes, not only independent reads. Reconcile expected and actual totals after the run.
6. Move time-sensitive fulfillment and settlement to retryable workers/queues with monitoring before high order volume. The current once-daily deadline cron and its bounded scan are not sufficient as a real-time high-volume delivery service.
7. Review remaining account-history readers (wallet ledger, seller insights, favorite collections), report/search indexes and retention policies as data grows. A bounded orders page alone does not establish whole-site scalability.
8. Set alerts and rollback criteria. Confirm backup restoration and provider-outage recovery in staging.

## Reproducible result from this change

A disposable local SQLite fixture with 10,000 orders returned a 20-order page in two SQL statements. The JSON response was 9,793 bytes. Ten reads had 1.11 ms median / 1.47 ms maximum in that local environment. It did not measure network latency, PostgreSQL production behavior or simultaneous users. No promise about one million concurrent visitors follows from this result.

Run the disposable fixture benchmark with `python scripts/benchmark_order_history.py` in the project verification environment. It creates and tears down its own test database.

## Parallel rehearsal, 27 October 2026

The repeatable harness is `scripts/qa_capacity.py`. Its local mode explicitly disables developer environment loading and creates a disposable database. Its PostgreSQL mode never migrates or seeds the configured database; every operation is enclosed in `BEGIN READ ONLY` with a 2-second statement timeout, a 500 ms lock timeout and at most four pooled connections. The sanitized results are saved in `docs/capacity-results-2026-10-27.json`.

Local dataset: **1,000,000 synthetic registered users and 10,000 orders**, concentrated on one buyer and seller. Buyer and seller history calls use separate authenticated roles. The mixed HTTP workload covers session lookup, catalogue listings, purchase history, sales history, categories and catalogue facets. It excludes images, third-party services, mobile rendering, real payment requests and distributed network traffic.

- Five short phases send 192 requests each at concurrency 1, 4, 8, 16 and 32. All 960 measured requests succeeded after the fixes.
- A separate 60-second soak at concurrency 16 completed **14,684 requests, zero errors**, approximately 244.51 requests/second. Client-observed p50 was 24.09 ms, p95 291.16 ms, p99 380.40 ms and maximum 743.29 ms. The largest JSON response was 10,267 bytes. These are observed localhost results, not a production throughput rating.
- Eight simultaneous buyers competing for stock of one produced one successful reservation and seven expected 409 conflicts; reserved stock stayed at one. Eight simultaneous submissions of the same checkout request key created one new database order. These use the local sandbox provider and do not contact Stripe.
- The configured PostgreSQL pool completed 64 bounded read-only operations across concurrency 1/2/4/8 with no query errors. This checks the order-history query compatibility and connection reuse on the existing small dataset. Its local-to-Seoul network timings include transaction setup, read-only verification and pool waits; they are not deployed API latency or a million-row PostgreSQL benchmark.
- An initial standalone-server run reported TCP connection resets. Its default listen backlog was five; it is now 128, and subsequent runs had no resets. Vercel owns its own listener, so this change is not a Vercel capacity adjustment.
- The production HTTP probe redirected to Vercel SSO (302). A subsequent login page returning 200 must not be counted as a successful application request. No production HTTP concurrency or peak-capacity claim follows from that probe.
- After the authentication change, the complete server suite ran 301 tests successfully with one opt-in PostgreSQL test skipped. The explicit read-only PostgreSQL rehearsal above was run separately. The build also passed.

Reproduce locally after installing the project dependencies:

```sh
python scripts/qa_capacity.py local --registered-users 1000000 --soak-seconds 60 --output /tmp/sentryloot-capacity-local.json
python scripts/qa_capacity.py postgres-readonly --output /tmp/sentryloot-capacity-postgres.json
```

The first command temporarily uses disk for the synthetic dataset and deletes the database on exit. The second requires the configured DATABASE_URL and network access. Do not increase production concurrency by removing the harness bounds; use a dedicated staging deployment and representative PostgreSQL fixtures for a larger ramp, sustained peak, financial-write contention and infrastructure monitoring.

This rehearsal demonstrates bounded lists and correct local reservation/idempotency behavior with one million registered records. It **does not demonstrate one million simultaneous users**, production autoscaling, provider capacity, or the existing PostgreSQL plan's maximum sustainable throughput. The production order-history pagination indexes were absent during the read-only inventory check; applying them remains a separate migration, not part of this test.
