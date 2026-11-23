-- Manual, data-preserving alignment for the audited legacy revsignal schema.
--
-- This script deliberately does not convert deals.created_at. The legacy
-- timestamp values are TIMESTAMP WITHOUT TIME ZONE and their source timezone
-- has not been confirmed. Resolve that separately before converting it to
-- TIMESTAMPTZ.
--
-- Preconditions are intentionally strict: review the live schema, row counts,
-- and backup before execution. This script is expected to run once.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $database_guard$
BEGIN
    IF current_database() <> 'revsignal' THEN
        RAISE EXCEPTION
            'Migration stopped: connected database is %, expected revsignal',
            current_database();
    END IF;
END;
$database_guard$;

-- Prevent row counts or relationships changing between preflight and commit.
LOCK TABLE public.deals, public.activities IN ACCESS EXCLUSIVE MODE;

DO $preflight$
DECLARE
    deal_columns text[];
    activity_columns text[];
    deal_count bigint;
    activity_count bigint;
    close_date_type text;
    created_at_type text;
    fk_column smallint;
    fk_target_column smallint;
BEGIN
    IF to_regclass('public.deals') IS NULL
       OR to_regclass('public.activities') IS NULL THEN
        RAISE EXCEPTION
            'Migration stopped: public.deals and public.activities must both exist';
    END IF;

    SELECT array_agg(column_name::text ORDER BY ordinal_position)
      INTO deal_columns
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'deals';

    IF deal_columns IS DISTINCT FROM ARRAY[
        'id', 'company', 'deal_value', 'stage', 'probability',
        'expected_close_date', 'created_at'
    ]::text[] THEN
        RAISE EXCEPTION
            'Migration stopped: public.deals columns differ from the audited legacy schema: %',
            deal_columns;
    END IF;

    SELECT array_agg(column_name::text ORDER BY ordinal_position)
      INTO activity_columns
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'activities';

    IF activity_columns IS DISTINCT FROM ARRAY[
        'id', 'deal_id', 'activity_type', 'activity_date', 'notes'
    ]::text[] THEN
        RAISE EXCEPTION
            'Migration stopped: public.activities columns differ from the audited schema: %',
            activity_columns;
    END IF;

    SELECT format_type(a.atttypid, a.atttypmod)
      INTO close_date_type
      FROM pg_attribute AS a
     WHERE a.attrelid = 'public.deals'::regclass
       AND a.attname = 'expected_close_date'
       AND a.attnum > 0
       AND NOT a.attisdropped;

    SELECT format_type(a.atttypid, a.atttypmod)
      INTO created_at_type
      FROM pg_attribute AS a
     WHERE a.attrelid = 'public.deals'::regclass
       AND a.attname = 'created_at'
       AND a.attnum > 0
       AND NOT a.attisdropped;

    IF close_date_type IS DISTINCT FROM 'timestamp without time zone'
       OR created_at_type IS DISTINCT FROM 'timestamp without time zone' THEN
        RAISE EXCEPTION
            'Migration stopped: expected_close_date and created_at must both still be timestamp without time zone (found %, %)',
            close_date_type, created_at_type;
    END IF;

    IF pg_get_serial_sequence('public.deals', 'id') IS NULL
       OR pg_get_serial_sequence('public.activities', 'id') IS NULL
       OR pg_get_serial_sequence('public.deals', 'id')
          IS DISTINCT FROM 'public.deals_id_seq'
       OR pg_get_serial_sequence('public.activities', 'id')
          IS DISTINCT FROM 'public.activities_id_seq' THEN
        RAISE EXCEPTION
            'Migration stopped: expected owned deals_id_seq and activities_id_seq sequences were not found';
    END IF;

    IF to_regclass('public.deals_pkey') IS NULL
       OR to_regclass('public.activities_pkey') IS NULL
       OR to_regclass('public.ix_deals_id') IS NULL
       OR to_regclass('public.ix_activities_id') IS NULL
       OR to_regclass('public.ix_deals_deal_id') IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration stopped: audited indexes are missing or the new deal ID index name is already in use';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM (
              VALUES
                  ('deals', 'id', 'integer', true, 'nextval(''deals_id_seq''::regclass)'),
                  ('deals', 'company', 'character varying(255)', true, NULL::text),
                  ('deals', 'deal_value', 'double precision', true, NULL::text),
                  ('deals', 'stage', 'character varying(100)', true, NULL::text),
                  ('deals', 'probability', 'double precision', true, NULL::text),
                  ('deals', 'expected_close_date', 'timestamp without time zone', false, NULL::text),
                  ('deals', 'created_at', 'timestamp without time zone', true, NULL::text),
                  ('activities', 'id', 'integer', true, 'nextval(''activities_id_seq''::regclass)'),
                  ('activities', 'deal_id', 'integer', true, NULL::text),
                  ('activities', 'activity_type', 'character varying(50)', true, NULL::text),
                  ('activities', 'activity_date', 'timestamp with time zone', true, NULL::text),
                  ('activities', 'notes', 'character varying(500)', false, NULL::text)
          ) AS expected(table_name, column_name, column_type, not_null, column_default)
          LEFT JOIN pg_class AS tbl
            ON tbl.oid = to_regclass('public.' || expected.table_name)
          LEFT JOIN pg_attribute AS attr
            ON attr.attrelid = tbl.oid
           AND attr.attname = expected.column_name
           AND attr.attnum > 0
           AND NOT attr.attisdropped
          LEFT JOIN pg_attrdef AS def
            ON def.adrelid = tbl.oid
           AND def.adnum = attr.attnum
         WHERE attr.attname IS NULL
            OR format_type(attr.atttypid, attr.atttypmod)
                 IS DISTINCT FROM expected.column_type
            OR attr.attnotnull IS DISTINCT FROM expected.not_null
            OR pg_get_expr(def.adbin, def.adrelid)
                 IS DISTINCT FROM expected.column_default
    ) THEN
        RAISE EXCEPTION
            'Migration stopped: an audited existing column type, nullability, or default has changed';
    END IF;

    SELECT attr.attnum
      INTO fk_column
      FROM pg_attribute AS attr
     WHERE attr.attrelid = 'public.activities'::regclass
       AND attr.attname = 'deal_id'
       AND attr.attnum > 0
       AND NOT attr.attisdropped;

    SELECT attr.attnum
      INTO fk_target_column
      FROM pg_attribute AS attr
     WHERE attr.attrelid = 'public.deals'::regclass
       AND attr.attname = 'id'
       AND attr.attnum > 0
       AND NOT attr.attisdropped;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint AS c
         WHERE c.conrelid = 'public.activities'::regclass
           AND c.confrelid = 'public.deals'::regclass
           AND c.contype = 'f'
           AND c.confupdtype = 'a'
           AND c.confdeltype = 'a'
           AND c.conkey = ARRAY[fk_column]::smallint[]
           AND c.confkey = ARRAY[fk_target_column]::smallint[]
    ) THEN
        RAISE EXCEPTION
            'Migration stopped: expected activities.deal_id -> deals.id foreign key was not found';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint AS c
         WHERE c.conrelid = 'public.deals'::regclass
           AND c.contype = 'p'
           AND c.conkey = ARRAY[
               (
                   SELECT attnum
                     FROM pg_attribute
                    WHERE attrelid = 'public.deals'::regclass
                      AND attname = 'id'
               )
           ]::smallint[]
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_constraint AS c
         WHERE c.conrelid = 'public.activities'::regclass
           AND c.contype = 'p'
           AND c.conkey = ARRAY[
               (
                   SELECT attnum
                     FROM pg_attribute
                    WHERE attrelid = 'public.activities'::regclass
                      AND attname = 'id'
               )
           ]::smallint[]
    ) THEN
        RAISE EXCEPTION
            'Migration stopped: the audited primary keys on deals.id and activities.id were not found';
    END IF;

    SELECT count(*) INTO deal_count FROM public.deals;
    SELECT count(*) INTO activity_count FROM public.activities;

    IF deal_count <> 4 OR activity_count <> 2 THEN
        RAISE EXCEPTION
            'Migration stopped: expected 4 deals and 2 activities, found % deals and % activities',
            deal_count, activity_count;
    END IF;
