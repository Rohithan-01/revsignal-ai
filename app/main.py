from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.data_import import import_csv_records, synthetic_sample_rows
from app.database import Base, SessionLocal, engine
from app.engine.activity_engine import (
    calculate_activity_signal,
    get_activity_status,
    get_latest_activity_date,
)
from app.engine.recommendation_engine import generate_recommendation
from app.engine.risk_engine import (
    DEMO_BUSINESS_TIMEZONE,
    calculate_overall_risk,
    calculate_risk,
    is_deal_overdue,
)
from app.models import Activity, Deal
from app.risk_engine import analyze_deal
from app.schemas import (
    ActivityCreate,
    ActivityResponse,
    DealCreate,
    DealDetailResponse,
    DealRead,
    DealResponse,
    MetricsResponse,
    UploadResponse,
)

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
async def startup() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(
    request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    if isinstance(exc, IntegrityError):
        return JSONResponse(
            status_code=409,
            content={"detail": "Database constraint violation"},
        )

    if isinstance(exc, DBAPIError) and exc.connection_invalidated:
        return JSONResponse(
            status_code=503,
            content={"detail": "Database is temporarily unavailable"},
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Database operation failed"},
    )


@app.get("/")
def dashboard_root() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "RevSignal"}


async def seed_deals() -> dict[str, object]:
    today = datetime.now(ZoneInfo(DEMO_BUSINESS_TIMEZONE)).date()
    deals = [
        Deal(
            company=company,
            deal_value=value,
            stage=stage,
            probability=probability,
            expected_close_date=today + timedelta(days=days),
        )
        for company, value, stage, probability, days in (
            ("Acme Corp", 50000, "Negotiation", 70, 15),
            ("TechNova", 25000, "Proposal", 40, 30),
            ("DataFlow", 80000, "Qualified", 60, 45),
            ("CloudPeak", 120000, "Negotiation", 80, 10),
            ("NextGen Solutions", 35000, "Discovery", 25, 60),
        )
    ]
    async with SessionLocal() as session:
        session.add_all(deals)
        await session.commit()
    return {"message": "Dummy deals created", "count": len(deals)}


def register_seed_endpoint(application: FastAPI) -> None:
    if os.getenv("ENABLE_SEED_ENDPOINT", "").strip().lower() == "true":
        application.post("/seed/deals")(seed_deals)


register_seed_endpoint(app)


def _legacy_deal_response(deal: Deal) -> dict[str, object]:
    is_overdue = is_deal_overdue(
        deal.expected_close_date,
        DEMO_BUSINESS_TIMEZONE,
    )
    activity_status = get_activity_status(None)
    overall_risk_level, risk_reasons = calculate_overall_risk(
        deal.probability,
        is_overdue,
        activity_status,
        has_expected_close_date=deal.expected_close_date is not None,
    )
    return {
        "id": deal.id,
        "company": deal.company,
        "deal_value": deal.deal_value,
        "stage": deal.stage,
        "probability": deal.probability,
        "risk_level": calculate_risk(deal.probability),
        "overall_risk_level": overall_risk_level,
        "risk_reasons": risk_reasons,
        "is_overdue": is_overdue,
        "activity_status": activity_status,
        "days_since_last_activity": None,
        "recommendation": generate_recommendation(
            overall_risk_level,
            is_overdue,
        ),
        "expected_close_date": deal.expected_close_date,
        "created_at": deal.created_at,
    }


@app.get("/deals", response_model=list[DealResponse])
async def get_deals() -> list[dict[str, object]]:
    async with SessionLocal() as session:
        result = await session.execute(select(Deal))
        deals = result.scalars().all()
        activity_result = await session.execute(
            select(Activity.deal_id, Activity.activity_date).order_by(
                Activity.activity_date.desc()
            )
        )
        activity_dates_by_deal: dict[int, list[datetime]] = {}
        for deal_id, activity_date in activity_result.all():
            activity_dates_by_deal.setdefault(deal_id, []).append(activity_date)

    response = []
    for deal in deals:
        activity_dates = activity_dates_by_deal.get(deal.id, [])
        days_since_last_activity = calculate_activity_signal(activity_dates)
        activity_status = get_activity_status(days_since_last_activity)
        is_overdue = is_deal_overdue(
            deal.expected_close_date,
            DEMO_BUSINESS_TIMEZONE,
        )
        overall_risk_level, risk_reasons = calculate_overall_risk(
            deal.probability,
            is_overdue,
            activity_status,
            has_expected_close_date=deal.expected_close_date is not None,
        )
        response.append({
            "id": deal.id,
            "company": deal.company,
            "deal_value": deal.deal_value,
            "stage": deal.stage,
            "probability": deal.probability,
            "risk_level": calculate_risk(deal.probability),
            "overall_risk_level": overall_risk_level,
            "risk_reasons": risk_reasons,
            "is_overdue": is_overdue,
            "activity_status": activity_status,
            "days_since_last_activity": days_since_last_activity,
            "recommendation": generate_recommendation(
                overall_risk_level,
                is_overdue,
            ),
            "expected_close_date": deal.expected_close_date,
            "created_at": deal.created_at,
        })
    return response


