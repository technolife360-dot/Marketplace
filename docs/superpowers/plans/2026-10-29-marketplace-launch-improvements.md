# Marketplace launch improvements

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the code, content and verification work from the marketplace audit while clearly separating sandbox operation from a real commercial launch.

**Architecture:** Extend existing payment, catalogue, regional translation and launch-readiness modules. Preserve preview gates, original ledger currencies, provider idempotency and private data boundaries. Use public R2 for public artwork.

**Tech Stack:** Python HTTP application, SQLite/PostgreSQL, vanilla JavaScript, Stripe test SDK, Cloudflare R2, Chrome.

**Spec:** The owner approved sandbox testing, has no Top Up supplier yet, and needs a plain-language explanation of authentic catalogue data. The approved audit covers payment/refund/payout correctness, regional checkout clarity, catalogue quality, Top Up readiness, shopping translations, consistent branding, trust and browser/performance verification.

## Global Constraints

- No live payments, supplier orders, fabricated offers/reviews/support commitments, or production activation.
- Preserve existing working features and `static/AGENTS.md` rules.
- Never include secrets or personal/payment records in reports or readiness responses.
- Existing authentic products remain subject to publisher/product-scope approval; UI availability is not permission to sell.

## Review Focus

Currency-unit boundaries, webhook/refund/transfer consistency; readiness checks must not imply a successful external operation from credential presence. Check translated shopping flows and mobile layout visually.

## Tasks

- [x] Verify Stripe sandbox connection and official currency-unit rules; correct provider boundary with independently specified regression tests if necessary (`stripe_test_payments.py`, `stripe_test_topups.py`, payment tests).
- [x] Extend the existing admin readiness endpoint/view with actionable payment, catalogue, business/support and Top Up states; test authorization and sanitized output.
- [x] Expand core shopping translations in `static/regional-languages.json`; integrate cache version and public information-page translation paths; test key coverage and regional behavior.
- [x] Replace wrong-brand hero references and publish/fix the missing PUBG UID guide through the public asset manifest.
- [x] Add clear catalogue preparation guidance using existing draft import/admin tools; document owner-supplied commercial facts and no-supplier Top Up limits.
- [x] Run isolated automated checks, inspect local Chrome desktop/mobile shopping and readiness paths, repair discovered regressions, review the final diff and push authorized changes.

## Execution ledger

- Audit: existing test checkout/refund/settlement, catalogue draft import/moderation, launch profile publication, Analytics/Speed Insights and optional Web Vitals diagnostics already exist. Extend them rather than adding duplicate systems.
- Ruling: live launch and a real Top Up catalogue cannot be completed without merchant approval, a supplier and authentic stock/pricing. Deliver tested preparation and exact remaining steps; do not activate flags.
- Asset verification: missing UID PNG published to the public listing bucket; direct R2 HTTP 200 and hash match. Use direct public URL to avoid protected deployment routes.

- Verification: authenticated Stripe sandbox Connect list read succeeded (empty). No site test secrets available locally, so external checkout/webhook E2E remains unverified. Mocked provider boundary suite covers independently specified UZS/MYR units and rejects old undercharged sessions.
- Web Interface Guidelines review applied to new readiness blocks: native details/summary keyboard activation, semantic links/headings, visible focus, no extra backgrounds, two columns desktop/one mobile, no 390px overflow.

- Final verification: 130 Node tests passed; 338 Python tests ran with 3 skipped; provider suite re-run 27/27 after dynamic payment-method change; build passed. Chrome desktop/mobile: core Spanish copy, native guide keyboard activation, missing UID media naturalWidth 1230, no 390px overflow, single coupon input border, no console errors. Saved evidence under regions/launch-improvements.
- Final review: fresh reviewer found no actionable P1/P2 in full diff or later FX-disclosure/payment-method deltas. Buyer summaries disclose estimated conversions without restoring the removed duplicate original-currency monetary row.
- External sandbox verification: Stripe API accepted unpaid test Checkout Sessions with UZS 9600000 and MYR 30000 minor units. No payment or delivery occurred. Production health reports stripe_test/internal_testing and live sales false; this is not a site webhook E2E verification. Connector exposes no expire operation; temporary audit sessions remain unpaid until expiry.
- Local verification retry: final repeat stalled in an old tests/__pycache__ read (confirmed by process sample). Stopped only owned test/status processes and restarted Python with PYTHONPYCACHEPREFIX in /tmp. No application data changed.
- The retry also stalled reading unchanged regional_preferences.py; normal commit refresh stalled reading unchanged scripts/send_monitor_alert.py. Stopped owned retry/commit processes. Earlier full Python run (338, 3 skips), final 27 provider tests, final 130 Node tests and successful build remain the test evidence. Used the validated staged tree for the commit; repository has only sample hooks. Disk I/O issue remains an environment limitation.
