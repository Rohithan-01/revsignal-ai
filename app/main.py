import os
import csv
import io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from pydantic import ValidationError
from app.models import Base
from app.database import engine

from app.database import SessionLocal
from app.models import Deal, Activity
from sqlalchemy import select
from typing import List
from app.engine.risk_engine import (
    DEMO_BUSINESS_TIMEZONE,
    calculate_overall_risk,
    calculate_risk,
    is_deal_overdue,
)
from app.engine.recommendation_engine import generate_recommendation
from app.engine.activity_engine import (
    calculate_activity_signal,
    get_latest_activity_date,
    get_activity_status,
)

from app.schemas import (
    DealDetailResponse,
    DealResponse,
    DealCreate,
    ActivityCreate,
    ActivityResponse,
)

app = FastAPI(title="RevSignal API")


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
async def root():
    return {"message": "RevSignal API is running"}


@app.get("/health/db")
async def database_health():
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))
        return {
            "database": "connected",
            "result": result.scalar()
        }

@app.on_event("startup")
async def create_tables():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

async def seed_deals():
    today = datetime.now(
        ZoneInfo(DEMO_BUSINESS_TIMEZONE)
    ).date()
    async with SessionLocal() as session:
        deals = [
            Deal(
                company="Acme Corp",
                deal_value=50000,
                stage="Negotiation",
                probability=70,
                expected_close_date=today + timedelta(days=15),
            ),
            Deal(
                company="TechNova",
                deal_value=25000,
                stage="Proposal",
                probability=40,
                expected_close_date=today + timedelta(days=30),
            ),
            Deal(
                company="DataFlow",
                deal_value=80000,
                stage="Qualified",
                probability=60,
                expected_close_date=today + timedelta(days=45),
            ),
            Deal(
                company="CloudPeak",
                deal_value=120000,
                stage="Negotiation",
                probability=80,
                expected_close_date=today + timedelta(days=10),
            ),
            Deal(
                company="NextGen Solutions",
                deal_value=35000,
                stage="Discovery",
                probability=25,
                expected_close_date=today + timedelta(days=60),
            ),
        ]

        session.add_all(deals)
        await session.commit()

        return {
            "message": "Dummy deals created",
            "count": len(deals)
        }


def register_seed_endpoint(application: FastAPI) -> None:
    if os.getenv("ENABLE_SEED_ENDPOINT", "").strip().lower() == "true":
        application.post("/seed/deals")(seed_deals)


register_seed_endpoint(app)


@app.get("/deals", response_model=List[DealResponse])
async def get_deals():
    async with SessionLocal() as session:
        result = await session.execute(
            select(Deal)
        )
        deals = result.scalars().all()

        activity_result = await session.execute(
            select(Activity.deal_id, Activity.activity_date).order_by(
                Activity.activity_date.desc()
            )
        )
        activity_dates_by_deal = {}
        for deal_id, activity_date in activity_result.all():
            activity_dates_by_deal.setdefault(deal_id, []).append(
                activity_date
            )

    response = []
    for deal in deals:
        activity_dates = activity_dates_by_deal.get(deal.id, [])
        days_since_last_activity = calculate_activity_signal(
            activity_dates
        )
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
async def get_deal(deal_id: int):
    async with SessionLocal() as session:
        deal = await session.get(Deal, deal_id)
        if deal is None:
            raise HTTPException(status_code=404, detail="Deal not found")

        activity_result = await session.execute(
            select(Activity).where(Activity.deal_id == deal_id)
        )
        activities = activity_result.scalars().all()

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
        "latest_activity_date": latest_activity_date,
        "activities": activities,
    }

@app.post("/deals", response_model=DealResponse)
async def create_deal(deal: DealCreate):
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

    risk_level = calculate_risk(new_deal.probability)
    is_overdue = is_deal_overdue(
        new_deal.expected_close_date,
        DEMO_BUSINESS_TIMEZONE,
    )
    activity_status = get_activity_status(None)
    overall_risk_level, risk_reasons = calculate_overall_risk(
        new_deal.probability,
        is_overdue,
        activity_status,
        has_expected_close_date=new_deal.expected_close_date is not None,
    )
    recommendation = generate_recommendation(
         overall_risk_level,
         is_overdue,
    )

    return {
    "id": new_deal.id,
    "company": new_deal.company,
    "deal_value": new_deal.deal_value,
    "stage": new_deal.stage,
    "probability": new_deal.probability,
    "risk_level": risk_level,
    "overall_risk_level": overall_risk_level,
    "risk_reasons": risk_reasons,
    "is_overdue": is_overdue,
    "activity_status": activity_status,
    "days_since_last_activity": None,
    "recommendation": recommendation,
    "expected_close_date": new_deal.expected_close_date,
    "created_at": new_deal.created_at,
    }


@app.post("/deals/import-csv")
async def import_deals_csv(file: UploadFile = File(...)):
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
            raise HTTPException(
                status_code=400,
                detail="CSV row 1: missing header row",
            )

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
        response_deals.append({
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
        })

    return {"count": len(response_deals), "deals": response_deals}


@app.post("/activities", response_model=ActivityResponse)
async def create_activity(activity: ActivityCreate):
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
async def get_activities():
    async with SessionLocal() as session:
        result = await session.execute(
            select(Activity)
        )
        activities = result.scalars().all()

        return activities

@app.get("/deals/{deal_id}/activities", response_model=list[ActivityResponse])
async def get_deal_activities(deal_id: int):
    async with SessionLocal() as session:
        deal = await session.get(Deal, deal_id)
        if deal is None:
            raise HTTPException(status_code=404, detail="Deal not found")

        result = await session.execute(
            select(Activity).where(Activity.deal_id == deal_id)
        )
        activities = result.scalars().all()

        return activities

@app.get("/deals/{deal_id}/activity-signal")
async def get_activity_signal(deal_id: int):
    async with SessionLocal() as session:
        deal = await session.get(Deal, deal_id)
        if deal is None:
            raise HTTPException(status_code=404, detail="Deal not found")

        result = await session.execute(
            select(Activity).where(Activity.deal_id == deal_id)
        )

        activities = result.scalars().all()

        activity_dates = [
            activity.activity_date
            for activity in activities
        ]

        days_since_last_activity = calculate_activity_signal(
            activity_dates
        )

        activity_status = get_activity_status(
           days_since_last_activity
          )

        return {
          "deal_id": deal_id,
          "days_since_last_activity": days_since_last_activity,
          "activity_status": activity_status,
        }