# RevSignal data dictionary

## Standard CRM fields

- `deal_id`: unique business identifier in the canonical `D-<positive integer>` format
- `id`: internal integer deal primary key; activity foreign keys reference this field
- `account_name`: account or customer name
- `deal_value`: value of the opportunity
- `stage`: pipeline stage
- `probability`: numeric closing probability; defaults to 50 for compatibility
- `probability_is_known`: whether the probability was explicitly supplied or verified
- `created_date`: when the deal entered the pipeline
- `expected_close_date`: target close date
- `last_activity_date`: most recent customer or internal touchpoint
- `activity_count`: number of recorded activities
- `meeting_count`: number of meetings
- `email_count`: number of customer email touches
- `stakeholder_count`: size of the buying group
- `status`: open, won, or lost

## Derived values

- `risk_score`: integer score from 0 to 100
- `risk_level`: LOW, MEDIUM, or HIGH
- `risk_reasons`: evidence for the risk score
- `recommended_action`: deterministic action recommendation

New business IDs continue after the highest existing numeric suffix. The
current 12-deal mapping and guarded manual migration/rollback are documented in
[deal-id-migration.md](./deal-id-migration.md).

The numeric `probability` value is retained even when its provenance is unknown.
Unknown probabilities are not used in risk classification. Existing records are
marked unknown by `0003_track_probability_provenance.sql`; the migration does not
change their numeric probability values.
