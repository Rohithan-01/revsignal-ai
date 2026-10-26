import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.models import Base
from app.database import engine
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models import Deal, Activity
from sqlalchemy import select
from typing import List
from app.engine.risk_engine import (
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
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is temporarily unavailable"},
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
    async with SessionLocal() as session:
        deals = [
            Deal(
                company="Acme Corp",
                deal_value=50000,
                stage="Negotiation",
                probability=70,
                expected_close_date=datetime.now() + timedelta(days=15),
            ),
            Deal(
                company="TechNova",
                deal_value=25000,
                stage="Proposal",
                probability=40,
                expected_close_date=datetime.now() + timedelta(days=30),
            ),
            Deal(
                company="DataFlow",
                deal_value=80000,
                stage="Qualified",
                probability=60,
                expected_close_date=datetime.now() + timedelta(days=45),
            ),
            Deal(
                company="CloudPeak",
                deal_value=120000,
                stage="Negotiation",
                probability=80,
                expected_close_date=datetime.now() + timedelta(days=10),
            ),
            Deal(
                company="NextGen Solutions",
                deal_value=35000,
                stage="Discovery",
                probability=25,
                expected_close_date=datetime.now() + timedelta(days=60),
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
        latest_activity_by_deal = {}
        for deal_id, activity_date in activity_result.all():
            latest_activity_by_deal.setdefault(
                deal_id,
                activity_date,
            )

    response = []
    for deal in deals:
        latest_activity_date = latest_activity_by_deal.get(deal.id)
        days_since_last_activity = calculate_activity_signal(
            [latest_activity_date] if latest_activity_date else []
        )
        activity_status = get_activity_status(days_since_last_activity)
        is_overdue = is_deal_overdue(deal.expected_close_date)
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
    is_overdue = is_deal_overdue(deal.expected_close_date)
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
    is_overdue = is_deal_overdue(new_deal.expected_close_date)
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