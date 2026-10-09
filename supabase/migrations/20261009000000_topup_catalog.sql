CREATE TABLE IF NOT EXISTS public.topup_packages (
    id text PRIMARY KEY,
    game_slug text NOT NULL,
    game_name text NOT NULL,
    url_slug text NOT NULL,
    currency text NOT NULL,
    amount integer NOT NULL CHECK (amount > 0),
    price_minor bigint NOT NULL DEFAULT 0 CHECK (price_minor >= 0),
    stock_on_hand integer NOT NULL DEFAULT 0 CHECK (stock_on_hand >= 0),
    stock_reserved integer NOT NULL DEFAULT 0 CHECK (stock_reserved >= 0),
    enabled integer NOT NULL DEFAULT 1,
    manual_enabled integer NOT NULL DEFAULT 1,
    supplier_enabled integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (game_slug, url_slug),
    CHECK (stock_reserved <= stock_on_hand)
);

CREATE TABLE IF NOT EXISTS public.topup_orders (
    id text PRIMARY KEY,
    reference text NOT NULL UNIQUE,
    buyer_id text NOT NULL REFERENCES public.users(id),
    package_id text NOT NULL REFERENCES public.topup_packages(id),
    player_id text NOT NULL,
    server_id text NOT NULL DEFAULT '',
    quantity integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price_minor bigint NOT NULL CHECK (unit_price_minor > 0),
    currency text NOT NULL DEFAULT 'UZS',
    status text NOT NULL DEFAULT 'awaiting_payment',
    payment_reference text NOT NULL DEFAULT '',
    inventory_quantity integer NOT NULL DEFAULT 0,
    supplier_quantity integer NOT NULL DEFAULT 0,
    supplier_reference text NOT NULL DEFAULT '',
    fulfillment_note text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CHECK (inventory_quantity + supplier_quantity <= quantity)
);

CREATE TABLE IF NOT EXISTS public.topup_inventory_events (
    id text PRIMARY KEY,
    package_id text NOT NULL REFERENCES public.topup_packages(id),
    actor_id text REFERENCES public.users(id),
    delta integer NOT NULL,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.topup_packages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.topup_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.topup_inventory_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.topup_packages, public.topup_orders, public.topup_inventory_events FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS idx_topup_orders_created ON public.topup_orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_topup_orders_buyer ON public.topup_orders(buyer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_topup_inventory_events_package ON public.topup_inventory_events(package_id, created_at DESC);
