-- New accounts start in English. Existing users keep their saved preference.
ALTER TABLE public.users ALTER COLUMN language SET DEFAULT 'en';
