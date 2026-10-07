-- Record seller and buyer acknowledgments for account-sale-specific risks.
-- The application keeps sales fail-closed until a game is separately cleared.
BEGIN;

ALTER TABLE public.listings
  ADD COLUMN IF NOT EXISTS seller_account_terms_version TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS seller_account_terms_at TEXT;

ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS accepted_account_sale_terms_version TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS accepted_account_sale_terms_at TEXT;

COMMIT;
