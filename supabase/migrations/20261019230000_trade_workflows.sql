-- Additive participant-scoped order workflows. Browser roles have no direct access.

BEGIN;

CREATE TABLE IF NOT EXISTS public.order_buyer_details(order_item_id TEXT PRIMARY KEY REFERENCES public.order_items(id),payload TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.delivery_batches(id TEXT PRIMARY KEY,order_item_id TEXT NOT NULL REFERENCES public.order_items(id),seller_id TEXT NOT NULL REFERENCES public.users(id),quantity INTEGER NOT NULL CHECK(quantity>0),delivered_total INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL,request_key TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(order_item_id,request_key));

CREATE TABLE IF NOT EXISTS public.order_artifacts(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES public.orders(id),order_item_id TEXT REFERENCES public.order_items(id),case_id TEXT,owner_id TEXT NOT NULL REFERENCES public.users(id),body TEXT NOT NULL DEFAULT '',object_path TEXT UNIQUE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.order_cancellations(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES public.orders(id),requester_id TEXT NOT NULL REFERENCES public.users(id),reason TEXT NOT NULL,details TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',resolution TEXT NOT NULL DEFAULT '',response_due_at TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cancellation_active ON public.order_cancellations(order_id) WHERE status IN ('pending','escalated');

CREATE TABLE IF NOT EXISTS public.cancellation_replies(cancellation_id TEXT NOT NULL REFERENCES public.order_cancellations(id),seller_id TEXT NOT NULL REFERENCES public.users(id),decision TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(cancellation_id,seller_id));

CREATE TABLE IF NOT EXISTS public.order_cases(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES public.orders(id),requester_id TEXT NOT NULL REFERENCES public.users(id),kind TEXT NOT NULL,source_id TEXT NOT NULL,reason TEXT NOT NULL,details TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',resolution TEXT NOT NULL DEFAULT '',remedy TEXT NOT NULL DEFAULT '',response_due_at TEXT NOT NULL,reviewed_by TEXT REFERENCES public.users(id),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(order_id,requester_id,kind,source_id));

CREATE TABLE IF NOT EXISTS public.order_case_entries(id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES public.order_cases(id),sender_id TEXT NOT NULL REFERENCES public.users(id),body TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.saved_searches(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,name TEXT NOT NULL,filters_json TEXT NOT NULL,fingerprint TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,fingerprint));

CREATE TABLE IF NOT EXISTS public.saved_search_matches(search_id TEXT NOT NULL REFERENCES public.saved_searches(id) ON DELETE CASCADE,listing_id TEXT NOT NULL REFERENCES public.listings(id) ON DELETE CASCADE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(search_id,listing_id));

CREATE INDEX IF NOT EXISTS idx_delivery_batches_item ON public.delivery_batches(order_item_id,created_at);

CREATE INDEX IF NOT EXISTS idx_order_artifacts_order ON public.order_artifacts(order_id,created_at);

CREATE INDEX IF NOT EXISTS idx_order_cases_queue ON public.order_cases(status,updated_at);

ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS completed_at TEXT;

ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS protection_until TEXT;

ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS delivered_quantity INTEGER NOT NULL DEFAULT 0;

ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS resolved_at TEXT;

ALTER TABLE public.delivery_batches ADD COLUMN IF NOT EXISTS delivered_total INTEGER NOT NULL DEFAULT 0;

ALTER TABLE public.order_buyer_details ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.order_buyer_details FROM PUBLIC, anon, authenticated;

ALTER TABLE public.delivery_batches ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.delivery_batches FROM PUBLIC, anon, authenticated;

ALTER TABLE public.order_artifacts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.order_artifacts FROM PUBLIC, anon, authenticated;

ALTER TABLE public.order_cancellations ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.order_cancellations FROM PUBLIC, anon, authenticated;

ALTER TABLE public.cancellation_replies ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.cancellation_replies FROM PUBLIC, anon, authenticated;

ALTER TABLE public.order_cases ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.order_cases FROM PUBLIC, anon, authenticated;

ALTER TABLE public.order_case_entries ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.order_case_entries FROM PUBLIC, anon, authenticated;

ALTER TABLE public.saved_searches ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.saved_searches FROM PUBLIC, anon, authenticated;

ALTER TABLE public.saved_search_matches ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.saved_search_matches FROM PUBLIC, anon, authenticated;

COMMIT;
