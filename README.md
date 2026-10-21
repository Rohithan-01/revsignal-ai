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

frontend/
  app/                  # Next.js dashboard, deal views, import, recommendations
  components/           # Shared navigation, data access, tables, and UI
  lib/                  # Typed API client, formatting, and labelled demo data

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

Use Python 3.9 or newer. From the repository root, create and activate a virtual environment:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

On macOS or Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Then open:

- API docs: http://localhost:8000/docs

The app creates `revsignal.db` in the repository root by default. To use a different database location, set `DATABASE_URL` in the process environment before starting the app. No external services are required.

## Frontend

The responsive Next.js dashboard runs separately from the FastAPI service. Start the backend on port 8000, then in another terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open http://localhost:3000. The frontend uses `NEXT_PUBLIC_API_BASE_URL` from `frontend/.env.local` (default `http://localhost:8000`). The backend allows the local frontend origins by default; set `CORS_ORIGINS` to a comma-separated list if your frontend uses a different origin.

If the API cannot be reached, the interface explicitly switches to clearly labelled illustrative demo data. CSV import remains backend-only and will report an error rather than simulating a successful upload. The recommendations view reflects deal recommendations available from the analysis API; approval or execution is not implemented.

Frontend checks:

```powershell
cd frontend
npm test
npm run typecheck
npm run build
```

The frontend uses Next.js App Router, React, TypeScript, Tailwind CSS, Recharts, Lucide icons, and Framer Motion. Respect for reduced-motion preferences is built in.

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

Upload the included sample from the dashboard, or use the API:

```bash
curl -F "file=@data/sample_crm.csv" http://localhost:8000/api/deals/upload
```

## Notes and assumptions

This MVP intentionally uses a transparent, rule-based scoring model rather than claiming statistical model accuracy. Dashboard metrics are calculated from imported open deals.
