# VIPayment connection review — 2026-10-30

Status: API profile and games catalogue documentation verified; actual authentication and delivery NOT VERIFIED. No API credentials found in the configured local secrets file. Browser access stopped at Cloudflare verification and was handed to the owner. No funds, orders, customer IDs or delivery credentials were sent.

Public site advertises Rp10,000 minimum funding and API access. Profile uses POST `/api/profile` with server-only `key` and `sign=md5(API_ID+API_KEY)`. Games catalogue uses POST `/api/game-feature` with `type=services`. No verified sandbox was found in the reviewed documentation; do not describe these endpoints as sandbox.

Prepared `vipayment_supplier.py` deliberately only supports profile/catalogue reads; purchase operations are rejected. Set server-only `VIPAYMENT_API_ID` and `VIPAYMENT_API_KEY` after the owner obtains API access. Admin-only POST endpoints `/api/admin/top-up/supplier/vipayment/check` and `/api/admin/top-up/supplier/vipayment/catalog` do not change the existing supplier or enable sales. A successful mock is not actual connection verification. Never log request bodies, signatures or keys.

Reliability: Google Play lists the app under PT Vipayment Digital Solution, but this is not independent legal-registry or publisher-authorization verification. Their FAQ distinguishes Basic/Reseller/H2H pricing and requires administrator confirmation for H2H level. Terms say unused deposits are not refunded and orders generally cannot be cancelled once submitted. Third-party review aggregation includes a complaint alleging problematic MLBB credits; this allegation was not independently verified. Older AppBrain removal information conflicts with a currently accessible Google Play listing, so do not present it as a current delisting.

Before commercial use: confirm non-Indonesian onboarding/payment methods, exact game/region SKUs, publisher authorization, H2H approval, refund handling and a small owner-approved delivery test. The public order API does not document a merchant idempotency key: never automatically retry an ambiguous order-creation timeout. Current implementation has no order-creation operation.

Sources:
- https://vip-reseller.co.id/page/api/profile
- https://vip-reseller.co.id/page/api/game-feature
- https://vip-reseller.co.id/page/general-questions
- https://vip-reseller.co.id/page/terms-of-service
- https://play.google.com/store/apps/details?id=com.vippay.app
- https://chrome-stats.com/d/com.vippay.app

UniPin comparison: official website has a reseller application and reseller@unipin.com support route. Reviewed public pages do not establish a $10 reseller/API minimum or automatic API approval. Small retail voucher denominations do not establish wholesale API terms. Do not connect via browser automation as a substitute for an approved business API.

The official reseller form linked from unipin.com was opened in Chrome: it allows “As an individual” or “As a registered Company” and a “From $0 to $999” monthly turnover band. These are application eligibility fields, not confirmation of minimum funding or API access. No form data was entered or submitted. Form: https://forms.office.com/r/YhhKzTkBKN?origin=unipin.com
