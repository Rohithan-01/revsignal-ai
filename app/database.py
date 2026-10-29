from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.engine import make_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./revsignal.db")
database_url = make_url(DATABASE_URL)

if database_url.drivername == "sqlite":
    database_url = database_url.set(drivername="sqlite+aiosqlite")
elif database_url.drivername == "postgresql":
    database_url = database_url.set(drivername="postgresql+asyncpg")

if database_url.drivername.startswith("sqlite"):
    database_path = database_url.database
    if database_path and database_path != ":memory:" and not Path(database_path).is_absolute():
        database_url = database_url.set(
            database=f"{BASE_DIR / database_path}"
        )

DATABASE_URL = database_url.render_as_string(hide_password=False)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
