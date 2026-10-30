# SEAGM sandbox connection

Status on 2026-10-30: website account login verified in Chrome; sandbox API access is **not connected**. No SEAGM UID/key pair exists in the configured local secrets file or the Vercel project. The documented sandbox `/ping` and `/time` endpoints returned HTTP 403; `/ping` showed a Cloudflare block page from this machine. This does not prove the account has API access or that Vercel egress is allowed.

Request merchant/reseller **sandbox** API access through SEAGM Business Partnership. Ask for sandbox UID, secret key, accessible game/region catalogue, test delivery/refund workflow and any outbound-IP allowlist requirements. Do not promise a funding amount or legal-company status that has not been approved. A website account is not an API credential.

After SEAGM issues credentials, store `SEAGM_UID` and `SEAGM_SECRET_KEY` as server-only secrets and set `SEAGM_API_ENV=sandbox`. Do not put them in client JavaScript, Git, chat, screenshots or public environment variables. Use Preview/local for sandbox verification; do not replace a production supplier configuration with test credentials.

Verification sequence: administrator `POST /api/admin/top-up/supplier/check` must return a matching authenticated account with `connected=true`; then `GET /api/admin/top-up/supplier/catalog` and `GET /api/admin/top-up/supplier/categories/{id}/types` must return accessible products. Validate each game, region, package ID, required player fields, currency and price before mapping products. Missing credentials, malformed success replies or a mismatched account ID must not be reported as a successful connection.

The current client supports read-only account/catalogue checks. Supplier order creation and delivery adapters are not implemented yet. Purchases remain closed until payment and supplier fulfillment are integrated and verified separately. A mocked test is not evidence of an actual authenticated supplier connection.

Official sources: https://doc.openapi.seagm.io/ and https://www.seagm.com/en-sa/page/index?view=partnership
