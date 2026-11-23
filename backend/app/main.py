from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from weakref import WeakKeyDictionary
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .data_import import (
    DEAL_ID_PATTERN,
    import_csv_records,
    synthetic_sample_rows,
    validate_deal_id,
)
from .database import Base, SessionLocal, engine
from .engine.activity_engine import (
    calculate_activity_signal,
    get_activity_status,
    get_latest_activity_date,
)
from .engine.recommendation_engine import generate_recommendation
from .engine.risk_engine import (
    DEMO_BUSINESS_TIMEZONE,
    calculate_overall_risk,
    calculate_risk,
    is_deal_overdue,
)
from .models import Activity, Deal
from .risk_engine import analyze_deal
from .risk_engine import calculate_crm_risk_level
from .schemas import (
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
logger = logging.getLogger("uvicorn.error")
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
_DEAL_ID_LOCK_KEY = 0x5256534445414C
_MINIMUM_DEAL_ID_NUMBER = 100
_deal_id_locks: WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Lock
] = WeakKeyDictionary()


@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _current_deal_id_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _deal_id_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _deal_id_locks[loop] = lock
    return lock


@asynccontextmanager
async def _deal_id_write_lock(session: AsyncSession) -> AsyncIterator[None]:
    async with _current_deal_id_lock():
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _DEAL_ID_LOCK_KEY},
            )
        elif dialect_name == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        else:
            raise RuntimeError(
                f"Safe deal ID allocation is unsupported for {dialect_name}."
            )
        yield


async def _next_deal_id_number(
    session: AsyncSession,
    reserved_ids: list[str] | None = None,
) -> int:
    result = await session.execute(select(Deal.deal_id))
    deal_ids = list(result.scalars().all()) + (reserved_ids or [])
    suffixes = [_MINIMUM_DEAL_ID_NUMBER]
    for existing_id in deal_ids:
        match = DEAL_ID_PATTERN.fullmatch(str(existing_id))
        if match is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Existing deal ID {existing_id!r} is not canonical; "
                    "apply the deal ID migration before creating deals."
                ),
            )
        suffixes.append(int(match.group(1)))
    return max(suffixes) + 1


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(
    request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    logger.error(
        "Database operation failed for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )

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

    original_error = getattr(exc, "orig", None)
    sqlstate = (
        getattr(original_error, "sqlstate", None)
        or getattr(original_error, "pgcode", None)
    )
    if sqlstate in {"42703", "42P01", "42704", "42804"}:
        return JSONResponse(
            status_code=500,
            content={
                "detail": (
                    "Database schema is incompatible with this application; "
                    "administrator action is required"
                )
            },
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


@app.get("/health/db")
async def database_health_check() -> JSONResponse:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database connectivity check failed for GET /health/db")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "disconnected"},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "database": "connected"},
    )


async def seed_deals() -> dict[str, object]:
    today = datetime.now(ZoneInfo(DEMO_BUSINESS_TIMEZONE)).date()
    seed_rows = [
        ("D-113", "Acme Corp", 50000, "Negotiation", 70, 15),
        ("D-114", "TechNova", 25000, "Proposal", 40, 30),
        ("D-115", "DataFlow", 80000, "Qualified", 60, 45),
        ("D-116", "CloudPeak", 120000, "Negotiation", 80, 10),
        ("D-117", "NextGen Solutions", 35000, "Discovery", 25, 60),
    ]
    async with SessionLocal() as session:
        async with _deal_id_write_lock(session):
            deal_ids = [row[0] for row in seed_rows]
            result = await session.execute(
                select(Deal.deal_id).where(Deal.deal_id.in_(deal_ids))
            )
            existing_ids = sorted(result.scalars().all())
            if existing_ids:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": (
                            "Seed deal IDs already exist; no records were changed"
                        ),
                        "deal_ids": existing_ids,
                    },
                )
            session.add_all(
                [
                    Deal(
                        deal_id=deal_id,
                        company=company,
                        deal_value=value,
                        stage=stage,
                        probability=probability,
                        probability_is_known=True,
                        expected_close_date=today + timedelta(days=days),
                    )
                    for (
                        deal_id,
                        company,
                        value,
                        stage,
                        probability,
                        days,
                    ) in seed_rows
                ]
            )
            await session.commit()
    return {"message": "Dummy deals loaded successfully", "count": len(seed_rows)}


