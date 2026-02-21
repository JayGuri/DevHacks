# backend/db/database.py — SQLite + SQLAlchemy engine, session factory
"""
Lightweight SQLite database layer using SQLAlchemy (sync mode).
The DB file is created alongside the backend at ./arfl_backend.db.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'arfl_backend.db')}"
)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called once at app startup."""
    Base.metadata.create_all(bind=engine)
