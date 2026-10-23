# Seller verification admin workspace

Open Admin → Sellers. The workspace uses real seller profiles and audited Didit decisions; there are no demo records in the application.

- Signed Didit status webhooks update the identity state and an allowlisted summary in the existing private `platform_config` table (`didit_review:<user_id>`). The state, summary, notification, and audit event commit together. Production ignores non-live events. Duplicate/stale events cannot replace newer results.
- Only identity summaries are persisted: per-check statuses, name, country, document type and last four characters. Passport/selfie images, full document numbers, date of birth and raw provider responses are not stored. Account deletion removes the summary.
- Admin → Load secure Didit report explicitly calls `GET /v3/session/{session_id}/decision/`. Its response is checked against the profile's session and allowlisted before returning. Provider images are exposed only on trusted Didit/AWS hosts and only in the authenticated response. The action is audited; the response uses `Cache-Control: no-store`.
- Approval, rejection and requests for information require a reason. Identity approval does not automatically enable selling. Approval requires a verified email, an active account and a verified Didit identity. A reviewer cannot approve their own account, and a changed session requires a fresh review. Decisions commit atomically with their audit event and seller notification.
- Search, country/status/date filters and server-side pagination work on all seller states, including approved and rejected sellers. Summary cards show all-time totals; the date filter applies to the request queue. The chart shows actual daily audit event counts for seven days, not fabricated growth. CSV export respects filters and excludes full identifiers; up to 5,000 filtered records can be exported at once.
- Existing sessions with no stored summary show unavailable checks until an admin explicitly loads their secure report. Loading a report does not itself enable selling or replace the signed webhook verdict.

No new database migration is required. Existing Didit API/workflow/webhook configuration is reused. This change does not alter the Didit workflow or provider settings.

Validation: `python -m unittest tests.test_seller_verification tests.test_identity_service`; `npm run build`; `node --test tests/frontend.test.cjs`. HTTP tests and localhost Chrome checks should use an isolated database, never production seller records.
