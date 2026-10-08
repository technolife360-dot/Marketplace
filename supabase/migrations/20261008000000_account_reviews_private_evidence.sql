-- Buyer screenshots for game-account orders are private and moderator-reviewed.
BEGIN;

CREATE TABLE IF NOT EXISTS public.account_reviews (
  order_id TEXT PRIMARY KEY REFERENCES public.orders(id) ON DELETE CASCADE,
  buyer_id TEXT NOT NULL REFERENCES public.users(id),
  status TEXT NOT NULL DEFAULT 'collecting'
    CHECK (status IN ('collecting', 'pending', 'needs_info', 'approved', 'refunded')),
  buyer_attested_at TEXT,
  review_note TEXT NOT NULL DEFAULT '',
  reviewed_by TEXT REFERENCES public.users(id),
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  submitted_at TEXT,
  reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS public.account_review_evidence (
  order_id TEXT NOT NULL REFERENCES public.account_reviews(order_id) ON DELETE CASCADE,
  slot INTEGER NOT NULL CHECK (slot IN (1, 2)),
  object_path TEXT NOT NULL UNIQUE,
  uploaded_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  PRIMARY KEY (order_id, slot)
);

ALTER TABLE public.account_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_review_evidence ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.account_reviews, public.account_review_evidence FROM anon, authenticated;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname IN ('account_reviews', 'account_review_evidence')
      AND NOT c.relrowsecurity
  ) THEN
    RAISE EXCEPTION 'Account evidence tables must have row-level security enabled';
  END IF;
  IF has_table_privilege('anon', 'public.account_review_evidence', 'SELECT')
     OR has_table_privilege('authenticated', 'public.account_review_evidence', 'SELECT')
     OR has_table_privilege('anon', 'public.account_reviews', 'SELECT')
     OR has_table_privilege('authenticated', 'public.account_reviews', 'SELECT') THEN
    RAISE EXCEPTION 'Browser roles must not directly read private account review data';
  END IF;
END;
$$;

COMMIT;
