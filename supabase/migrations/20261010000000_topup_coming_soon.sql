ALTER TABLE public.topup_packages
    ADD COLUMN IF NOT EXISTS coming_soon integer NOT NULL DEFAULT 1;
