# SentryLoot security operations checklist

This checklist covers the controls that cannot be proven by repository tests alone. Keep sales closed until the relevant external checks are recorded.

## Secrets

- Keep local `.env` and OAuth client JSON files in `~/Desktop/SentryLoot-Secrets/`; never put real keys in the repository, screenshots, chat, or a public sync folder.
- The local secrets folder and `.env` should be owner-only (`700` directory, `600` files). Rotate any credential that was shared outside a trusted private channel.
- Put production values in Vercel Environment Variables. Keep `SESSION_SECRET`, `CRON_SECRET`, `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, email, OAuth, identity, encryption, and AI keys server-only.
- Do not copy development secrets to Vercel or reuse a local key as a production key.

## Supabase access and evidence storage

1. Apply migrations in timestamp order, including `20261008000000_account_reviews_private_evidence.sql`.
2. In Supabase Storage, create `account-evidence` with **Public bucket disabled**. Keep `listing-images` separate; listing photos are public media and must never contain account credentials or private evidence.
3. Set `SUPABASE_ACCOUNT_EVIDENCE_BUCKET=account-evidence`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` only as server variables. The application rejects evidence uploads if the bucket is public or cannot be verified.
4. In the SQL editor, confirm RLS and grants after migrations:

```sql
select c.relname, c.relrowsecurity,
       has_table_privilege('anon', c.oid, 'select') as anon_select,
       has_table_privilege('authenticated', c.oid, 'select') as authenticated_select
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in ('users','sessions','orders','deliveries','ledger_entries',
                    'account_reviews','account_review_evidence')
order by c.relname;
```

Every listed table should have RLS enabled and the two direct SELECT privileges should be false. Do not grant browser roles access to evidence tables; the server uses the service role and checks user/admin ownership itself.

## Buyer screenshot review

- Buyers upload two screenshots only after account delivery. The server re-encodes them, strips image metadata, uses a private bucket, and gives only admins five-minute signed links.
- Ask for the game profile/UID and a relevant page after successful login. Tell buyers to hide email, phone, password, OTP, recovery codes, payment details, and other people's information.
- A screenshot proves only that the buyer could access the account at one moment. It does not prove exclusive ownership, publisher permission, or that the seller cannot recover the account later. A human must check the evidence and record a reason.
- Approval adds sandbox earnings to the seller wallet. It does not transfer real money. Keep live purchases closed until payment, refunds, custody, and seller withdrawal are separately cleared and implemented.
- Approved/refunded screenshots are retained for 30 days, then the daily retention job deletes the objects. Account deletion also removes that buyer's evidence. Check Storage logs after each retention run.

## Admin access

- Admin endpoints continue to require an authenticated session plus a row in `admin_accounts`; do not disable this check or make every signed-in user an admin.
- Bootstrap only the owner's verified account using the documented controlled seed procedure. Review the admin user list periodically and remove access when it is no longer needed.
- Confirm the owner's current account can open all admin sections, including the new Account reviews queue. Admin decisions need a reason and are written to the audit log.

## Rate limiting, backups, and alerts

- The Vercel adapter validates `X-Vercel-Forwarded-For` before using it for login, registration, OAuth, and password-reset limits. Review Vercel logs for 429 spikes and authentication failures; do not trust arbitrary client-supplied forwarding headers.
- Enable Supabase managed backups/PITR appropriate to the production plan. Record retention, access owners, and recovery credentials outside this repository.
- Restore a recent backup to a separate staging project at least once before launch. Verify migrations, login, order reads, encrypted-delivery key availability, and storage access before calling the restore successful.
- Configure Vercel deployment/function failure notifications and Supabase database/storage alerts to an owner-controlled address. `/api/health` is a readiness report, not uptime monitoring.
- Set a unique `CRON_SECRET` in Vercel Production. Verify both daily cron jobs appear in Vercel and complete successfully: account deletion and private evidence retention. Missing secrets cause cron requests to fail closed.
- Keep a short incident record with the date, affected users/data, containment action, owner, and follow-up. Never paste keys or screenshots containing account secrets into the record.

## Launch verification record

Before opening sales, record who verified each item and the date:

- Supabase RLS/grants and private evidence bucket.
- Vercel secrets, cron success, and failure notifications.
- Backup configuration and a successful restore drill.
- Admin access review and two-screenshot moderator workflow.
- Security review, supported game rules, operator/legal review, and jurisdiction-specific user notices.
