-- Validate the checks after auditing legacy top-up rows.
BEGIN;

ALTER TABLE public.topup_packages
  VALIDATE CONSTRAINT topup_packages_flags_binary;

ALTER TABLE public.topup_orders
  VALIDATE CONSTRAINT topup_orders_fulfillment_nonnegative;

COMMIT;
