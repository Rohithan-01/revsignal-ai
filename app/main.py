from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.data_import import import_csv_records, synthetic_sample_rows
from app.database import Base, SessionLocal, engine
from app.models import Deal
from app.risk_engine import analyze_deal
from app.schemas import DealRead, MetricsResponse, UploadResponse

app = FastAPI(title="RevSignal", version="0.1.0")
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/")
def dashboard_root() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "RevSignal"}


def _deal_to_response(deal: Deal) -> DealRead:
    return DealRead(
        id=deal.id,
        deal_id=deal.deal_id,
        account_name=deal.account_name,
        deal_value=float(deal.deal_value),
        stage=deal.stage,
        status=deal.status,
        created_date=deal.created_date,
        expected_close_date=deal.expected_close_date,
        last_activity_date=deal.last_activity_date,
        activity_count=deal.activity_count,
        meeting_count=deal.meeting_count,
        email_count=deal.email_count,
        stakeholder_count=deal.stakeholder_count,
        risk_score=deal.risk_score,
        risk_level=deal.risk_level,
        risk_reasons=json.loads(deal.risk_reasons or "[]"),
        recommended_action=deal.recommended_action,
    )


def _upsert_deal(db, assessment: dict[str, object]) -> Deal:
    deal_id = str(assessment["deal_id"])
    existing = db.query(Deal).filter(Deal.deal_id == deal_id).first()
    if existing is not None:
        existing.account_name = str(assessment.get("account_name") or "Unknown account")
        existing.deal_value = float(assessment.get("deal_value") or 0)
        existing.stage = str(assessment.get("stage") or "Unknown")
        existing.status = str(assessment.get("status") or "open")
        existing.created_date = assessment.get("created_date")
        existing.expected_close_date = assessment.get("expected_close_date")
        existing.last_activity_date = assessment.get("last_activity_date")
        existing.activity_count = assessment.get("activity_count")
        existing.meeting_count = assessment.get("meeting_count")
        existing.email_count = assessment.get("email_count")
        existing.stakeholder_count = assessment.get("stakeholder_count")
        existing.risk_score = int(assessment.get("risk_score") or 0)
        existing.risk_level = str(assessment.get("risk_level") or "LOW")
        existing.risk_reasons = json.dumps(assessment.get("risk_reasons") or [])
        existing.recommended_action = str(assessment.get("recommended_action") or "")
        db.commit()
        db.refresh(existing)
        return existing

    new_deal = Deal(
        deal_id=deal_id,
        account_name=str(assessment.get("account_name") or "Unknown account"),
        deal_value=float(assessment.get("deal_value") or 0),
        stage=str(assessment.get("stage") or "Unknown"),
        status=str(assessment.get("status") or "open"),
        created_date=assessment.get("created_date"),
        expected_close_date=assessment.get("expected_close_date"),
        last_activity_date=assessment.get("last_activity_date"),
        activity_count=assessment.get("activity_count"),
        meeting_count=assessment.get("meeting_count"),
        email_count=assessment.get("email_count"),
        stakeholder_count=assessment.get("stakeholder_count"),
        risk_score=int(assessment.get("risk_score") or 0),
        risk_level=str(assessment.get("risk_level") or "LOW"),
        risk_reasons=json.dumps(assessment.get("risk_reasons") or []),
        recommended_action=str(assessment.get("recommended_action") or ""),
    )
    db.add(new_deal)
    db.commit()
    db.refresh(new_deal)
    return new_deal


