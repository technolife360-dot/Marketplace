# Cookie preferences

The browser starts with both optional categories disabled. A successful same-origin
`POST /api/cookie-consent` records explicit booleans for `analytics` and `support`.
GET returns a valid, unexpired receipt or `consent: null`. Old banner dismissal
values and locally edited caches never enable integrations.

- Necessary: authentication, security and a random `sl_cookie_preferences` identifier.
- Optional analytics: Vercel Web Analytics and Speed Insights loaders.
- Optional support: the Crisp SDK. The first-party launcher opens preferences when
  support is disabled; email support remains available.

The server uses existing `platform_config` rows keyed by
`cookie-consent:<sha256(browser identifier)>`. Consent changes are appended to
`audit_logs` as `cookie_consent_changed`. Receipts contain the policy version,
category choices, receipt ID, server timestamp and expiry. This requires no new
schema migration. No IP address or user agent is added to consent receipts.
Authenticated changes use the existing CSRF protection. Anonymous changes require
a custom JSON request header and same-origin validation. Rate limiting applies.

The preference cookie is HttpOnly, SameSite=Lax, Secure in production and expires
after 180 days. Browser storage contains a receipt cache used for cross-tab change
notifications, never as authority to turn on services. Missing/expired receipts
or server failures default to optional services off. Server writes must succeed
before the UI says a choice was saved.

Cookie settings are reachable from the desktop footer, the mobile settings button,
and the privacy policy. Revoking a previously enabled category saves the new
choice, clears accessible first-party integration storage and reloads the page so
previously running SDKs are gone. Third-party records already held by providers
are not erased by this action. Account/cart cookies and storage are preserved.

Verification: Python HTTP tests cover persistence, audit records, expiry, forged
identifiers, signed-in CSRF and cross-origin rejection. JavaScript tests cover
fail-closed behavior and analytics gating. Browser QA additionally checks category
selection, persistence across reload, SDK presence before/after opt-in and revocation.
