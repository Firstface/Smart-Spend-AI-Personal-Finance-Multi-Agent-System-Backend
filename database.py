"""
SQLAlchemy database connection configuration.
Uses Neon PostgreSQL (cloud). Key settings:
- pool_pre_ping: test connections before use to handle Neon idle disconnections
- pool_recycle: recycle connections every 5 minutes to avoid stale SSL
- keepalives: OS-level TCP keepalive to prevent Neon from closing idle connections
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,     # Test connection health before use
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,       # Recycle connections every 5 min to avoid Neon SSL timeout
    connect_args={
        # TCP keepalive: send probe every 30 s, retry 5 times at 10 s intervals
        # Prevents Neon from closing connections idle during long LLM calls
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency injection: provide a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            # Connection may have been dropped by Neon after a long LLM call.
            # Invalidate so the pool discards this connection rather than reusing it.
            try:
                db.invalidate()
            except Exception:
                pass
