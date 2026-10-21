import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./revsignal.db")

if DATABASE_URL.startswith("sqlite") and not DATABASE_URL.startswith("sqlite:///"):
    DATABASE_URL = f"sqlite:///{BASE_DIR / DATABASE_URL.replace('sqlite:///', '')}"

if DATABASE_URL.startswith("sqlite:///."):
    DATABASE_URL = f"sqlite:///{(BASE_DIR / DATABASE_URL.replace('sqlite:///', '', 1)).resolve()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass
