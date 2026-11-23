BEGIN;

LOCK TABLE public.deals IN ACCESS EXCLUSIVE MODE;

DO $precondition$
DECLARE
    deal_count bigint;
BEGIN
    SELECT count(*) INTO deal_count FROM public.deals;
    IF deal_count <> 12 THEN
        RAISE EXCEPTION
            'Deal ID rollback aborted: expected exactly 12 deals, found %',
            deal_count;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM (VALUES
              (1, 'D-101', 'legacy-1', 'TechNova Solutions'),
              (2, 'D-102', 'legacy-2', 'Zenith Technologies'),
              (3, 'D-103', 'legacy-3', 'BlueWave Solutions'),
              (4, 'D-104', 'legacy-4', 'PixelCore Systems'),
              (5, 'D-105', 'D-1001', 'Northwind Labs'),
              (6, 'D-106', 'D-1002', 'Harbor Retail'),
              (7, 'D-107', 'D-1003', 'Apex Manufacturing'),
              (8, 'D-108', 'D-1004', 'Meridian Health'),
              (9, 'D-109', 'D-1005', 'Velora Systems'),
              (10, 'D-110', 'D-1006', 'Summit Legal'),
              (11, 'D-111', 'D-1007', 'BluePeak Financial'),
              (12, 'D-112', 'D-1008', 'Greenline Logistics')
          ) AS expected(id, new_deal_id, old_deal_id, company)
          LEFT JOIN public.deals AS d ON d.id = expected.id
         WHERE d.id IS NULL
            OR d.deal_id IS DISTINCT FROM expected.new_deal_id
            OR d.company IS DISTINCT FROM expected.company
    ) THEN
        RAISE EXCEPTION
            'Deal ID rollback aborted: the database does not match the expected migrated mapping';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM public.deals AS d
         WHERE d.id NOT BETWEEN 1 AND 12
           AND d.deal_id IN (
               'legacy-1', 'legacy-2', 'legacy-3', 'legacy-4',
               'D-1001', 'D-1002', 'D-1003', 'D-1004',
               'D-1005', 'D-1006', 'D-1007', 'D-1008'
           )
    ) THEN
        RAISE EXCEPTION
            'Deal ID rollback aborted: an old deal ID is already used by an unexpected row';
    END IF;
END;
$precondition$;

UPDATE public.deals AS d
   SET deal_id = expected.old_deal_id
  FROM (VALUES
      (1, 'D-101', 'legacy-1', 'TechNova Solutions'),
      (2, 'D-102', 'legacy-2', 'Zenith Technologies'),
      (3, 'D-103', 'legacy-3', 'BlueWave Solutions'),
      (4, 'D-104', 'legacy-4', 'PixelCore Systems'),
      (5, 'D-105', 'D-1001', 'Northwind Labs'),
      (6, 'D-106', 'D-1002', 'Harbor Retail'),
      (7, 'D-107', 'D-1003', 'Apex Manufacturing'),
      (8, 'D-108', 'D-1004', 'Meridian Health'),
      (9, 'D-109', 'D-1005', 'Velora Systems'),
      (10, 'D-110', 'D-1006', 'Summit Legal'),
      (11, 'D-111', 'D-1007', 'BluePeak Financial'),
      (12, 'D-112', 'D-1008', 'Greenline Logistics')
  ) AS expected(id, new_deal_id, old_deal_id, company)
 WHERE d.id = expected.id;

DO $postcondition$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM (VALUES
              (1, 'legacy-1', 'TechNova Solutions'),
              (2, 'legacy-2', 'Zenith Technologies'),
              (3, 'legacy-3', 'BlueWave Solutions'),
              (4, 'legacy-4', 'PixelCore Systems'),
              (5, 'D-1001', 'Northwind Labs'),
              (6, 'D-1002', 'Harbor Retail'),
              (7, 'D-1003', 'Apex Manufacturing'),
              (8, 'D-1004', 'Meridian Health'),
              (9, 'D-1005', 'Velora Systems'),
              (10, 'D-1006', 'Summit Legal'),
              (11, 'D-1007', 'BluePeak Financial'),
              (12, 'D-1008', 'Greenline Logistics')
          ) AS expected(id, deal_id, company)
          LEFT JOIN public.deals AS d ON d.id = expected.id
         WHERE d.id IS NULL
            OR d.deal_id IS DISTINCT FROM expected.deal_id
            OR d.company IS DISTINCT FROM expected.company
    ) THEN
        RAISE EXCEPTION
            'Deal ID rollback failed: restored rows do not match the original mapping';
    END IF;
END;
$postcondition$;

COMMIT;