@app.get("/deals/{deal_id}", response_model=DealDetailResponse)
async def get_deal(deal_id: int) -> dict[str, object]:
    async with SessionLocal() as session:
        deal = await session.get(Deal, deal_id)
        if deal is None:
            raise HTTPException(status_code=404, detail="Deal not found")
        result = await session.execute(
            select(Activity).where(Activity.deal_id == deal_id)
        )
        activities = result.scalars().all()

    activity_dates = [activity.activity_date for activity in activities]
    latest_activity_date = get_latest_activity_date(activity_dates)
    days_since_last_activity = calculate_activity_signal(activity_dates)
    activity_status = get_activity_status(days_since_last_activity)
    is_overdue = is_deal_overdue(
        deal.expected_close_date,
        DEMO_BUSINESS_TIMEZONE,
    )
    overall_risk_level, risk_reasons = calculate_overall_risk(
        deal.probability,
        is_overdue,
        activity_status,
        has_expected_close_date=deal.expected_close_date is not None,
    )
    return {
        **_legacy_deal_response(deal),
        "overall_risk_level": overall_risk_level,
        "risk_reasons": risk_reasons,
        "activity_status": activity_status,
        "days_since_last_activity": days_since_last_activity,
        "recommendation": generate_recommendation(
            overall_risk_level,
            is_overdue,
        ),
        "latest_activity_date": latest_activity_date,
        "activities": activities,
    }


@app.post("/deals", response_model=DealResponse)
async def create_deal(deal: DealCreate) -> dict[str, object]:
    new_deal = Deal(
        company=deal.company,
        deal_value=deal.deal_value,
        stage=deal.stage,
        probability=deal.probability,
        expected_close_date=deal.expected_close_date,
    )
    async with SessionLocal() as session:
        session.add(new_deal)
        await session.commit()
        await session.refresh(new_deal)
    return _legacy_deal_response(new_deal)


@app.post("/deals/import-csv")
async def import_deals_csv(file: UploadFile = File(...)) -> dict[str, object]:
    import csv
    import io

    expected_headers = {
        "company",
        "deal_value",
        "stage",
        "probability",
        "expected_close_date",
    }
    try:
        contents = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="CSV file must use UTF-8 encoding",
        ) from exc

    reader = csv.reader(io.StringIO(contents, newline=""), strict=True)
    try:
        headers = next(reader, None)
        if headers is None:
            raise HTTPException(status_code=400, detail="CSV row 1: missing header row")
        missing_headers = expected_headers - set(headers)
        unexpected_headers = set(headers) - expected_headers
        if missing_headers or unexpected_headers or len(headers) != len(expected_headers):
            details = []
            if missing_headers:
                details.append(f"missing columns: {', '.join(sorted(missing_headers))}")
            if unexpected_headers:
                details.append(
                    f"unexpected columns: {', '.join(sorted(unexpected_headers))}"
                )
            if not details:
                details.append("duplicate column names")
            raise HTTPException(
                status_code=400,
                detail=f"CSV row 1: invalid headers ({'; '.join(details)})",
            )

        validated_deals = []
        row_errors = []
        for row_number, values in enumerate(reader, start=2):
            if not values:
                continue
            if len(values) != len(headers):
                row_errors.append(
                    f"row {row_number}: expected {len(headers)} columns, "
                    f"received {len(values)}"
                )
                continue
            row = dict(zip(headers, values))
            close_date = row["expected_close_date"].strip()
            if not close_date:
                row["expected_close_date"] = None
            else:
                try:
                    row["expected_close_date"] = date.fromisoformat(close_date)
                except ValueError:
                    pass
            try:
                validated_deals.append(DealCreate.model_validate(row))
            except ValidationError as exc:
                for error in exc.errors():
                    location = ".".join(str(part) for part in error["loc"])
                    row_errors.append(
                        f"row {row_number}, {location}: {error['msg']}"
                    )
    except csv.Error as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Malformed CSV near row {reader.line_num}: {exc}",
        ) from exc

    if row_errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "CSV validation failed", "errors": row_errors},
        )

    new_deals = [
        Deal(
            company=deal.company,
            deal_value=deal.deal_value,
            stage=deal.stage,
            probability=deal.probability,
            expected_close_date=deal.expected_close_date,
        )
        for deal in validated_deals
    ]
    async with SessionLocal() as session:
        try:
            session.add_all(new_deals)
            await session.flush()
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            raise

    response_deals = []
    for deal in new_deals:
        response = _legacy_deal_response(deal)
        response["activity_status"] = get_activity_status(None)
        response_deals.append(response)
    return {"count": len(response_deals), "deals": response_deals}