END;
$preflight$;

-- This cast retains each stored calendar date; it does not apply a timezone.
ALTER TABLE public.deals
    ALTER COLUMN expected_close_date
    TYPE date
    USING expected_close_date::date;

-- Add the CRM/dashboard fields expected by the current Deal model.
-- Required columns are backfilled below before NOT NULL is applied.
ALTER TABLE public.deals
    ADD COLUMN deal_id varchar(100),
    ADD COLUMN status varchar(50),
    ADD COLUMN created_date date,
    ADD COLUMN last_activity_date date,
    ADD COLUMN activity_count integer,
    ADD COLUMN meeting_count integer,
    ADD COLUMN email_count integer,
    ADD COLUMN stakeholder_count integer,
    ADD COLUMN risk_score integer,
    ADD COLUMN risk_level varchar(20),
    ADD COLUMN risk_reasons text,
    ADD COLUMN recommended_action text,
    ADD COLUMN updated_at timestamp with time zone;

-- Keep existing rows. Stable legacy IDs avoid collisions with future UUIDs.
-- Activity count and last activity date are derived from the existing related
-- activity rows; the date uses the application's Asia/Kolkata business day.
-- Meeting/email/stakeholder counts cannot be reliably inferred from the
-- existing activity table and remain NULL.
UPDATE public.deals AS d
   SET deal_id = 'legacy-' || d.id::text,
       status = 'open',
       created_date = NULL,
       last_activity_date = (
           SELECT max(a.activity_date AT TIME ZONE 'Asia/Kolkata')::date
             FROM public.activities AS a
            WHERE a.deal_id = d.id
       ),
       activity_count = (
           SELECT count(*)::integer
             FROM public.activities AS a
            WHERE a.deal_id = d.id
       ),
       meeting_count = NULL,
       email_count = NULL,
       stakeholder_count = NULL,
       risk_score = 0,
       risk_level = 'LOW',
       risk_reasons = '[]',
       recommended_action = '',
       updated_at = transaction_timestamp();

