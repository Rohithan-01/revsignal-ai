BEGIN;

LOCK TABLE public.deals IN ACCESS EXCLUSIVE MODE;

DO $precondition$
DECLARE
    deal_count bigint;
BEGIN
    SELECT count(*) INTO deal_count FROM public.deals;
    IF deal_count <> 12 THEN
        RAISE EXCEPTION
            'Deal ID migration aborted: expected exactly 12 deals, found %',
            deal_count;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM (VALUES
              (1, 'legacy-1', 'D-101', 'TechNova Solutions'),
              (2, 'legacy-2', 'D-102', 'Zenith Technologies'),
              (3, 'legacy-3', 'D-103', 'BlueWave Solutions'),
              (4, 'legacy-4', 'D-104', 'PixelCore Systems'),
              (5, 'D-1001', 'D-105', 'Northwind Labs'),
              (6, 'D-1002', 'D-106', 'Harbor Retail'),
              (7, 'D-1003', 'D-107', 'Apex Manufacturing'),
              (8, 'D-1004', 'D-108', 'Meridian Health'),
              (9, 'D-1005', 'D-109', 'Velora Systems'),
              (10, 'D-1006', 'D-110', 'Summit Legal'),
              (11, 'D-1007', 'D-111', 'BluePeak Financial'),
              (12, 'D-1008', 'D-112', 'Greenline Logistics')
          ) AS expected(id, old_deal_id, new_deal_id, company)
          LEFT JOIN public.deals AS d ON d.id = expected.id
         WHERE d.id IS NULL
            OR d.deal_id IS DISTINCT FROM expected.old_deal_id
            OR d.company IS DISTINCT FROM expected.company
    ) THEN
        RAISE EXCEPTION
            'Deal ID migration aborted: the database does not match the confirmed starting mapping';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM public.deals AS d
         WHERE d.id NOT BETWEEN 1 AND 12
           AND d.deal_id IN (
               'D-101', 'D-102', 'D-103', 'D-104',
               'D-105', 'D-106', 'D-107', 'D-108',
               'D-109', 'D-110', 'D-111', 'D-112'
           )
    ) THEN
        RAISE EXCEPTION
            'Deal ID migration aborted: a target deal ID is already used by an unexpected row';
    END IF;
END;
$precondition$;

UPDATE public.deals AS d
   SET deal_id = expected.new_deal_id
  FROM (VALUES
      (1, 'legacy-1', 'D-101', 'TechNova Solutions'),
      (2, 'legacy-2', 'D-102', 'Zenith Technologies'),
      (3, 'legacy-3', 'D-103', 'BlueWave Solutions'),
      (4, 'legacy-4', 'D-104', 'PixelCore Systems'),
      (5, 'D-1001', 'D-105', 'Northwind Labs'),
      (6, 'D-1002', 'D-106', 'Harbor Retail'),
      (7, 'D-1003', 'D-107', 'Apex Manufacturing'),
      (8, 'D-1004', 'D-108', 'Meridian Health'),
      (9, 'D-1005', 'D-109', 'Velora Systems'),
      (10, 'D-1006', 'D-110', 'Summit Legal'),
      (11, 'D-1007', 'D-111', 'BluePeak Financial'),
      (12, 'D-1008', 'D-112', 'Greenline Logistics')
  ) AS expected(id, old_deal_id, new_deal_id, company)
 WHERE d.id = expected.id;

DO $postcondition$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM (VALUES
              (1, 'D-101', 'TechNova Solutions'),
              (2, 'D-102', 'Zenith Technologies'),
              (3, 'D-103', 'BlueWave Solutions'),
              (4, 'D-104', 'PixelCore Systems'),
              (5, 'D-105', 'Northwind Labs'),
              (6, 'D-106', 'Harbor Retail'),
              (7, 'D-107', 'Apex Manufacturing'),
              (8, 'D-108', 'Meridian Health'),
              (9, 'D-109', 'Velora Systems'),
              (10, 'D-110', 'Summit Legal'),
              (11, 'D-111', 'BluePeak Financial'),
              (12, 'D-112', 'Greenline Logistics')
          ) AS expected(id, deal_id, company)
          LEFT JOIN public.deals AS d ON d.id = expected.id
         WHERE d.id IS NULL
            OR d.deal_id IS DISTINCT FROM expected.deal_id
            OR d.company IS DISTINCT FROM expected.company
    ) THEN
        RAISE EXCEPTION
            'Deal ID migration failed: updated rows do not match the target mapping';
    END IF;
END;
$postcondition$;

COMMIT;
