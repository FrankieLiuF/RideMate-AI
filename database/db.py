from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ridemate.db")

# Cloud Run provides DATABASE_URL; local dev uses SQLite
if DATABASE_URL.startswith("postgres"):
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Get a database session. Caller must close it."""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # caller is responsible for db.close()


def init_db():
    """Create all tables. Call once at startup."""
    from . import models  # noqa: F401 — ensure models are imported
    models.Base.metadata.create_all(bind=engine)
