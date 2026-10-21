-- Purchase-verified feedback, language filters and helpful votes.
BEGIN;
ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS updated_at TEXT;
ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS hidden INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS public.topup_reviews (
        id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES topup_orders(id) ON DELETE CASCADE,
        reviewer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), body TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0 CHECK(hidden IN (0,1)),
        reply TEXT NOT NULL DEFAULT '', replied_by TEXT REFERENCES users(id) ON DELETE SET NULL, replied_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS public.purchase_review_reports (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('listing','topup')),
        review_id TEXT NOT NULL, reporter_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','dismissed','removed')),
        resolution TEXT NOT NULL DEFAULT '', resolved_by TEXT REFERENCES users(id) ON DELETE SET NULL, resolved_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(kind,review_id,reporter_id));
CREATE TABLE IF NOT EXISTS public.purchase_review_helpful (
        kind TEXT NOT NULL CHECK(kind IN ('listing','topup')), review_id TEXT NOT NULL,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(kind,review_id,user_id));
CREATE INDEX IF NOT EXISTS purchase_review_reports_status ON public.purchase_review_reports(status,created_at);
CREATE INDEX IF NOT EXISTS review_order_items_listing ON public.order_items(listing_id,order_id);
CREATE INDEX IF NOT EXISTS review_topup_orders_package ON public.topup_orders(package_id,status);
ALTER TABLE public.topup_reviews ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT '';
CREATE OR REPLACE VIEW public.visible_reviews WITH (security_invoker=true) AS SELECT * FROM public.reviews WHERE hidden=0;
REVOKE ALL ON public.visible_reviews FROM PUBLIC, anon, authenticated;
ALTER TABLE public.topup_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.topup_reviews FROM PUBLIC, anon, authenticated;
ALTER TABLE public.purchase_review_reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.purchase_review_reports FROM PUBLIC, anon, authenticated;
ALTER TABLE public.purchase_review_helpful ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.purchase_review_helpful FROM PUBLIC, anon, authenticated;
COMMIT;