@app.post("/api/deals/upload", response_model=UploadResponse)
def upload_deals(file: UploadFile = File(...)) -> UploadResponse:
    try:
        imported = import_csv_records(file.file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with SessionLocal() as db:
        for record in imported:
            _upsert_deal(db, record)

    return UploadResponse(
        success=True,
        message=f"Imported {len(imported)} deals from the uploaded file.",
        records_imported=len(imported),
    )


@app.get("/api/deals", response_model=list[DealRead])
def list_deals(
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    stage: Optional[str] = None,
):
    with SessionLocal() as db:
        query = db.query(Deal)
        if status:
            query = query.filter(Deal.status.ilike(status))
        if risk_level:
            query = query.filter(Deal.risk_level.ilike(risk_level))
        if stage:
            query = query.filter(Deal.stage.ilike(stage))
        deals = query.order_by(Deal.risk_score.desc(), Deal.deal_value.desc()).all()
        return [_deal_to_response(deal) for deal in deals]


@app.get("/api/deals/high-risk", response_model=list[DealRead])
def list_high_risk_deals() -> list[DealRead]:
    with SessionLocal() as db:
        deals = (
            db.query(Deal)
            .filter(Deal.status == "open", Deal.risk_level == "HIGH")
            .order_by(Deal.risk_score.desc())
            .all()
        )
        return [_deal_to_response(deal) for deal in deals]


@app.get("/api/deals/{deal_id}", response_model=DealRead)
def get_deal(deal_id: str):
    with SessionLocal() as db:
        deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
        if deal is None:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id} was not found.")
        return _deal_to_response(deal)


@app.get("/api/metrics", response_model=MetricsResponse)
def get_metrics() -> MetricsResponse:
    with SessionLocal() as db:
        deals = db.query(Deal).all()
        open_deals = [deal for deal in deals if str(deal.status).lower() in {"open", "active", "pipeline", "qualified", "proposal", "negotiation", "discovery", "in_progress"}]

        total_open_pipeline_value = sum(float(deal.deal_value) for deal in open_deals)
        high_risk_deals = [deal for deal in open_deals if deal.risk_level == "HIGH"]
        revenue_high_risk = sum(float(deal.deal_value) for deal in high_risk_deals)
        deals_needing_attention = sum(1 for deal in open_deals if deal.risk_level in {"HIGH", "MEDIUM"})

        risk_distribution = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
        for deal in open_deals:
            level = str(deal.risk_level).upper()
            risk_distribution[level] = risk_distribution.get(level, 0) + 1

        pipeline_value_by_stage: dict[str, float] = {}
        for deal in open_deals:
            stage = deal.stage
            pipeline_value_by_stage[stage] = pipeline_value_by_stage.get(stage, 0.0) + float(deal.deal_value)

        top_deals = sorted(open_deals, key=lambda deal: deal.risk_score, reverse=True)[:10]
        return MetricsResponse(
            total_open_pipeline_value=round(total_open_pipeline_value, 2),
            revenue_high_risk=round(revenue_high_risk, 2),
            high_risk_deals=len(high_risk_deals),
            deals_needing_attention=deals_needing_attention,
            deal_distribution_by_risk=risk_distribution,
            pipeline_value_by_stage={key: round(value, 2) for key, value in pipeline_value_by_stage.items()},
            top_deals=[_deal_to_response(deal).model_dump() for deal in top_deals],
        )


@app.post("/api/deals/{deal_id}/analyze", response_model=DealRead)
def analyze_deal_endpoint(deal_id: str):
    with SessionLocal() as db:
        deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
        if deal is None:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id} was not found.")

        record = {
            "deal_id": deal.deal_id,
            "account_name": deal.account_name,
            "deal_value": deal.deal_value,
            "stage": deal.stage,
            "status": deal.status,
            "created_date": deal.created_date,
            "expected_close_date": deal.expected_close_date,
            "last_activity_date": deal.last_activity_date,
            "activity_count": deal.activity_count,
            "meeting_count": deal.meeting_count,
            "email_count": deal.email_count,
            "stakeholder_count": deal.stakeholder_count,
        }
        assessment = analyze_deal(record)
        deal.risk_score = assessment["risk_score"]
        deal.risk_level = assessment["risk_level"]
        deal.risk_reasons = json.dumps(assessment["risk_reasons"])
        deal.recommended_action = assessment["recommended_action"]
        db.commit()
        db.refresh(deal)
        return _deal_to_response(deal)


@app.get("/seed/sample")
def seed_sample_data() -> dict:
    with SessionLocal() as db:
        for row in synthetic_sample_rows():
            assessment = analyze_deal(row)
            _upsert_deal(db, assessment)

    return {"message": "Seed data loaded successfully.", "records_imported": len(synthetic_sample_rows())}
