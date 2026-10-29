# RevSignal data dictionary

## Standard CRM fields

- `deal_id`: unique opportunity identifier
- `account_name`: account or customer name
- `deal_value`: value of the opportunity
- `stage`: pipeline stage
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
