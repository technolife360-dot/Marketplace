ALTER TABLE public.topup_packages
    ADD COLUMN IF NOT EXISTS supplier_type_id text NOT NULL DEFAULT '';
