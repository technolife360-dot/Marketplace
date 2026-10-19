-- Additive marketplace UX schema. Browser roles never access these tables directly.

BEGIN;

ALTER TABLE public.listings ADD COLUMN IF NOT EXISTS delivery_minutes INTEGER;

CREATE TABLE IF NOT EXISTS public.seller_follows (
        user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        seller_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id,seller_id), CHECK(user_id<>seller_id));

CREATE TABLE IF NOT EXISTS public.review_replies (
        review_id TEXT PRIMARY KEY REFERENCES public.reviews(id) ON DELETE CASCADE,
        seller_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.message_attachments (
        message_id TEXT PRIMARY KEY REFERENCES public.messages(id) ON DELETE CASCADE,
        conversation_id TEXT NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
        owner_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        object_path TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.listing_alert_state (
        listing_id TEXT PRIMARY KEY REFERENCES public.listings(id) ON DELETE CASCADE,
        price_minor BIGINT NOT NULL, available INTEGER NOT NULL,
        published_once INTEGER NOT NULL DEFAULT 0);

CREATE INDEX IF NOT EXISTS idx_follows_seller ON public.seller_follows(seller_id);

CREATE INDEX IF NOT EXISTS idx_messages_recent ON public.messages(conversation_id,created_at,id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_order_conversation ON public.conversations(order_id,buyer_id,seller_id) WHERE order_id IS NOT NULL;

ALTER TABLE public.seller_follows ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.seller_follows FROM PUBLIC, anon, authenticated;

ALTER TABLE public.review_replies ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.review_replies FROM PUBLIC, anon, authenticated;

ALTER TABLE public.message_attachments ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.message_attachments FROM PUBLIC, anon, authenticated;

ALTER TABLE public.listing_alert_state ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.listing_alert_state FROM PUBLIC, anon, authenticated;

COMMIT;
