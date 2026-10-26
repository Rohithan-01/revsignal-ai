# Revsignal-ai
RevSignal is an AI-powered revenue copilot that detects deal risks, predicts sales outcomes, recommends next-best actions, and automates CRM workflows for B2B sales teams.

The current backend uses demo business rules rather than a trained model. Deal responses include an overall risk assessment based on three signals: probability below 30%, an overdue expected close date, and stale or inactive customer activity. Two or more risk signals produce HIGH risk, one produces MEDIUM risk, and none produce LOW risk. Deals without recorded activity are treated as having no recent activity; a missing expected close date is not considered overdue and is reported as unavailable.
