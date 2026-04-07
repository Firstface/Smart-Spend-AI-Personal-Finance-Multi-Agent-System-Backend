"""
Shared dependency injection: extract user_id from Authorization header.
Falls back to a stable demo UUID when no token is present (for development/debugging).
"""
from fastapi import Header
from typing import Optional
from api.auth import get_current_user_id


# Keep fallback compatible with DB schemas that store user_id as UUID.
DEMO_USER_ID = "00000000-0000-0000-0000-000000000000"


def get_user_id(authorization: Optional[str] = Header(default=None)) -> str:
    """
    Extract user_id from 'Authorization: Bearer <token>'.
    Returns a demo UUID when no token is present, for compatibility with unauthenticated frontend state.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return DEMO_USER_ID
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return get_current_user_id(token)
    except Exception:
        return DEMO_USER_ID
