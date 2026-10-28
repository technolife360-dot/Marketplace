# Global browsing preferences

Country coverage: 249 ISO 3166-1 territories. `static/asia-markets.json` and the
`asia_markets` exports keep their legacy names for compatibility; coverage is global.
Currency assignments come from Unicode CLDR current tender data, retrieved
2026-10-29. Territories without their own tender use USD as a display fallback.
Source: https://github.com/unicode-org/cldr-json/blob/main/cldr-json/cldr-core/supplemental/currencyData.json

## API and precedence

- `GET /api/me` includes `region`, alongside the existing session response. Page
  startup needs no extra geolocation request.
- `GET /api/region` returns the same resolved preferences independently.
- Authenticated profile > explicit guest choice on this browser > Vercel edge
  country > browser language's explicit country tag > US/USD fallback.
- Edge country is trusted only with `VERCEL=1`. No arbitrary forwarded IP lookup,
  third-party visitor IP service, browser location permission or IP storage is added.
- Country is a browsing preference, not evidence of residence, game activation
  compatibility, billing/tax jurisdiction, identity or Stripe eligibility.
- Existing accounts keep their stored country/currency/language while travelling.
  Changing country defaults currency unless an explicit currency is also supplied.
- Registration accepts global countries. OAuth state signs the selected language
  as well as country; pre-existing signed state remains compatible.
- Language selection remains English, Uzbek and Russian. Unsupported browser
  languages fall back to English; e.g. Germany uses en-DE and EUR, Saudi Arabia
  uses en-SA and SAR. German/Arabic interface translations are not claimed.

Users can change preferences from the globe menu on desktop, or **Region &
currency** in mobile navigation. Guests save locally; signed-in users save through
`POST /api/profile` with the existing session, validation and CSRF protection.

## Rates and accounting

`GET /api/exchange-rates` returns a public USD-base snapshot, with per-currency
source dates and `estimate_only: true`. Its handler bypasses database/session
resolution and includes no user data. Existing deployment safety checks still
run at cold start. Frankfurter is called once per warm server process per
six hours, with single-flight locking, a three-second timeout and five-minute
failure backoff. Fresh snapshots can be cached at the CDN for one hour; each
browser also caches the snapshot in session storage until expiration.

A failed refresh may return the last good snapshot for up to 48 hours, marked
`stale`; stale or unavailable snapshots are not publicly cached. Missing rates
show original prices. Catalogue card estimates and seller wallet conversions
share this API; there are no direct browser-to-FX-provider requests.

All original prices remain visible. Conversions use the existing ledger units:
MYR is cents; UZS is whole som. Orders, commission, accounting, refunds, filters
and Stripe test payment amounts are not converted or reinterpreted. Checkout
still charges the order's original currency. No live Stripe settings are changed.

## Future UK Stripe onboarding

A UK business account and verification must be completed with Stripe before
activating live payments. Profile country alone cannot enable a payment method.
Use the existing hosted Checkout Sessions/webhook flow; eligible payment methods
are selected dynamically by Stripe. Adaptive Pricing can be evaluated after the
business/account and marketplace/Connect eligibility, supported currencies and
settlement requirements are confirmed. Do not turn a display estimate into the
order's authoritative payment amount.

References:
- https://vercel.com/docs/headers/request-headers
- https://docs.stripe.com/currencies
- https://docs.stripe.com/payments/checkout/localize-prices

## Verification

`npm test` includes regional detection, spoofed direct-host headers, language
quality weights/fallback, profile precedence, all seven requested markets,
registration/profile writes, invalid-input atomicity, FX cache/outage/stale
expiry, legacy unit conversions and guest persistence tests. Browser QA uses
an isolated SQLite database, never production payment data.
