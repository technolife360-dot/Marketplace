# SentryLoot — gaming marketplace foundation

A runnable, Uzbek-first marketplace built with Python, SQLite or Supabase PostgreSQL, and vanilla JavaScript. SQLite remains the default for local development. Set `DATABASE_URL` to use the server-side Supabase PostgreSQL connection; keep this credential private and out of browser code.

## Run locally

Requires Python 3.11+.

```sh
python3 -m pip install -r requirements.txt
mkdir -p ~/Desktop/SentryLoot-Secrets
cp .env.example ~/Desktop/SentryLoot-Secrets/.env
# Generate a unique encryption key and place it in ~/Desktop/SentryLoot-Secrets/.env as DELIVERY_ENCRYPTION_KEY.
python3 -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
python3 seed.py
MARKETPLACE_MODE=development python3 app.py
```

Open http://127.0.0.1:8000. Development verification tokens and sandbox payment completion are shown only in development mode. For a separate database set `DATABASE_PATH=/path/to/file.sqlite3`.

## Supabase PostgreSQL

The application uses Supabase only when `DATABASE_URL` is set in the server environment. Apply `supabase/migrations/20261005000000_marketplace_schema.sql` first, then every later migration in timestamp order, including `20261007010000_facebook_oauth.sql`, `20261008000000_account_reviews_private_evidence.sql`, `20261009000000_topup_catalog.sql`, `20261010000000_topup_coming_soon.sql`, and `20261010010000_topup_supplier_mapping.sql`, in the Supabase SQL Editor or your migration runner. The server checks for the required tables and seeds reference rows on startup. Install dependencies with `python3 -m pip install -r requirements.txt`; Psycopg 3 connects to PostgreSQL and uses dictionary rows for the existing API code. Keep `DATABASE_URL` on the backend in a deployment secret manager; never expose it in browser code or commit it. If unset, the app continues to use the local SQLite database.

Vercel runs a daily account-deletion job. Set a random `CRON_SECRET` environment variable for Production; Vercel sends it as a bearer token. Pending or reviewing deletion requests are automatically erased after 30 days, while anonymized order and ledger records are retained.

Listing photo uploads require a Supabase Storage bucket named `listing-images` with public reads enabled, plus server-only `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_LISTING_IMAGES_BUCKET` settings. The browser accepts JPEG/PNG/WebP originals up to 15 MB, resizes and compresses them to below 4.9 MB, then uploads them. The API enforces a 5 MB request limit, decodes and re-encodes each image as WebP to strip embedded metadata, and writes it to Storage. Never expose the service role key in frontend code or share it in chat. Until the Storage bucket and server secrets are configured, the upload API returns a setup error; photo files are not stored in the database.

Account-purchase evidence uses a separate private Supabase Storage bucket named `account-evidence` (`SUPABASE_ACCOUNT_EVIDENCE_BUCKET`). Apply the migration above and create the bucket with **Public bucket disabled** before enabling uploads. The server verifies that the bucket reports `public=false`, normalizes screenshots to WebP, removes embedded image metadata, limits each file to 5 MB, and returns only short-lived signed links to admins. Buyers upload exactly two screenshots after the seller delivers the account; a moderator must approve before sandbox seller earnings are credited. Screenshots only demonstrate buyer access at that time and cannot prove that the seller is unable to recover the account later. Approved/refunded evidence is deleted after 30 days; account-deletion requests also remove that buyer's evidence. The daily retention job requires the existing server-only `CRON_SECRET`.

Local secrets are kept in `~/Desktop/SentryLoot-Secrets/.env`, outside the repository. The application checks that path before falling back to a project `.env`; both are ignored by Git. Restrict file permissions and do not share or sync this folder publicly.

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
- Top Up pages use stable game/package URLs. Admins can set package prices and visibility, add packages, and adjust auditable stock. Prices start at zero and stock starts empty by design; configure both in Admin before publishing packages.

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