@app.post("/activities", response_model=ActivityResponse)
async def create_activity(activity: ActivityCreate) -> Activity:
    async with SessionLocal() as session:
        deal = await session.get(Deal, activity.deal_id)
        if deal is None:
            raise HTTPException(status_code=404, detail="Deal not found")
        new_activity = Activity(
            deal_id=activity.deal_id,
            activity_type=activity.activity_type,
            activity_date=activity.activity_date,
            notes=activity.notes,
        )
        session.add(new_activity)
        await session.commit()
        await session.refresh(new_activity)
        return new_activity


@app.get("/activities", response_model=list[ActivityResponse])
async def get_activities() -> list[Activity]:
    async with SessionLocal() as session:
        result = await session.execute(select(Activity))
        return result.scalars().all()


@app.get("/deals/{deal_id}/activities", response_model=list[ActivityResponse])
async def get_deal_activities(deal_id: int) -> list[Activity]:
    async with SessionLocal() as session:
        deal = await session.get(Deal, deal_id)
        if deal is None:
            raise HTTPException(status_code=404, detail="Deal not found")
        result = await session.execute(
            select(Activity).where(Activity.deal_id == deal_id)
        )
        return result.scalars().all()


@app.get("/deals/{deal_id}/activity-signal")
async def get_activity_signal(deal_id: int) -> dict[str, object]:
    async with SessionLocal() as session:
        deal = await session.get(Deal, deal_id)
        if deal is None:
            raise HTTPException(status_code=404, detail="Deal not found")
        result = await session.execute(
            select(Activity).where(Activity.deal_id == deal_id)
        )
        activities = result.scalars().all()
    activity_dates = [activity.activity_date for activity in activities]
    days_since_last_activity = calculate_activity_signal(activity_dates)
    return {
        "deal_id": deal_id,
        "days_since_last_activity": days_since_last_activity,
        "activity_status": get_activity_status(days_since_last_activity),
    }


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


async def _upsert_deal(session, assessment: dict[str, object]) -> Deal:
    deal_id = str(assessment["deal_id"])
    result = await session.execute(
        select(Deal).where(Deal.deal_id == deal_id)
    )
    deal = result.scalar_one_or_none()
    values = {
        "company": str(assessment.get("account_name") or "Unknown account"),
        "deal_value": float(assessment.get("deal_value") or 0),
        "stage": str(assessment.get("stage") or "Unknown"),
        "status": str(assessment.get("status") or "open"),
        "probability": float(assessment.get("probability") or 50),
        "created_date": assessment.get("created_date"),
        "expected_close_date": assessment.get("expected_close_date"),
        "last_activity_date": assessment.get("last_activity_date"),
        "activity_count": assessment.get("activity_count"),
        "meeting_count": assessment.get("meeting_count"),
        "email_count": assessment.get("email_count"),
        "stakeholder_count": assessment.get("stakeholder_count"),
        "risk_score": int(assessment.get("risk_score") or 0),
        "risk_level": str(assessment.get("risk_level") or "LOW"),
        "risk_reasons": json.dumps(assessment.get("risk_reasons") or []),
        "recommended_action": str(assessment.get("recommended_action") or ""),
    }
    if deal is None:
        deal = Deal(deal_id=deal_id, **values)
        session.add(deal)
    else:
        for key, value in values.items():
            setattr(deal, key, value)
    return deal