def register_seed_endpoint(application: FastAPI) -> None:
    if os.getenv("ENABLE_SEED_ENDPOINT", "").strip().lower() == "true":
        application.post("/seed/deals")(seed_deals)


register_seed_endpoint(app)


def _legacy_risk_details(
    deal: Deal,
    activity_dates: list[datetime],
) -> tuple[int | None, str, bool, str, list[str], str]:
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
        probability_is_known=deal.probability_is_known,
    )
    recommendation = generate_recommendation(overall_risk_level, is_overdue)
    return (
        days_since_last_activity,
        activity_status,
        is_overdue,
        overall_risk_level,
        risk_reasons,
        recommendation,
    )


def _legacy_risk_level(deal: Deal, overall_risk_level: str) -> str:
    if deal.probability_is_known:
        return calculate_risk(deal.probability)
    return overall_risk_level


def _legacy_deal_response(deal: Deal) -> dict[str, object]:
    (
        days_since_last_activity,
        activity_status,
        is_overdue,
        overall_risk_level,
        risk_reasons,
        recommendation,
    ) = _legacy_risk_details(
        deal,
        [],
    )
    return {
        "id": deal.id,
        "company": deal.company,
        "deal_value": deal.deal_value,
        "stage": deal.stage,
        "probability": deal.probability,
        "probability_is_known": deal.probability_is_known,
        "risk_level": _legacy_risk_level(deal, overall_risk_level),
        "overall_risk_level": overall_risk_level,
        "risk_reasons": risk_reasons,
        "is_overdue": is_overdue,
        "activity_status": activity_status,
        "days_since_last_activity": days_since_last_activity,
        "recommendation": recommendation,
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
        (
            days_since_last_activity,
            activity_status,
            is_overdue,
            overall_risk_level,
            risk_reasons,
            recommendation,
        ) = _legacy_risk_details(
            deal,
            activity_dates,
        )
        response.append({
            "id": deal.id,
            "company": deal.company,
            "deal_value": deal.deal_value,
            "stage": deal.stage,
            "probability": deal.probability,
            "probability_is_known": deal.probability_is_known,
            "risk_level": _legacy_risk_level(deal, overall_risk_level),
            "overall_risk_level": overall_risk_level,
            "risk_reasons": risk_reasons,
            "is_overdue": is_overdue,
            "activity_status": activity_status,
            "days_since_last_activity": days_since_last_activity,
            "recommendation": recommendation,
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
        probability_is_known=deal.probability_is_known,
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
    async with SessionLocal() as session:
        async with _deal_id_write_lock(session):
            next_number = await _next_deal_id_number(session)
            new_deal = Deal(
                deal_id=f"D-{next_number}",
                company=deal.company,
                deal_value=deal.deal_value,
                stage=deal.stage,
                probability=deal.probability,
                probability_is_known="probability" in deal.model_fields_set,
                expected_close_date=deal.expected_close_date,
            )
            session.add(new_deal)
            await session.commit()
            await session.refresh(new_deal)
    return _legacy_deal_response(new_deal)


@app.post("/deals/import-csv")
async def import_deals_csv(file: UploadFile = File(...)) -> dict[str, object]:
    import csv
    import io

    required_headers = {
        "company",
        "deal_value",
        "stage",
        "probability",
        "expected_close_date",
    }
    allowed_headers = required_headers | {"deal_id"}
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
        header_set = set(headers)
        missing_headers = required_headers - header_set
        unexpected_headers = header_set - allowed_headers
        duplicate_headers = len(headers) != len(header_set)
        if missing_headers or unexpected_headers or duplicate_headers:
            details = []
            if missing_headers:
                details.append(f"missing columns: {', '.join(sorted(missing_headers))}")
            if unexpected_headers:
                details.append(
                    f"unexpected columns: {', '.join(sorted(unexpected_headers))}"
                )
            if duplicate_headers:
                details.append("duplicate column names")
            raise HTTPException(
                status_code=400,
                detail=f"CSV row 1: invalid headers ({'; '.join(details)})",
            )

        validated_deals: list[tuple[DealCreate, str | None]] = []
        row_errors = []
        seen_deal_ids: set[str] = set()
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
            requested_deal_id = row.pop("deal_id", "").strip() or None
            if requested_deal_id is not None:
                try:
                    requested_deal_id = validate_deal_id(requested_deal_id)
                    if requested_deal_id in seen_deal_ids:
                        raise ValueError(
                            f"Duplicate deal_id {requested_deal_id!r} in CSV."
                        )
                    seen_deal_ids.add(requested_deal_id)
                except ValueError as exc:
                    row_errors.append(f"row {row_number}, deal_id: {exc}")
                    continue
            close_date = row["expected_close_date"].strip()
            if not close_date:
                row["expected_close_date"] = None
            else:
                try:
                    row["expected_close_date"] = date.fromisoformat(close_date)
                except ValueError:
                    pass
            try:
                validated_deals.append(
                    (DealCreate.model_validate(row), requested_deal_id)
                )
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

    async with SessionLocal() as session:
        try:
            async with _deal_id_write_lock(session):
                requested_ids = [
                    deal_id
                    for _, deal_id in validated_deals
                    if deal_id is not None
                ]
                existing_result = await session.execute(
                    select(Deal.deal_id).where(
                        Deal.deal_id.in_(requested_ids)
                    )
                )
                existing_ids = sorted(existing_result.scalars().all())
                if existing_ids:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "message": (
                                "Import contains deal IDs that already exist; "
                                "no records were changed"
                            ),
                            "deal_ids": existing_ids,
                        },
                    )
                next_number = await _next_deal_id_number(
                    session,
                    reserved_ids=requested_ids,
                )
                new_deals = []
                for deal, requested_id in validated_deals:
                    if requested_id is None:
                        assigned_id = f"D-{next_number}"
                        next_number += 1
                    else:
                        assigned_id = requested_id
                    new_deals.append(
                        Deal(
                            deal_id=assigned_id,
                            company=deal.company,
                            deal_value=deal.deal_value,
                            stage=deal.stage,
                            probability=deal.probability,
                            probability_is_known=True,
                            expected_close_date=deal.expected_close_date,
                        )
                    )
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


def _assessment_record(
    deal: Deal,
    activity_dates: list[datetime] | None = None,
) -> dict[str, object]:
    last_activity_date = deal.last_activity_date
    if last_activity_date is None and activity_dates:
        latest_activity = get_latest_activity_date(activity_dates)
        if latest_activity is not None:
            if latest_activity.tzinfo is None or latest_activity.utcoffset() is None:
                latest_activity = latest_activity.replace(tzinfo=ZoneInfo("UTC"))
            last_activity_date = latest_activity.astimezone(
                ZoneInfo(DEMO_BUSINESS_TIMEZONE)
            ).date()

    return {
        "deal_id": deal.deal_id,
        "account_name": deal.account_name,
        "deal_value": deal.deal_value,
        "stage": deal.stage,
        "status": deal.status,
        "probability": deal.probability,
        "probability_is_known": deal.probability_is_known,
        "created_date": deal.created_date,
        "expected_close_date": deal.expected_close_date,
        "last_activity_date": last_activity_date,
        "activity_count": deal.activity_count,
        "meeting_count": deal.meeting_count,
        "email_count": deal.email_count,
        "stakeholder_count": deal.stakeholder_count,
    }


def _deal_to_response(
    deal: Deal,
    activity_dates: list[datetime] | None = None,
) -> DealRead:
    record = _assessment_record(deal, activity_dates)
    if not _has_persisted_crm_assessment(deal):
        assessment = analyze_deal(record)
        risk_score = int(assessment["risk_score"])
        risk_level = str(assessment["risk_level"])
        risk_reasons = list(assessment["risk_reasons"])
        recommended_action = str(assessment["recommended_action"])
    else:
        risk_score = deal.risk_score
        risk_level, probability_reason = calculate_crm_risk_level(
            risk_score,
            deal.probability,
            deal.probability_is_known,
        )
        risk_reasons = json.loads(deal.risk_reasons or "[]")
        if probability_reason is not None and probability_reason not in risk_reasons:
            risk_reasons.append(probability_reason)
        recommended_action = deal.recommended_action
        if (
            risk_level != str(deal.risk_level).upper()
            or not recommended_action.strip()
        ):
            assessment = analyze_deal(record)
            recommended_action = str(assessment["recommended_action"])

    return DealRead(
        id=deal.id,
        deal_id=deal.deal_id,
        account_name=deal.account_name,
        deal_value=float(deal.deal_value),
        stage=deal.stage,
        status=deal.status,
        probability=float(deal.probability),
        probability_is_known=deal.probability_is_known,
        created_date=deal.created_date,
        expected_close_date=deal.expected_close_date,
        last_activity_date=deal.last_activity_date,
        activity_count=deal.activity_count,
        meeting_count=deal.meeting_count,
        email_count=deal.email_count,
        stakeholder_count=deal.stakeholder_count,
        risk_score=risk_score,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        recommended_action=recommended_action,
    )


def _has_persisted_crm_assessment(deal: Deal) -> bool:
    return (
        deal.risk_score != 0
        or bool(json.loads(deal.risk_reasons or "[]"))
        or bool(deal.recommended_action.strip())
        or str(deal.risk_level).upper() != "LOW"
    )


async def _activity_dates_by_deal(
    session,
    deals: list[Deal],
) -> dict[int, list[datetime]]:
    deal_ids = [deal.id for deal in deals if deal.id is not None]
    if not deal_ids:
        return {}

    activity_result = await session.execute(
        select(Activity.deal_id, Activity.activity_date).where(
            Activity.deal_id.in_(deal_ids)
        )
    )
    activity_dates: dict[int, list[datetime]] = {}
    for deal_id, activity_date in activity_result.all():
        activity_dates.setdefault(deal_id, []).append(activity_date)
    return activity_dates


async def _upsert_deal(session, assessment: dict[str, object]) -> Deal:
    try:
        deal_id = validate_deal_id(assessment["deal_id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = await session.execute(
        select(Deal).where(Deal.deal_id == deal_id)
    )
    deal = result.scalar_one_or_none()
    values = {
        "company": str(assessment.get("account_name") or "Unknown account"),
        "deal_value": float(assessment.get("deal_value") or 0),
        "stage": str(assessment.get("stage") or "Unknown"),
        "status": str(assessment.get("status") or "open"),
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
        probability_value = assessment.get("probability")
        values["probability"] = (
            50.0
            if probability_value is None
            else float(probability_value)
        )
        values["probability_is_known"] = bool(
            assessment.get("probability_is_known", False)
        )
        deal = Deal(deal_id=deal_id, **values)
        session.add(deal)
    else:
        if assessment.get("probability_is_known"):
            values["probability"] = float(assessment["probability"])
            values["probability_is_known"] = True
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
            async with _deal_id_write_lock(session):
                incoming_ids = [str(record["deal_id"]) for record in imported]
                existing_result = await session.execute(
                    select(Deal.deal_id).where(Deal.deal_id.in_(incoming_ids))
                )
                existing_ids = sorted(existing_result.scalars().all())
                if existing_ids:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "message": (
                                "Import contains deal IDs that already exist; "
                                "no records were changed"
                            ),
                            "deal_ids": existing_ids,
                        },
                    )
                for record in imported:
                    assessment = analyze_deal(record)
                    session.add(
                        Deal(
                            deal_id=str(assessment["deal_id"]),
                            company=str(assessment["account_name"]),
                            deal_value=float(assessment["deal_value"]),
                            stage=str(assessment["stage"]),
                            status=str(assessment["status"]),
                            probability=float(assessment["probability"]),
                            probability_is_known=bool(
                                assessment["probability_is_known"]
                            ),
                            created_date=assessment["created_date"],
                            expected_close_date=assessment["expected_close_date"],
                            last_activity_date=assessment["last_activity_date"],
                            activity_count=assessment["activity_count"],
                            meeting_count=assessment["meeting_count"],
                            email_count=assessment["email_count"],
                            stakeholder_count=assessment["stakeholder_count"],
                            risk_score=int(assessment["risk_score"]),
                            risk_level=str(assessment["risk_level"]),
                            risk_reasons=json.dumps(assessment["risk_reasons"]),
                            recommended_action=str(
                                assessment["recommended_action"]
                            ),
                        )
                    )
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
    if stage:
        statement = statement.where(Deal.stage.ilike(stage))
    statement = statement.order_by(Deal.risk_score.desc(), Deal.deal_value.desc())
    async with SessionLocal() as session:
        result = await session.execute(statement)
        deals = result.scalars().all()
        activity_dates = await _activity_dates_by_deal(session, deals)
        responses = [
            _deal_to_response(deal, activity_dates.get(deal.id, []))
            for deal in deals
        ]
        if risk_level:
            normalized_risk_level = risk_level.upper()
            responses = [
                response
                for response in responses
                if response.risk_level == normalized_risk_level
            ]
        return responses


@app.get("/api/deals/high-risk", response_model=list[DealRead])
async def list_high_risk_deals() -> list[DealRead]:
    statement = (
        select(Deal)
        .where(Deal.status == "open")
        .order_by(Deal.risk_score.desc())
    )
    async with SessionLocal() as session:
        result = await session.execute(statement)
        deals = result.scalars().all()
        activity_dates = await _activity_dates_by_deal(session, deals)
        responses = [
            _deal_to_response(deal, activity_dates.get(deal.id, []))
            for deal in deals
        ]
        return [response for response in responses if response.risk_level == "HIGH"]


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
        activity_dates = await _activity_dates_by_deal(session, [deal])
        return _deal_to_response(
            deal,
            activity_dates.get(deal.id, []),
        )


@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics() -> MetricsResponse:
    async with SessionLocal() as session:
        result = await session.execute(select(Deal))
        deals = result.scalars().all()
        activity_dates_by_deal = await _activity_dates_by_deal(session, deals)

    open_deals = [
        deal for deal in deals
        if str(deal.status).lower() in {
            "open", "active", "pipeline", "qualified", "proposal",
            "negotiation", "discovery", "in_progress", "in-progress",
        }
    ]
    response_by_deal_id = {
        deal.id: _deal_to_response(
            deal,
            activity_dates_by_deal.get(deal.id, []),
        )
        for deal in open_deals
    }
    risk_levels = {
        deal.id: response_by_deal_id[deal.id].risk_level
        for deal in open_deals
    }
    high_risk_deals = [
        deal for deal in open_deals if risk_levels[deal.id] == "HIGH"
    ]
    risk_distribution = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    pipeline_by_stage: dict[str, float] = {}
    for deal in open_deals:
        level = risk_levels[deal.id]
        risk_distribution[level] = risk_distribution.get(level, 0) + 1
        pipeline_by_stage[deal.stage] = (
            pipeline_by_stage.get(deal.stage, 0.0) + float(deal.deal_value)
        )
    top_deals = sorted(
        open_deals,
        key=lambda deal: response_by_deal_id[deal.id].risk_score,
        reverse=True,
    )[:10]
    top_deal_responses = [
        response_by_deal_id[deal.id].model_dump()
        for deal in top_deals
    ]

    return MetricsResponse(
        total_open_pipeline_value=round(
            sum(float(deal.deal_value) for deal in open_deals), 2
        ),
        revenue_high_risk=round(
            sum(float(deal.deal_value) for deal in high_risk_deals), 2
        ),
        high_risk_deals=len(high_risk_deals),
        deals_needing_attention=sum(
            risk_levels[deal.id] in {"HIGH", "MEDIUM"}
            for deal in open_deals
        ),
        deal_distribution_by_risk=risk_distribution,
        pipeline_value_by_stage={
            key: round(value, 2) for key, value in pipeline_by_stage.items()
        },
        top_deals=top_deal_responses,
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
        activity_dates = await _activity_dates_by_deal(session, [deal])
        deal_activity_dates = activity_dates.get(deal.id, [])
        assessment = analyze_deal(
            _assessment_record(deal, deal_activity_dates)
        )
        deal.risk_score = int(assessment["risk_score"])
        deal.risk_level = str(assessment["risk_level"])
        deal.risk_reasons = json.dumps(assessment["risk_reasons"])
        deal.recommended_action = str(assessment["recommended_action"])
        await session.commit()
        await session.refresh(deal)
        return _deal_to_response(deal, deal_activity_dates)


@app.get("/seed/sample")
async def seed_sample_data() -> dict[str, object]:
    rows = synthetic_sample_rows()
    async with SessionLocal() as session:
        try:
            async with _deal_id_write_lock(session):
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
