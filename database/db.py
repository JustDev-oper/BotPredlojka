"""
Database connection and session management.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import logging
from pathlib import Path

from config import DATABASE_URL, DATA_DIR
from database.models import Base

logger = logging.getLogger(__name__)

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Create engine with proper SQLite settings
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
    pool_pre_ping=True,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info(f"Database initialized at {DATA_DIR}")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        logger.error(f"Error getting database session: {e}")
        db.close()
        raise


def close_db(db: Session):
    """Close database session."""
    if db:
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error closing database session: {e}")

