# RevSignal

RevSignal is an AI-powered revenue copilot that detects deal risks, predicts sales outcomes, recommends next-best actions, and automates CRM workflows for B2B sales teams.

## Overview

This repository begins as a lightweight Python MVP for the core product flow:

- CSV upload and normalization
- Deal validation
- Rule-based risk scoring
- Action recommendations
- Dashboard metrics and drill-down detail views

The project intentionally keeps the initial implementation explainable and deterministic. It does not require paid APIs or external CRM credentials to run locally.

## Repository structure

- `app/` — FastAPI application, risk engine, CSV importer, and static dashboard
- `data/` — sample CRM dataset for local development
- `docs/` — product and data documentation
- `tests/` — validation and risk-scoring tests

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

Create a local environment file if needed:

```bash
cp .env.example .env
```

The default configuration uses a local SQLite database file.

## Sample data

A sample CRM dataset is included in `data/sample_crm.csv`. Upload it through the dashboard or via the API.

## API endpoints

- `GET /health`
- `POST /api/deals/upload`
- `GET /api/deals`
- `GET /api/deals/{deal_id}`
- `GET /api/deals/high-risk`
- `GET /api/metrics`
- `POST /api/deals/{deal_id}/analyze`

## Notes

This MVP is intentionally rule-based and transparent. It is designed to support future ML or LLM-powered extensions without exposing them in the initial product flow.
