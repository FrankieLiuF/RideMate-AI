"""
Database engine configuration — SQLite for development, PostgreSQL for production.

DUAL-DATABASE STRATEGY
======================
The same SQLAlchemy code works with both databases by swapping DATABASE_URL:

  Development:
    DATABASE_URL not set → sqlite:///./ridemate.db (auto-created)

  Production (Cloud Run):
    DATABASE_URL=postgresql://user:pass@host/dbname (set via env var)

Why SQLite dev, PostgreSQL prod?
  - SQLite: zero setup, single file, survives restarts, git-ignored
  - PostgreSQL: Cloud Run native, connection pooling, concurrent writes
  - Schema is identical — all tables use standard SQLAlchemy types

The 'check_same_thread' flag is SQLite-specific:
  SQLite by default only allows the thread that created the connection to
  use it. FastAPI runs on multiple threads, so we must disable this check.
  PostgreSQL ignores this flag entirely.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ridemate.db")

# PostgreSQL connections are thread-safe pool-based.
# SQLite needs check_same_thread=False for multi-threaded FastAPI.
if DATABASE_URL.startswith("postgres"):
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Session factory — each request gets its own session.
# autocommit=False: we explicitly commit after writes
# autoflush=False: we control when changes are flushed to DB
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """
    Get a raw database session.

    IMPORTANT: The caller is responsible for closing the session.
    Tools in agent/tools.py use a try/finally pattern:
        db = SessionLocal()
        try: ... db.commit()
        finally: db.close()

    For dependency injection (future FastAPI Depends pattern), wrap with:
        def get_db_dep():
            db = SessionLocal()
            try: yield db
            finally: db.close()
    """
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # caller MUST close the session


def init_db():
    """
    Create all tables on startup. Called once from main.py.

    Uses SQLAlchemy's create_all() which is idempotent — tables that
    already exist are skipped. Safe to call on every server start.

    The 'import models' is deliberate even though it's a local import:
    it ensures all model classes are registered with Base.metadata
    before create_all() inspects the metadata.
    """
    from . import models  # noqa: F401 — trigger model registration
    models.Base.metadata.create_all(bind=engine)
