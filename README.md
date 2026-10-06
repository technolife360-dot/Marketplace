# SentryLoot — gaming marketplace foundation

A runnable, Uzbek-first marketplace built with Python, SQLite or Supabase PostgreSQL, and vanilla JavaScript. SQLite remains the default for local development. Set `DATABASE_URL` to use the server-side Supabase PostgreSQL connection; keep this credential private and out of browser code.

## Run locally

Requires Python 3.11+.

```sh
python3 -m pip install -r requirements.txt
cp .env.example .env
# Generate a unique encryption key and place it in .env as DELIVERY_ENCRYPTION_KEY.
python3 -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
python3 seed.py
MARKETPLACE_MODE=development python3 app.py
```

Open http://127.0.0.1:8000. Development verification tokens and sandbox payment completion are shown only in development mode. For a separate database set `DATABASE_PATH=/path/to/file.sqlite3`.

## Supabase PostgreSQL

The application uses Supabase only when `DATABASE_URL` is set in the server environment. Apply `supabase/migrations/20261005000000_marketplace_schema.sql` once in the Supabase SQL Editor (or your migration runner) before starting the server. The server checks for the required tables and seeds reference rows on startup. Install dependencies with `python3 -m pip install -r requirements.txt`; Psycopg 3 connects to PostgreSQL and uses dictionary rows for the existing API code. Keep `DATABASE_URL` on the backend in `.env` or a deployment secret manager; never expose it in browser code or commit it. If unset, the app continues to use the local SQLite database.

The app has no Node package dependencies; `package.json` provides optional npm aliases for environments that expect npm commands. `npm install` needs no third-party packages, `npm run build` checks the frontend and Python syntax, and `npm start` runs the Python server.

## Development accounts and seed data

```sh
python3 seed.py
```

This adds a small set of games/categories, explicitly labelled development demo listings, a demo wanted post and conversation, and two verified local test accounts. It creates no sample orders, fake sales, fake reviews, or trust statistics. Test logins are `buyer@example.test` / `BuyerDev!2026` and `seller@example.test` / `SellerDev!2026`; these must never be reused outside local development. To create the requested admin, set `SEED_ADMIN_EMAIL=admin@gamestore.com` and a unique `SEED_ADMIN_PASSWORD` of at least 14 characters in the environment before running `python3 seed.py`. The header admin icon appears only for that email after the account has its actual admin role; the email address alone never grants access. The admin account receives a password hash and is created only by this local command.

## Core workflows

- Register, verify email, then create a seller profile.
- Create a draft listing and submit it for moderation.
- Approve from the admin dashboard (bootstrap an admin through the environment as above).
- Add a published listing to cart; local development checkout creates a clearly labeled sandbox payment. Confirm it via the order page's sandbox action.
- Seller submits delivery; buyer can view delivery only after confirmed payment and can complete the order.
- Buyers/sellers can use messages, favorites, wanted requests, reports, and reviews after eligible order completion.

## Commands

```sh
python3 app.py                 # development server
python3 seed.py                # apply migration and seed reference data
python3 -m unittest discover -s tests -v
```

With SQLite selected, the server applies `migrations/001_initial.sql` on startup. With Supabase selected, apply the PostgreSQL migration described above before starting the server. Development mode may be set with `MARKETPLACE_MODE=development`. Use `MARKETPLACE_MODE=production` only behind HTTPS and after setting `SESSION_SECRET` to a random secret. Production checkout is intentionally blocked until a real verified payment adapter is configured; browser redirects alone never mark payments successful.

## Configuration and external services

See `.env.example`. The payment-provider boundary and checkout fail closed outside the development sandbox. Sandbox proceeds are held in an internal escrow ledger until delivery completion or moderator resolution. Sandbox refunds are records for testing only and never move money. Seller payouts can be requested, approved, then reconciled by an administrator with an external transfer reference; the app does not send those transfers. The live payment-provider adapter is not configured. Merchant onboarding, credentials, a provider adapter, signed callbacks, replay protection, live refund and settlement flows are required before any real payment.

Transactional email supports Resend's HTTPS API or SMTP. For Resend set `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `EMAIL_FROM`, and `PUBLIC_BASE_URL`; keep the key in the server `.env` or secret manager, never in browser code. Without `EMAIL_FROM`, development uses SentryLoot-branded `onboarding@resend.dev` for testing. Production must use an address on a Resend-verified domain and an HTTPS public URL. In development without a configured provider, verification and reset tokens are returned only as local development affordances. Verified users also receive order-paid, delivery, completion, and dispute decision updates; those emails contain order references/status only and never delivery credentials. Email layouts are responsive, branded HTML with plain-text alternatives.

Seller identity verification uses Didit’s hosted verification session. Configure `DIDIT_API_KEY`, `DIDIT_WORKFLOW_ID`, and `DIDIT_WEBHOOK_SECRET` in the server environment. The published workflow must include ID verification, liveness, and face match; avoid paid modules to stay within Didit’s free bundle. Register `https://<your-domain>/api/webhooks/didit` for the `status.updated` event using webhook version `v3`. The server verifies the V2 signature and timestamp, accepts approval only when all three required checks report `Approved`, and keeps selling disabled until the administrator separately approves the seller. Passport images and face biometrics stay with Didit; SentryLoot stores only the verification status, session ID, and consent metadata. Credentials and a public HTTPS deployment are not included in this repository.

