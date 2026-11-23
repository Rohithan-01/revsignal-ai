# RevSignal system architecture

## Runtime shape

The current MVP uses a single FastAPI service backed by SQLite. The app stores deal records and computes risk using a transparent rule-based engine.

## Layers

- API layer: `backend/app/main.py`
- persistence: `backend/app/database.py` and `backend/app/models.py`
- CSV normalization: `backend/app/data_import.py`
- risk logic: `backend/app/risk_engine.py`
- recommendations: `backend/app/engine/recommendation_engine.py`
- legacy frontend: `backend/app/static/index.html`
