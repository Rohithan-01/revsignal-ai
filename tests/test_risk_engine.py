# RevSignal data dictionary

## Required standard fields

- `deal_id`: unique identifier for the opportunity
- `account_name`: customer or account name
- `deal_value`: value of the open opportunity in USD
- `stage`: sales stage such as Discovery, Qualified, Proposal, or Negotiation
- `created_date`: when the deal entered the pipeline
- `expected_close_date`: date the deal is expected to close
- `last_activity_date`: most recent customer or internal activity date
- `activity_count`: total activity count available in the source system
- `meeting_count`: number of meetings or customer conversations
- `email_count`: number of customer emails or touchpoints
- `stakeholder_count`: number of decision-makers involved
- `status`: open, won, or lost

## Derived values

The service derives:

- `risk_score`: 0-100
- `risk_level`: LOW, MEDIUM, or HIGH
- `risk_reasons`: explainable evidence used in the score
- `recommended_action`: deterministic next step