Google and Facebook sign-in use server-side authorization-code flows. Configure a Google OAuth Web client and set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`; for Facebook Login set `FACEBOOK_APP_ID` / `FACEBOOK_APP_SECRET`. In production register each exact callback at `<PUBLIC_BASE_URL>/api/oauth/{google,facebook}/callback` in its provider console. In development, the callback host follows the browser host, so use one host consistently (`localhost` or `127.0.0.1`) and register its exact callback URI. Facebook requests only `public_profile` and `email`; the server exchanges the code and obtains the profile over HTTPS. Provider buttons appear only when credentials are configured. Existing password accounts are never silently linked by matching email; a conflicting provider identity is rejected until an explicit account-linking flow is added. Social registration records the same terms acceptance as password registration, and a provider identity never grants admin access.


File upload and private object storage are not enabled; listings use optional external image URLs only. Never put protected credentials in public listing media.

## Data/security notes

Passwords use PBKDF2-HMAC-SHA256; session tokens are random, stored hashed, expire, and use HttpOnly/SameSite cookies. Mutations require a session CSRF token. Buyer accounts use ordinary email verification. Seller listing, delivery, and payout requests additionally require Didit identity verification and administrator approval; the admin API rejects approval until Didit reports an approved ID, liveness, and face-match result. Admin actions are audited. Delivery payloads are encrypted with AES-256-GCM and bound to their order item; keep `DELIVERY_ENCRYPTION_KEY` in a secret manager and back it up separately from the database. Never commit or send that key in chat. Before upgrading a database that may contain older plaintext delivery records, back it up and run `python3 scripts/encrypt_delivery_payloads.py`; production startup refuses to serve while legacy plaintext deliveries remain. Losing the key makes encrypted deliveries unrecoverable. `/healthz` provides a basic process/database probe. `npm run backup` creates a private, integrity-checked SQLite snapshot for local evaluation only. The built-in server and SQLite database are for local development, not production serving. A live deployment needs a production server, PostgreSQL, HTTPS, edge rate limiting, managed backups and monitoring, private malware-scanned storage, configured SMTP and Didit accounts, security review, and legal/tax review. See [security operations](docs/SECURITY_OPERATIONS.md) for the restore, alert, secret, and incident checklist.

## Legal and operational readiness

Policy copy is a launch checklist, not legal advice. Obtain jurisdiction-specific review for Uzbekistan and each supported market, gaming publisher terms (especially account transfers/boosting), consumer refunds, privacy/data retention, tax, KYC/AML, payment aggregation, custody of funds, and seller payout rules. The admin panel has a seller review queue and public verification status, but administrators must not approve a seller until a separate identity check has actually been completed.

## Implemented scope and remaining launch work

Implemented locally: registration/login, Google and Apple ID OAuth sign-in boundaries, SMTP email verification, password-reset links and order-status messages (development-token fallback only outside production), signed expiring sessions with CSRF, Didit hosted-session and signed-webhook integration points, email/KYC/admin seller gating, seller review queue, seller wallet balance breakdown and guarded payout requests, private “my reviews” history for completed purchases, searchable help center, multilingual blog with admin-only draft/edit/publish workflows, homepage messaging access, editable/hideable seller listings, FTS-backed paginated listing search, favorites/cart, inventory reservations, sandbox escrow ledger, delivery visibility controls, dispute evidence and sandbox-only moderator resolution, notifications, reports, account deletion requests, admin moderation/user/report/order tools, Uzbek-first responsive pages, Asian country and currency profile preferences, and approximate wallet balance conversion. Listing prices, the internal ledger, and sandbox checkout remain in UZS; the selected profile currency affects display only and is not a payable or withdrawable balance.

Not launch-complete: production OAuth client/service IDs and HTTPS callback registration, verified SMTP sender configuration, Didit production credentials/workflow/webhook registration, private evidence uploads with malware scanning, a real payment/refund/payout adapter, backup/restore and monitoring/alerts, complete reviewed RU/EN translations, and jurisdiction-specific legal/tax/publisher-rule review. The repository now includes deterministic, moderator-only fraud review flags, game-specific account fields for the five seeded games, platform/rank search filters, a three-listing comparison view, and a non-secret health readiness report. These do not replace human review or external provider configuration. Listing photos are public product media after upload; they must not contain secrets, account credentials, or personal documents. Read [the six launch-readiness areas](docs/SIX_READINESS_WORK.md) before changing production gates. Do not open public sales until the required provider and operational items are completed.

The configured Asia market list supplies account country defaults and display-currency choices only. It does not mean buyers or sellers in every listed market can transact, pass provider onboarding, or receive a payout. Real checkout remains unavailable until a provider confirms coverage and is integrated.

Top Up catalog and admin inventory management are implemented, but live Top Up checkout is intentionally closed until the payment method is selected and integrated. Supplier fallback is also not active until a specific supplier API and credentials are supplied; the admin page labels this state instead of claiming that automatic fulfillment is available.

### SEAGM supplier setup

The server includes a SEAGM Open API connection check and a read-only direct-top-up category browser in Admin → Top Up. Apply through SEAGM's business partnership form, then add `SEAGM_UID` and `SEAGM_SECRET_KEY` to the private local environment file or deployment secret manager. Leave `SEAGM_API_ENV=sandbox` while checking credentials; only switch to `production` after SEAGM approves the account and the sandbox flow has been reviewed. Never put the secret in browser code, chat, or the repository. The admin actions show account connection/balance and supplier category IDs without placing a paid order.

This is supplier-side preparation, not a live storefront launch. Each enabled package still needs an approved SEAGM product/region mapping and a verified retail price. Top Up order creation and supplier fulfillment remain disabled until a real customer payment adapter and its signed success callback exist; the supplier must only be charged after payment is confirmed. SEAGM API keys and sandbox access cannot be created by this repository, and the actual account/API response must be checked after merchant onboarding.

## Deployment

Run locally with `npm install`, `npm run dev`, then open `http://127.0.0.1:8000`. `GET /healthz` can be used for a basic process check. `npm run backup` makes a timestamped SQLite snapshot and verifies it; schedule it only for local evaluation. Production database backups must use the managed PostgreSQL provider’s backup/PITR service. Before launch, complete the items in “Not launch-complete,” obtain provider approval and credentials, configure a real email sender and verified domain, and perform a deployment/security review. These marketplace, provider, and legal details are not present in the project, so the current build remains in its guarded preview mode.
