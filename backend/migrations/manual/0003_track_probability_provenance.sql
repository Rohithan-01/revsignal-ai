ALTER TABLE public.deals
    ADD COLUMN probability_is_known boolean NOT NULL DEFAULT false;