@app.post("/api/deals/upload", response_model=UploadResponse)
async def upload_deals(file: UploadFile = File(...)) -> UploadResponse:
    try:
        imported = import_csv_records(file.file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    async with SessionLocal() as session:
        try:
            for record in imported:
                assessment = analyze_deal(record)
                await _upsert_deal(session, assessment)
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            raise
    return UploadResponse(
        success=True,
        message=f"Imported {len(imported)} deals from the uploaded file.",
        records_imported=len(imported),
    )


@app.get("/api/deals", response_model=list[DealRead])
async def list_deals(
    status: str | None = None,
    risk_level: str | None = None,
    stage: str | None = None,
) -> list[DealRead]:
    statement = select(Deal)
    if status:
        statement = statement.where(Deal.status.ilike(status))
    if risk_level:
        statement = statement.where(Deal.risk_level.ilike(risk_level))
    if stage:
        statement = statement.where(Deal.stage.ilike(stage))
    statement = statement.order_by(Deal.risk_score.desc(), Deal.deal_value.desc())
    async with SessionLocal() as session:
        result = await session.execute(statement)
        return [_deal_to_response(deal) for deal in result.scalars().all()]


@app.get("/api/deals/high-risk", response_model=list[DealRead])
async def list_high_risk_deals() -> list[DealRead]:
    statement = (
        select(Deal)
        .where(Deal.status == "open", Deal.risk_level == "HIGH")
        .order_by(Deal.risk_score.desc())
    )
    async with SessionLocal() as session:
        result = await session.execute(statement)
        return [_deal_to_response(deal) for deal in result.scalars().all()]


@app.get("/api/deals/{deal_id}", response_model=DealRead)
async def get_imported_deal(deal_id: str) -> DealRead:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Deal).where(Deal.deal_id == deal_id)
        )
        deal = result.scalar_one_or_none()
        if deal is None:
            raise HTTPException(
                status_code=404,
                detail=f"Deal {deal_id} was not found.",
            )
        return _deal_to_response(deal)


@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics() -> MetricsResponse:
    async with SessionLocal() as session:
        result = await session.execute(select(Deal))
        deals = result.scalars().all()

    open_deals = [
        deal for deal in deals
        if str(deal.status).lower() in {
            "open", "active", "pipeline", "qualified", "proposal",
            "negotiation", "discovery", "in_progress", "in-progress",
        }
    ]
    high_risk_deals = [deal for deal in open_deals if deal.risk_level == "HIGH"]
    risk_distribution = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    pipeline_by_stage: dict[str, float] = {}
    for deal in open_deals:
        level = str(deal.risk_level).upper()
        risk_distribution[level] = risk_distribution.get(level, 0) + 1
        pipeline_by_stage[deal.stage] = (
            pipeline_by_stage.get(deal.stage, 0.0) + float(deal.deal_value)
        )
    top_deals = sorted(
        open_deals,
        key=lambda deal: deal.risk_score,
        reverse=True,
    )[:10]
    return MetricsResponse(
        total_open_pipeline_value=round(
            sum(float(deal.deal_value) for deal in open_deals), 2
        ),
        revenue_high_risk=round(
            sum(float(deal.deal_value) for deal in high_risk_deals), 2
        ),
        high_risk_deals=len(high_risk_deals),
        deals_needing_attention=sum(
            deal.risk_level in {"HIGH", "MEDIUM"} for deal in open_deals
        ),
        deal_distribution_by_risk=risk_distribution,
        pipeline_value_by_stage={
            key: round(value, 2) for key, value in pipeline_by_stage.items()
        },
        top_deals=[_deal_to_response(deal).model_dump() for deal in top_deals],
    )


@app.post("/api/deals/{deal_id}/analyze", response_model=DealRead)
async def analyze_deal_endpoint(deal_id: str) -> DealRead:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Deal).where(Deal.deal_id == deal_id)
        )
        deal = result.scalar_one_or_none()
        if deal is None:
            raise HTTPException(
                status_code=404,
                detail=f"Deal {deal_id} was not found.",
            )
        assessment = analyze_deal({
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
        })
        deal.risk_score = int(assessment["risk_score"])
        deal.risk_level = str(assessment["risk_level"])
        deal.risk_reasons = json.dumps(assessment["risk_reasons"])
        deal.recommended_action = str(assessment["recommended_action"])
        await session.commit()
        await session.refresh(deal)
        return _deal_to_response(deal)


@app.get("/seed/sample")
async def seed_sample_data() -> dict[str, object]:
    rows = synthetic_sample_rows()
    async with SessionLocal() as session:
        try:
            for row in rows:
                await _upsert_deal(session, analyze_deal(row))
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            raise
    return {
        "message": "Seed data loaded successfully.",
        "records_imported": len(rows),
    }
