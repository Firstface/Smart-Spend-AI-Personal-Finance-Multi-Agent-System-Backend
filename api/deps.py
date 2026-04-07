"""
Shared dependency injection: extract user_id from Authorization header.
Falls back to "demo-user" when no token is present (for development/debugging).
"""
from fastapi import Header
from typing import Optional
from api.auth import get_current_user_id


def get_user_id(authorization: Optional[str] = Header(default=None)) -> str:
    """
    Extract user_id from 'Authorization: Bearer <token>'.
    Returns 'demo-user' when no token is present, for compatibility with unauthenticated frontend state.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return "demo-user"
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return get_current_user_id(token)
    except Exception:
        return "demo-user"
