"""
POST /api/auth/register — User registration
POST /api/auth/login    — User login

Simplified JWT authentication:
- bcrypt password hashing
- python-jose JWT issuance / verification, 24-hour expiry
- Returns token + user object for frontend to store in localStorage
"""
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import bcrypt
from jose import jwt, JWTError

from database import get_db
from models.user import User
from schemas.transaction import RegisterRequest, LoginRequest, UserOut, AuthResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "smartspend-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def _hash_password(password: str) -> str:
    try:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Invalid hash or plaintext constraints should be treated as auth failure.
        return False
    except Exception:
        return False


def _validate_password_bytes(password: str) -> None:
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password cannot be longer than 72 bytes",
        )


def _create_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user_id(token: str) -> str:
    """Extract user_id from JWT token (called by other routes)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or expired",
        )


# ── Register ────────────────────────────────────────────────────────────────────
@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    try:
        _validate_password_bytes(body.password)
        email = body.email.strip().lower()
        username = body.username.strip()

        if not username:
            raise HTTPException(status_code=400, detail="Username cannot be empty")

        # Check for duplicate email
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=400, detail="This email is already registered")

        # Check for duplicate username
        if db.query(User).filter(User.username == username).first():
            raise HTTPException(status_code=400, detail="This username is already taken")

        user = User(
            id=uuid.uuid4(),
            username=username,
            email=email,
            password_hash=_hash_password(body.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = _create_token(str(user.id), user.email)
        return AuthResponse(
            token=token,
            user=UserOut(id=str(user.id), username=user.username, email=user.email),
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


# ── Login ───────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    try:
        _validate_password_bytes(body.password)
        email = body.email.strip().lower()

        user = db.query(User).filter(User.email == email).first()
        if not user or not _verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        token = _create_token(str(user.id), user.email)
        return AuthResponse(
            token=token,
            user=UserOut(id=str(user.id), username=user.username, email=user.email),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected login error")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")
