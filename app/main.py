from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine

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