ALTER TABLE public.deals
    ALTER COLUMN deal_id SET NOT NULL,
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN risk_score SET NOT NULL,
    ALTER COLUMN risk_level SET NOT NULL,
    ALTER COLUMN risk_reasons SET NOT NULL,
    ALTER COLUMN recommended_action SET NOT NULL,
    ALTER COLUMN updated_at SET NOT NULL;

-- Matches SQLAlchemy's unique indexed Deal.deal_id mapping.
CREATE UNIQUE INDEX ix_deals_deal_id
    ON public.deals USING btree (deal_id);

DO $verification$
DECLARE
    deal_count bigint;
    activity_count bigint;
    close_date_type text;
    created_at_type text;
BEGIN
    SELECT count(*) INTO deal_count FROM public.deals;
    SELECT count(*) INTO activity_count FROM public.activities;

    IF deal_count <> 4 OR activity_count <> 2 THEN
        RAISE EXCEPTION
            'Verification failed: expected 4 deals and 2 activities, found % deals and % activities',
            deal_count, activity_count;
    END IF;

    SELECT format_type(a.atttypid, a.atttypmod)
      INTO close_date_type
      FROM pg_attribute AS a
     WHERE a.attrelid = 'public.deals'::regclass
       AND a.attname = 'expected_close_date'
       AND a.attnum > 0
       AND NOT a.attisdropped;

    SELECT format_type(a.atttypid, a.atttypmod)
      INTO created_at_type
      FROM pg_attribute AS a
     WHERE a.attrelid = 'public.deals'::regclass
       AND a.attname = 'created_at'
       AND a.attnum > 0
       AND NOT a.attisdropped;

    IF close_date_type IS DISTINCT FROM 'date' THEN
        RAISE EXCEPTION
            'Verification failed: expected_close_date has type % instead of date',
            close_date_type;
    END IF;

    IF created_at_type IS DISTINCT FROM 'timestamp without time zone' THEN
        RAISE EXCEPTION
            'Verification failed: created_at was unexpectedly changed to %',
            created_at_type;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM public.deals
         WHERE deal_id IS NULL
            OR status IS NULL
            OR risk_score IS NULL
            OR risk_level IS NULL
            OR risk_reasons IS NULL
            OR recommended_action IS NULL
            OR updated_at IS NULL
    ) THEN
        RAISE EXCEPTION
            'Verification failed: one or more required deal fields remain NULL';
    END IF;

    IF (SELECT count(DISTINCT deal_id) FROM public.deals) <> deal_count THEN
        RAISE EXCEPTION
            'Verification failed: deal_id values are not unique';
    END IF;

    IF to_regclass('public.ix_deals_id') IS NULL
       OR to_regclass('public.ix_activities_id') IS NULL
       OR to_regclass('public.ix_deals_deal_id') IS NULL
       OR pg_get_serial_sequence('public.deals', 'id') IS NULL
       OR pg_get_serial_sequence('public.activities', 'id') IS NULL THEN
        RAISE EXCEPTION
            'Verification failed: expected indexes or owned ID sequences are missing';
    END IF;
END;
$verification$;

COMMIT;

-- created_at remains TIMESTAMP WITHOUT TIME ZONE by design.
-- After confirming whether its stored values mean UTC or Asia/Kolkata time,
-- perform a separately reviewed conversion:
--   UTC:        USING created_at AT TIME ZONE 'UTC'
--   Asia/Kolkata: USING created_at AT TIME ZONE 'Asia/Kolkata'
