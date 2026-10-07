# Six launch-readiness areas

This note separates work that can be completed in this repository from integrations that require provider accounts, credentials, or operational decisions. The production sale gate remains closed.

## 1. Game-account ownership proof

- The seller must attest to ownership/authority and publisher-rule review when creating an account listing. The accepted terms version and timestamp are retained.
- Didit verifies a seller's identity; it does not prove ownership of a game account.
- Private document or screenshot collection is intentionally not enabled. Do not request passwords, email access, OTPs, recovery codes, or identity documents in listing text or public image links.
- Remaining integration: a private upload/storage API with least-privilege access, malware scanning, retention/deletion controls, and a moderator review record. Until then, seller attestation is not proof and must not be represented as verification.

## 2. Account-recovery disputes

- Buyers can open an order dispute and attach an optional HTTPS evidence reference. Evidence files are not uploaded to the marketplace.
- Moderators can request more information and record a decision. Production money movement remains blocked; the resolution actions only operate on successful sandbox orders.
- The dispute queue shows how long a case has been waiting. Moderator actions now consistently identify the order, avoiding a mismatch between a report ID and order ID.
- Remaining integration: private file evidence, a staffed escalation policy with an approved response-time commitment, and a real provider refund/escrow adapter.

## 3. Didit production verification

- The server-side session and signed-webhook integration is implemented and fails closed when configuration is missing. Seller activation requires approved ID, liveness, face-match, and separate moderator approval.
- Remaining setup: Didit production credentials, a published/approved workflow, exact webhook registration, and a verified production callback. None of those secrets or account-side settings are stored in this repository.
- Didit is seller identity verification only, not game-account ownership proof.

## 4. Fraud and fake-seller controls

- Account listing submissions receive private deterministic review flags for likely off-platform contact/payment, credential or one-time-code disclosure, exact duplicate titles, and unusually high account-listing volume.
- Flags do not ban users or decide fraud automatically. They stay hidden from public listing data; moderators must record a reason before approving a flagged listing.
- Existing controls still apply: verified email, Didit identity status, administrator seller approval, listing moderation, rate limits, reporting, audit records, and closed production sales.
- Remaining integration: provider-backed payout-owner checks, shared-device/IP/link analysis, private image scanning, and ongoing human fraud operations. Heuristic flags can have false positives and are not a guarantee against fraud.

## 5. Public launch and production operations

- `/api/health` reports non-secret deployment readiness facts such as database type, payment adapter state, Didit configuration presence, and the sales guard. Production sales remain closed unless a real supported payment adapter and explicit gates exist.
- Vercel SSO protection, backup/PITR configuration, alert routing, incident ownership, and restore drills are deployment/account operations, not repository code. Do not treat a successful health response as an uptime-monitoring or backup test.
- Remaining setup: public access decision, production monitoring/alerts, managed backup and restore evidence, security review, legal operator/market review, and provider configuration.

## 6. Product experience

- Search supports game, category, region, platform, rank/level, price, and sort filters.
- Listing creation exposes game-specific fields for Valorant, PUBG Mobile, Dota 2, Counter-Strike 2, and Mobile Legends. Buyers can compare up to three listings; the selection stays in the current browser.
- Remaining work: review every visible Russian and English string, translate and review all supported routes, add/maintain publisher-specific fields as supported games change, and browser-test the complete experience.

## Release boundary

Repository work does not authorize opening public sales. Do not enable live account listings or real checkout until publisher terms, supported jurisdictions, business operator, payment/KYC providers, private evidence storage, operational controls, and legal review are confirmed for the exact launch markets.
