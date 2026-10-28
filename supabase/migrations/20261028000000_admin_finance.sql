-- Private expense journal. Apply explicitly before deploying the admin console.
-- No provider, payment, or production configuration is changed by this migration.
BEGIN;
CREATE TABLE IF NOT EXISTS public.admin_expenses (
 id TEXT PRIMARY KEY, amount_minor BIGINT NOT NULL CHECK(amount_minor>0),
 currency TEXT NOT NULL, book TEXT NOT NULL CHECK(book IN ('live','sandbox','stripe_test')),
 category TEXT NOT NULL, description TEXT NOT NULL, incurred_on TEXT NOT NULL,
 created_by TEXT NOT NULL REFERENCES public.users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 voided_at TEXT, voided_by TEXT REFERENCES public.users(id), void_reason TEXT NOT NULL DEFAULT ''
);
ALTER TABLE public.admin_expenses ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.admin_expenses FROM PUBLIC, anon, authenticated;
CREATE INDEX IF NOT EXISTS idx_admin_expenses_period ON public.admin_expenses(book,currency,incurred_on);
CREATE INDEX IF NOT EXISTS idx_ledger_reporting ON public.ledger_entries(entry_type,currency,created_at,order_id);
COMMIT;
