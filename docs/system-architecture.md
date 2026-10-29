# RevSignal system architecture

## Runtime shape

The current MVP uses a single FastAPI service backed by SQLite. The app stores deal records and computes risk using a transparent rule-based engine.

## Layers

- API layer: `app/main.py`
- persistence: `app/database.py` and `app/models.py`
- CSV normalization: `app/data_import.py`
- risk logic: `app/risk_engine.py`
- recommendations: `app/recommendation_engine.py`
- frontend: `app/static/index.html`
