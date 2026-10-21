# RevSignal

RevSignal is an AI-powered revenue copilot that identifies risky deals, explains why they are risky, recommends next-best actions, and surfaces a clean B2B sales dashboard for pipeline management.

## Overview

This repository implements a foundational Python FastAPI MVP for the core product flow:

- CSV upload and normalization
- validation for malformed and incomplete CRM records
- rule-based explainable deal risk scoring
- deterministic next-best actions
- dashboard metrics based on imported deal data

## Repository structure

```text
app/
  data_import.py
  database.py
  main.py
  models.py
  recommendation_engine.py
  risk_engine.py
  static/index.html

data/
  sample_crm.csv

docs/
  product-requirements.md
  system-architecture.md
  data-dictionary.md

tests/
  test_data_import.py
  test_risk_engine.py
```

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open:

- API docs: http://localhost:8000/docs
- Dashboard: http://localhost:8000/

## Environment

Use the provided example config if needed:

```bash
cp .env.example .env
```

The default configuration uses SQLite at the repository root as `revsignal.db`.

## Sample data

The repo includes `data/sample_crm.csv`, a clearly labelled synthetic CRM dataset for local development.

## API endpoints

- `GET /health`
- `POST /api/deals/upload`
- `GET /api/deals`
- `GET /api/deals/{deal_id}`
- `GET /api/deals/high-risk`
- `GET /api/metrics`
- `POST /api/deals/{deal_id}/analyze`
- `GET /seed/sample`

## Notes and assumptions

This MVP intentionally uses a transparent, rule-based scoring model rather than claiming statistical model accuracy. It is built to be easy to evolve later with historical outcomes and ML-based prediction workflows.
