from fastapi import FastAPI
from sqlalchemy import text
from app.models import Base
from app.database import engine
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models import Deal
from sqlalchemy import select

app = FastAPI(title="RevSignal API")


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

@app.post("/seed/deals")
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

@app.get("/deals")
async def get_deals():
    async with SessionLocal() as session:
        result = await session.execute(
            select(Deal)
        )
        deals = result.scalars().all()

        return deals