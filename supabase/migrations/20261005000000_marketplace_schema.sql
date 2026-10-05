-- Supabase/PostgreSQL schema for SentryLoot.
-- Keep the tables private to the server-side application: RLS is enabled and
-- anon/authenticated receive no direct table grants or policies.
BEGIN;

CREATE TABLE IF NOT EXISTS public.users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT 'UZ',
  language TEXT NOT NULL DEFAULT 'uz',
  currency TEXT NOT NULL DEFAULT 'UZS',
  email_verified SMALLINT NOT NULL DEFAULT 0 CHECK (email_verified IN (0, 1)),
  suspended SMALLINT NOT NULL DEFAULT 0 CHECK (suspended IN (0, 1)),
  accepted_terms_version TEXT NOT NULL DEFAULT '',
  accepted_terms_at TEXT,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON public.users (lower(email));

CREATE TABLE IF NOT EXISTS public.admin_accounts (
  user_id TEXT PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  csrf TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.oauth_identities (
  provider TEXT NOT NULL CHECK (provider IN ('google', 'apple')),
  subject TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  PRIMARY KEY (provider, subject),
  UNIQUE (provider, user_id)
);
CREATE TABLE IF NOT EXISTS public.email_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS public.seller_profiles (
  user_id TEXT PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  shop_name TEXT NOT NULL,
  bio TEXT NOT NULL DEFAULT '',
  verification_status TEXT NOT NULL DEFAULT 'unverified',
  selling_enabled SMALLINT NOT NULL DEFAULT 1 CHECK (selling_enabled IN (0, 1)),
  identity_status TEXT NOT NULL DEFAULT 'not_started',
  identity_provider TEXT NOT NULL DEFAULT '',
  identity_reference TEXT NOT NULL DEFAULT '',
  identity_verified_at TEXT,
  identity_consent_at TEXT,
  identity_consent_version TEXT NOT NULL DEFAULT '',
  identity_last_event_at TEXT,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.games (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  active SMALLINT NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE TABLE IF NOT EXISTS public.categories (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  product_type TEXT NOT NULL,
  active SMALLINT NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE TABLE IF NOT EXISTS public.listings (
  id TEXT PRIMARY KEY,
  seller_id TEXT NOT NULL REFERENCES public.users(id),
  game_id TEXT NOT NULL REFERENCES public.games(id),
  category_id TEXT NOT NULL REFERENCES public.categories(id),
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  product_type TEXT NOT NULL,
  price_minor BIGINT NOT NULL CHECK (price_minor > 0),
  currency TEXT NOT NULL DEFAULT 'UZS',
  platform TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  attributes_json TEXT NOT NULL DEFAULT '{}',
  delivery_method TEXT NOT NULL DEFAULT 'manual',
  delivery_eta TEXT NOT NULL DEFAULT '24 hours',
  requirements TEXT NOT NULL DEFAULT '',
  stock INTEGER NOT NULL DEFAULT 1 CHECK (stock >= 0),
  reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
  status TEXT NOT NULL DEFAULT 'draft',
  moderation_note TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  updated_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  search_vector TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('simple'::regconfig, coalesce(title, '') || ' ' || coalesce(description, ''))
  ) STORED
);
CREATE INDEX IF NOT EXISTS idx_listings_search ON public.listings USING GIN (search_vector);
CREATE TABLE IF NOT EXISTS public.favorites (
  user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  listing_id TEXT NOT NULL REFERENCES public.listings(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  PRIMARY KEY (user_id, listing_id)
);
CREATE TABLE IF NOT EXISTS public.carts (
  user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  listing_id TEXT NOT NULL REFERENCES public.listings(id) ON DELETE CASCADE,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  updated_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  PRIMARY KEY (user_id, listing_id)
);
CREATE TABLE IF NOT EXISTS public.orders (
  id TEXT PRIMARY KEY,
  reference TEXT NOT NULL UNIQUE,
  buyer_id TEXT NOT NULL REFERENCES public.users(id),
  currency TEXT NOT NULL,
  subtotal_minor BIGINT NOT NULL,
  commission_minor BIGINT NOT NULL,
  commission_bps INTEGER NOT NULL DEFAULT 0,
  total_minor BIGINT NOT NULL,
  status TEXT NOT NULL,
  payment_mode TEXT NOT NULL,
  accepted_checkout_terms_version TEXT NOT NULL DEFAULT '',
  accepted_checkout_terms_at TEXT,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  updated_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.order_items (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES public.orders(id),
  listing_id TEXT NOT NULL REFERENCES public.listings(id),
  seller_id TEXT NOT NULL REFERENCES public.users(id),
  title TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit_price_minor BIGINT NOT NULL,
  commission_minor BIGINT NOT NULL,
  delivery_method TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS public.order_events (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES public.orders(id),
  actor_id TEXT REFERENCES public.users(id),
  from_status TEXT,
  to_status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.payments (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL UNIQUE REFERENCES public.orders(id),
  provider TEXT NOT NULL,
  provider_reference TEXT UNIQUE,
  amount_minor BIGINT NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  updated_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.ledger_entries (
  id TEXT PRIMARY KEY,
  order_id TEXT REFERENCES public.orders(id),
  user_id TEXT REFERENCES public.users(id),
  entry_type TEXT NOT NULL,
  amount_minor BIGINT NOT NULL,
  currency TEXT NOT NULL,
  description TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.deliveries (
  id TEXT PRIMARY KEY,
  order_item_id TEXT NOT NULL UNIQUE REFERENCES public.order_items(id),
  seller_id TEXT NOT NULL REFERENCES public.users(id),
  protected_payload TEXT NOT NULL,
  submitted_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  buyer_accessed_at TEXT
);
CREATE TABLE IF NOT EXISTS public.product_requests (
  id TEXT PRIMARY KEY,
  requester_id TEXT NOT NULL REFERENCES public.users(id),
  game_id TEXT NOT NULL REFERENCES public.games(id),
  category_id TEXT REFERENCES public.categories(id),
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  budget_minor BIGINT,
  currency TEXT NOT NULL DEFAULT 'UZS',
  expires_at TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.request_responses (
  id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES public.product_requests(id),
  seller_id TEXT NOT NULL REFERENCES public.users(id),
  message TEXT NOT NULL,
  listing_id TEXT REFERENCES public.listings(id),
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.conversations (
  id TEXT PRIMARY KEY,
  buyer_id TEXT NOT NULL REFERENCES public.users(id),
  seller_id TEXT NOT NULL REFERENCES public.users(id),
  listing_id TEXT REFERENCES public.listings(id),
  order_id TEXT REFERENCES public.orders(id),
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  UNIQUE (buyer_id, seller_id, listing_id)
);
CREATE TABLE IF NOT EXISTS public.messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
  sender_id TEXT NOT NULL REFERENCES public.users(id),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  read_at TEXT
);
CREATE TABLE IF NOT EXISTS public.notifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  href TEXT NOT NULL DEFAULT '/',
  read_at TEXT,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.reviews (
  id TEXT PRIMARY KEY,
  order_item_id TEXT NOT NULL UNIQUE REFERENCES public.order_items(id),
  reviewer_id TEXT NOT NULL REFERENCES public.users(id),
  seller_id TEXT NOT NULL REFERENCES public.users(id),
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.reports (
  id TEXT PRIMARY KEY,
  reporter_id TEXT NOT NULL REFERENCES public.users(id),
  listing_id TEXT REFERENCES public.listings(id),
  order_id TEXT REFERENCES public.orders(id),
  reason TEXT NOT NULL,
  details TEXT NOT NULL,
  evidence_url TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  resolution TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS public.account_deletion_requests (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES public.users(id),
  status TEXT NOT NULL DEFAULT 'pending',
  reason TEXT NOT NULL DEFAULT '',
  reviewed_by TEXT REFERENCES public.users(id),
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS public.payout_requests (
  id TEXT PRIMARY KEY,
  seller_id TEXT NOT NULL REFERENCES public.users(id),
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
  currency TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  admin_id TEXT REFERENCES public.users(id),
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  updated_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.platform_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.audit_logs (
  id TEXT PRIMARY KEY,
  actor_id TEXT REFERENCES public.users(id),
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS public.rate_limits (
  bucket TEXT NOT NULL,
  subject TEXT NOT NULL,
  window_start BIGINT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket, subject, window_start)
);
CREATE TABLE IF NOT EXISTS public.blog_posts (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  category_json TEXT NOT NULL,
  title_json TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  body_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
  author_id TEXT REFERENCES public.users(id),
  created_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  updated_at TEXT NOT NULL DEFAULT to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'),
  published_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_listings_public ON public.listings(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_game_category ON public.listings(game_id, category_id, status);
CREATE INDEX IF NOT EXISTS idx_listings_price ON public.listings(price_minor, status);
CREATE INDEX IF NOT EXISTS idx_listings_seller ON public.listings(seller_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_buyer ON public.orders(buyer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_items_seller ON public.order_items(seller_id, order_id);
CREATE INDEX IF NOT EXISTS idx_events_order ON public.order_events(order_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON public.messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_requests_open ON public.product_requests(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON public.notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON public.ledger_entries(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_status ON public.reports(status, created_at DESC);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.oauth_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seller_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.games ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.carts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.request_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_deletion_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payout_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.platform_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rate_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.blog_posts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.users, public.admin_accounts, public.sessions, public.oauth_identities,
  public.email_tokens, public.seller_profiles, public.games, public.categories, public.listings,
  public.favorites, public.carts, public.orders, public.order_items, public.order_events,
  public.payments, public.ledger_entries, public.deliveries, public.product_requests,
  public.request_responses, public.conversations, public.messages, public.notifications,
  public.reviews, public.reports, public.account_deletion_requests, public.payout_requests,
  public.platform_config, public.audit_logs, public.rate_limits, public.blog_posts
FROM anon, authenticated;

INSERT INTO public.platform_config(key, value) VALUES
  ('commission_bps', '0'),
  ('completion_window_hours', '72'),
  ('terms_version', 'draft-2026-10')
ON CONFLICT (key) DO NOTHING;
INSERT INTO public.games(id, slug, name) VALUES
  ('valorant', 'valorant', 'Valorant'),
  ('pubg-mobile', 'pubg-mobile', 'PUBG Mobile'),
  ('dota-2', 'dota-2', 'Dota 2'),
  ('counter-strike-2', 'counter-strike-2', 'Counter-Strike 2'),
  ('mobile-legends', 'mobile-legends', 'Mobile Legends')
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.categories(id, slug, name, product_type) VALUES
  ('accounts', 'accounts', 'Gaming accounts', 'account'),
  ('items', 'items', 'Items & skins', 'item'),
  ('currency', 'currency', 'In-game currency', 'currency'),
  ('services', 'services', 'Coaching & services', 'service'),
  ('codes', 'codes', 'Gift cards & digital codes', 'code')
ON CONFLICT (id) DO NOTHING;

COMMIT;
