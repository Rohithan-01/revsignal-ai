# RevSignal

RevSignal is a prototype B2B sales deal risk assessment API and dashboard. Its
assessments use explainable rule-based scoring; the project does not claim to
use a trained machine-learning model or a live CRM integration.

The backend supports deal creation and retrieval, activity tracking, calendar
date-based overdue checks in the demo business timezone (`Asia/Kolkata`),
activity-age signals, recommendations, and CSV import. Activity timestamps
are timezone-aware instants normalized to UTC. The dashboard adds normalized
CRM CSV import, deal filters, pipeline metrics, risk explanations, and
recommended actions.

## Repository structure

```text
app/
  data_import.py
  database.py
  main.py
  models.py
  risk_engine.py
  engine/
  static/index.html
frontend/
  app/
  components/
  lib/
data/
  sample_crm.csv
docs/
tests/
```

## Backend setup

Use Python 3.10 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload
```

The backend defaults to a local SQLite database. Set `DATABASE_URL` in the
process environment to use another database. Startup creates missing tables;
`create_all()` does not update existing table schemas, so existing databases
may require an explicit migration before use.

## Frontend setup

With the backend running, use another terminal:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Open http://localhost:3000. The frontend defaults to the local backend at
`http://localhost:8000`. Configure `CORS_ORIGINS` if the frontend uses a
different origin. If the API is unavailable, the dashboard clearly labels
illustrative demo data rather than presenting it as live data.

Frontend checks:

```powershell
npm test
npm run typecheck
npm run build
```

## API endpoints

Core deal/activity API:

- `GET /health`
- `POST /deals`
- `GET /deals`
- `GET /deals/{deal_id}`
- `POST /deals/import-csv`
- `POST /activities`
- `GET /activities`
- `GET /deals/{deal_id}/activities`
- `GET /deals/{deal_id}/activity-signal`

Dashboard API:

- `POST /api/deals/upload`
- `GET /api/deals`
- `GET /api/deals/{deal_id}`
- `GET /api/deals/high-risk`
- `GET /api/metrics`
- `POST /api/deals/{deal_id}/analyze`
- `GET /seed/sample`

The repository includes synthetic sample CRM data at `data/sample_crm.csv`.
The dashboard import recognizes common CRM header aliases and requires a
deal ID, account name, deal value, and stage. Re-uploading an existing deal
ID updates that imported deal.

## Deployment and documentation

Deployment configuration is provided in `render.yaml` and `vercel.json`.
See [docs/deployment.md](docs/deployment.md) for deployment assumptions and
database-persistence limitations. Product and schema notes are in the
`docs/` directory.
