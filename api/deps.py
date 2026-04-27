"""
Shared dependency injection: extract user_id from Authorization header.
Falls back to a stable demo UUID when no token is present (for development/debugging).
"""
import uuid
from typing import Optional

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from api.auth import get_current_user_id
from database import get_db
from models.user import User


# Keep fallback compatible with DB schemas that store user_id as UUID.
DEMO_USER_ID = "00000000-0000-0000-0000-000000000000"
DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@local.test"
DEMO_PASSWORD_HASH = "!demo-no-login"


def _ensure_demo_user(db: Session) -> None:
    """Create the demo user lazily so fallback writes won't violate FK constraints."""
    demo_uuid = uuid.UUID(DEMO_USER_ID)
    existing = db.query(User).filter(User.id == demo_uuid).first()
    if existing:
        return

    # Keep this deterministic so repeated runs remain idempotent.
    user = User(
        id=demo_uuid,
        username=DEMO_USERNAME,
        email=DEMO_EMAIL,
        password_hash=DEMO_PASSWORD_HASH,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Another request may have created the same row concurrently.
        existing = db.query(User).filter(User.id == demo_uuid).first()
        if not existing:
            raise


def get_user_id(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> str:
    """
    Extract user_id from 'Authorization: Bearer <token>'.
    Returns a demo UUID when no token is present, for compatibility with unauthenticated frontend state.
    """
    if not authorization or not authorization.startswith("Bearer "):
        _ensure_demo_user(db)
        return DEMO_USER_ID
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return get_current_user_id(token)
    except Exception:
        _ensure_demo_user(db)
        return DEMO_USER_ID
