-- The seller wizard needs a real category row before it can accept top-up offers.
-- Idempotent reference data only; preserve any existing admin configuration.
INSERT INTO public.categories(id, slug, name, product_type)
VALUES ('top-ups', 'top-ups', 'Game top-ups', 'currency')
ON CONFLICT (id) DO NOTHING;
