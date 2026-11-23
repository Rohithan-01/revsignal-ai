# Business deal ID migration

Business IDs use `D-` followed by a positive integer. The confirmed mapping is:

| Internal `deals.id` | Company | Previous `deal_id` | New `deal_id` |
|---:|---|---|---|
| 1 | TechNova Solutions | `legacy-1` | `D-101` |
| 2 | Zenith Technologies | `legacy-2` | `D-102` |
| 3 | BlueWave Solutions | `legacy-3` | `D-103` |
| 4 | PixelCore Systems | `legacy-4` | `D-104` |
| 5 | Northwind Labs | `D-1001` | `D-105` |
| 6 | Harbor Retail | `D-1002` | `D-106` |
| 7 | Apex Manufacturing | `D-1003` | `D-107` |
| 8 | Meridian Health | `D-1004` | `D-108` |
| 9 | Velora Systems | `D-1005` | `D-109` |
| 10 | Summit Legal | `D-1006` | `D-110` |
| 11 | BluePeak Financial | `D-1007` | `D-111` |
| 12 | Greenline Logistics | `D-1008` | `D-112` |

Before applying the migration, take a database backup and verify that the
database contains exactly these 12 rows. From the repository root, an operator
may run the guarded migration with:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/manual/0004_standardize_deal_ids.sql
```

The script runs in a transaction and aborts unless each internal ID, company,
and old business ID matches the confirmed mapping. It only updates
`public.deals.deal_id`; internal primary keys and activity foreign keys remain
unchanged. Do not apply it to a database with additional or changed rows.

To roll back, first confirm the database still matches the migrated mapping,
then run:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/manual/rollback_0004_standardize_deal_ids.sql
```

The rollback script is also transactional and restores the exact former
`deal_id` values. It aborts rather than overwriting rows if the current data
does not match its preconditions. Existing URLs that contain old business IDs
will need to use the new IDs after migration.

Application-generated IDs continue after the highest existing numeric suffix;
with the migrated data, the next new ID is `D-113`. CRM CSV uploads preserve
canonical IDs and reject duplicates, while `/seed/sample` retains its existing
upsert behavior.