Google and Apple ID (iCloud) sign-in use server-side OpenID Connect authorization-code flows. Configure a Google OAuth Web client and set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`; in production register `<PUBLIC_BASE_URL>/api/oauth/google/callback`. In development, the callback host follows the browser host, so use one host consistently (`localhost` or `127.0.0.1`) and register its exact callback URI. For Apple, enable Sign in with Apple for a Services ID, register the domain and exact return URL `<PUBLIC_BASE_URL>/api/oauth/apple/callback`, and set `APPLE_SERVICE_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, and the `.p8` contents in `APPLE_PRIVATE_KEY` (use literal `\n` between lines). Apple web sign-in requires a public HTTPS domain and a current Apple Developer account/key. The server checks state, nonce, expiry, issuer, audience, provider signature, and verified email. Provider buttons appear only when their credentials are configured. Existing password accounts are never silently linked by matching email; a conflicting provider identity is rejected until an explicit account-linking flow is added. Social registration records the same terms acceptance as password registration, and a provider identity never grants admin access.

File upload and private object storage are not enabled; listings use optional external image URLs only. Never put protected credentials in public listing media.

## Data/security notes

Passwords use PBKDF2-HMAC-SHA256; session tokens are random, stored hashed, expire, and use HttpOnly/SameSite cookies. Mutations require a session CSRF token. Buyer accounts use ordinary email verification. Seller listing, delivery, and payout requests additionally require Didit identity verification and administrator approval; the admin API rejects approval until Didit reports an approved ID, liveness, and face-match result. Admin actions are audited. Delivery payloads are encrypted with AES-256-GCM and bound to their order item; keep `DELIVERY_ENCRYPTION_KEY` in a secret manager and back it up separately from the database. Never commit or send that key in chat. Before upgrading a database that may contain older plaintext delivery records, back it up and run `python3 scripts/encrypt_delivery_payloads.py`; production startup refuses to serve while legacy plaintext deliveries remain. Losing the key makes encrypted deliveries unrecoverable. `/healthz` provides a basic process/database probe. `npm run backup` creates a private, integrity-checked SQLite snapshot for local evaluation only. The built-in server and SQLite database are for local development, not production serving. A live deployment needs a production server, PostgreSQL, HTTPS, edge rate limiting, managed backups and monitoring, private malware-scanned storage, configured SMTP and Didit accounts, security review, and legal/tax review.

## Legal and operational readiness

Policy copy is a launch checklist, not legal advice. Obtain jurisdiction-specific review for Uzbekistan and each supported market, gaming publisher terms (especially account transfers/boosting), consumer refunds, privacy/data retention, tax, KYC/AML, payment aggregation, custody of funds, and seller payout rules. The admin panel has a seller review queue and public verification status, but administrators must not approve a seller until a separate identity check has actually been completed.

## Implemented scope and remaining launch work

Implemented locally: registration/login, Google and Apple ID OAuth sign-in boundaries, SMTP email verification, password-reset links and order-status messages (development-token fallback only outside production), signed expiring sessions with CSRF, Didit hosted-session and signed-webhook integration points, email/KYC/admin seller gating, seller review queue, seller wallet balance breakdown and guarded payout requests, private “my reviews” history for completed purchases, searchable help center, multilingual blog with admin-only draft/edit/publish workflows, homepage messaging access, editable/hideable seller listings, FTS-backed paginated listing search, favorites/cart, inventory reservations, sandbox escrow ledger, delivery visibility controls, dispute evidence and sandbox-only moderator resolution, notifications, reports, account deletion requests, admin moderation/user/report/order tools, and Uzbek-first responsive pages with language/currency preferences (listing prices and sandbox checkout remain UZS; there is no exchange conversion).

Not launch-complete: a production HTTP server, production OAuth client/service IDs and HTTPS callback-domain registration, SMTP credentials and sender-domain verification, Didit API credentials, a published KYC workflow containing the free ID/liveness/face-match steps, and a signed V3 webhook, compliant identity consent/retention and privacy notices, real payment/webhook/refund adapters, automatic payout transfers and split settlement, encryption-key management and migration of any legacy delivery rows, private uploads and malware scanning, tax/coupon support, live dispute/refund settlement, configurable category attributes, complete RU/EN translations, public SEO/sitemap, broader browser/E2E security review, hosted deployment and production monitoring, and jurisdiction-specific legal/tax review. Do not set this build up for public sales until these items are completed.

## Deployment

Run locally with `npm install`, `npm run dev`, then open `http://127.0.0.1:8000`. `GET /healthz` can be used for a basic process check. `npm run backup` makes a timestamped SQLite snapshot and verifies it; schedule it only for local evaluation. Production database backups must use the managed PostgreSQL provider’s backup/PITR service. Before launch, complete the items in “Not launch-complete,” obtain provider approval and credentials, configure a real email sender and verified domain, and perform a deployment/security review. These marketplace, provider, and legal details are not present in the project, so the current build remains in its guarded preview mode.
