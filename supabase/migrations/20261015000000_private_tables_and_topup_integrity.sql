-- Server-owned tables stay private. This migration is safe to re-run.
BEGIN;

ALTER TABLE public.seller_profiles ALTER COLUMN selling_enabled SET DEFAULT 0;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'users','admin_accounts','sessions','oauth_identities','email_tokens','seller_profiles',
    'games','categories','listings','favorites','carts','orders','order_items','order_events',
    'payments','ledger_entries','deliveries','product_requests','request_responses',
    'conversations','messages','notifications','reviews','reports',
    'account_deletion_requests','payout_requests','platform_config','audit_logs',
    'rate_limits','blog_posts','account_reviews','account_review_evidence',
    'topup_packages','topup_orders','topup_inventory_events'
  ] LOOP
    IF to_regclass(format('public.%I', table_name)) IS NULL THEN
      RAISE EXCEPTION 'Missing required marketplace table: %', table_name;
    END IF;
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated', table_name);
  END LOOP;
END $$;

-- NOT VALID avoids rejecting legacy rows while enforcing these rules for new writes.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.topup_packages'::regclass AND conname='topup_packages_flags_binary') THEN
    ALTER TABLE public.topup_packages ADD CONSTRAINT topup_packages_flags_binary
      CHECK (enabled IN (0,1) AND coming_soon IN (0,1) AND manual_enabled IN (0,1) AND supplier_enabled IN (0,1)) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.topup_orders'::regclass AND conname='topup_orders_fulfillment_nonnegative') THEN
    ALTER TABLE public.topup_orders ADD CONSTRAINT topup_orders_fulfillment_nonnegative
      CHECK (inventory_quantity >= 0 AND supplier_quantity >= 0) NOT VALID;
  END IF;
END $$;

COMMIT;
