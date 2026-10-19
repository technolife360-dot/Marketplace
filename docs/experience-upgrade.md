# Marketplace experience upgrade — 20 October 2026

Payment and Top Up adapters stay disconnected. Referral/coupon/loyalty growth features remain deferred until the real catalogue and ordering launch, as requested in the source list.

Implementation and verification checklist:
- [x] Saved searches integration, contextual catalogue facets with counts, multilingual/typo search, explained quality ranking.
- [x] Equivalent offers, units/minimum quantity, compatibility checks, per-game validation, contextual FAQ, comparable attributes.
- [x] Bulk changes, CSV/XLSX import preview/confirmation, low-stock alerts, encrypted code inventory and allocation.
- [x] Seller quality by period/type, listing funnel, structured moderation corrections.
- [x] Chat search/history, block/report, mute/archive, saved replies, retryable drafts.
- [x] Notification preferences, opt-in email/browser alerts, target prices, account-synced recent/comparison lists.
- [x] Mobile purchase bar, field errors, loading/retry states, common design and keyboard/accessibility checks.
- [x] Game/category pages and seller canonical metadata; searchable help with support handoff.
- [ ] Measured performance and browser/failure tests; production backup/restore/monitor verification.
- [ ] Additive schema migration, RLS audit, tests, visual verification, commit/push.

Performance tooling: the web-perf skill was read. No chrome-devtools navigate_page/performance_start_trace tools are configured. Do not claim a DevTools trace or Safari/iPhone/Android device coverage without actually running them. Keep this tooling limitation separate from implementation work.

## Verification evidence

- `npm run build`: passed. Full suite: 5 frontend tests and 139 backend tests passed (latest log `/private/tmp/experience-final-tests.log`).
- All 17 migrations applied to disposable PostgreSQL 18. Sixteen new workflow tests passed against PostgreSQL as well as SQLite. Schema security audit: 71 tables, zero errors and zero warnings. The explicitly approved additive migration has also been applied to production; its audit likewise returned 71 tables, zero errors and zero warnings.
- Browser checks: catalogue counted facets and applying them, listing quantity/total on desktop and 390px mobile, notification preferences save, CSV chooser → preview → one draft, chat send/search, and comparison persistence in a separate tab. Safari desktop additionally passed catalogue/filter disclosure, listing navigation and quantity calculation. No claim of physical iPhone/Android coverage.
- Local lab under aggregate 1.6 Mbps / 200 ms response latency, no CPU throttling: optimized run FCP 1476 ms, LCP 3744 ms, CLS 0.003, INP 48 ms, TTFB 238 ms. LCP still needs improvement under this connection; this is not a production field measurement or Lighthouse score. Earlier uncompressed run reached LCP 14744 ms; compression plus WebP banners and sequential inactive-banner loading substantially reduced it. WebP banners total 454140 bytes versus 1521059 bytes for JPEG originals.
- Operational evidence (read-only): GitHub backup run `39208019698` succeeded through dump, encrypted upload, authenticated download, restore into isolated PostgreSQL 18, cleanup and retention. Production perimeter run `39295208341` succeeded. These are pre-change operational proofs, not proof that the new email workflow has run.
- Monitoring recipient: `sentryloot@gamestorehub.com`. Test email accepted by Resend using existing verified `mail.gamestorehub.com`. The local `resend.dev` sender was rejected with HTTP 403; do not propagate that sandbox sender to the workflows. Acceptance by provider does not prove mailbox delivery.
- Prepared hourly perimeter/backup failure emails and five-minute opt-in discovery-email dispatch. A new sending-only key restricted to the verified mail.gamestorehub.com domain has been provisioned as the encrypted MONITOR_RESEND_API_KEY secret in the existing repository.

## Approved rollout

The user explicitly approved the new production migration (12 additional private tables and four listing columns), a domain-scoped Resend sending credential in `technolife360-dot/Marketplace` GitHub Actions, and push without waiting for Vercel deployment. The migration and production security audit succeeded. The credential was created with `sending_access` restricted to `mail.gamestorehub.com` and stored as `MONITOR_RESEND_API_KEY`; no credential value was printed or committed.

After push, use the existing perimeter workflow’s `simulate_failure=true` dispatch to exercise the failure-email step. The workflow is expected to finish failed because of the deliberate drill; its email step must succeed and report provider acceptance. Physical mobile-device coverage and unavailable Chrome DevTools tracing remain explicitly unverified. Keep payments and Top Up disconnected.
