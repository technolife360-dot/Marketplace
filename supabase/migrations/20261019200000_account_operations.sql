-- Additive account security, support, disputes and delivery promises.

BEGIN;

CREATE TABLE IF NOT EXISTS public.account_security(user_id TEXT PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,secret_cipher TEXT NOT NULL DEFAULT '',pending_cipher TEXT NOT NULL DEFAULT '',pending_expires TEXT,enabled INTEGER NOT NULL DEFAULT 0,last_step BIGINT NOT NULL DEFAULT -1);

CREATE TABLE IF NOT EXISTS public.security_recovery_codes(user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,code_hash TEXT NOT NULL,used_at TEXT,PRIMARY KEY(user_id,code_hash));

CREATE TABLE IF NOT EXISTS public.pending_email_changes(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,new_email TEXT NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.seller_availability(user_id TEXT PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,timezone TEXT NOT NULL DEFAULT 'UTC',hours_json TEXT NOT NULL DEFAULT '[]',vacation INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.user_blocks(user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,blocked_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,blocked_id),CHECK(user_id<>blocked_id));

CREATE TABLE IF NOT EXISTS public.support_tickets(id TEXT PRIMARY KEY,requester_id TEXT NOT NULL REFERENCES public.users(id),order_id TEXT REFERENCES public.orders(id),subject TEXT NOT NULL,category TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.support_entries(id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES public.support_tickets(id) ON DELETE CASCADE,sender_id TEXT NOT NULL REFERENCES public.users(id),body TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.dispute_entries(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES public.orders(id),sender_id TEXT NOT NULL REFERENCES public.users(id),body TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS public.dispute_attachments(entry_id TEXT PRIMARY KEY REFERENCES public.dispute_entries(id) ON DELETE CASCADE,owner_id TEXT NOT NULL REFERENCES public.users(id),object_path TEXT NOT NULL UNIQUE);

CREATE TABLE IF NOT EXISTS public.order_deadline_notices(order_item_id TEXT NOT NULL REFERENCES public.order_items(id),kind TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(order_item_id,kind));

CREATE INDEX IF NOT EXISTS idx_support_owner ON public.support_tickets(requester_id,updated_at);

CREATE INDEX IF NOT EXISTS idx_support_entries ON public.support_entries(ticket_id,created_at);

CREATE INDEX IF NOT EXISTS idx_dispute_entries ON public.dispute_entries(order_id,created_at);

CREATE INDEX IF NOT EXISTS idx_blocks_reverse ON public.user_blocks(blocked_id,user_id);

ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS created_at TEXT NOT NULL DEFAULT '';

ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS last_seen_at TEXT NOT NULL DEFAULT '';

ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS user_agent TEXT NOT NULL DEFAULT '';

ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS network_label TEXT NOT NULL DEFAULT '';

ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS mfa_verified INTEGER NOT NULL DEFAULT 0;

ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS snapshot_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE public.order_items ADD COLUMN IF NOT EXISTS delivery_due_at TEXT;

ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS response_due_at TEXT;

ALTER TABLE public.account_security ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.account_security FROM PUBLIC, anon, authenticated;

ALTER TABLE public.security_recovery_codes ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.security_recovery_codes FROM PUBLIC, anon, authenticated;

ALTER TABLE public.pending_email_changes ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.pending_email_changes FROM PUBLIC, anon, authenticated;

ALTER TABLE public.seller_availability ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.seller_availability FROM PUBLIC, anon, authenticated;

ALTER TABLE public.user_blocks ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.user_blocks FROM PUBLIC, anon, authenticated;

ALTER TABLE public.support_tickets ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.support_tickets FROM PUBLIC, anon, authenticated;

ALTER TABLE public.support_entries ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.support_entries FROM PUBLIC, anon, authenticated;

ALTER TABLE public.dispute_entries ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.dispute_entries FROM PUBLIC, anon, authenticated;

ALTER TABLE public.dispute_attachments ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.dispute_attachments FROM PUBLIC, anon, authenticated;

ALTER TABLE public.order_deadline_notices ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.order_deadline_notices FROM PUBLIC, anon, authenticated;

COMMIT;
