# RevSignal system architecture

## Runtime shape

The current MVP uses a single FastAPI service backed by SQLite. The application stores deal records and calculates risk using a rule-based engine.

## Layers

- API layer: `/api/*` endpoints in `app/main.py`
- Data access: SQLAlchemy models in `app/models.py`
- Risk logic: `app/risk_engine.py`
- Recommendation logic: `app/recommendation_engine.py`
- CSV import: `app/data_import.py`
- UI: static dashboard in `app/static/index.html`
