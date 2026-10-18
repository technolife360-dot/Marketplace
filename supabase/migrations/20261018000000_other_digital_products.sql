INSERT INTO public.categories (id, slug, name, product_type, active)
VALUES ('digital', 'digital', 'Other digital products', 'digital', 1)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  product_type = EXCLUDED.product_type,
  active = 1;
