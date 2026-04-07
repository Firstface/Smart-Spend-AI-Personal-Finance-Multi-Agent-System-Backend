"""
POST /api/auth/register — 注册
POST /api/auth/login    — 登录

简化版 JWT 鉴权：
- bcrypt 哈希密码（passlib）
- python-jose 签发 / 验证 JWT，过期时间 24 小时
- 返回 token + user 对象供前端存入 localStorage
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError

from database import get_db
from models.user import User
from schemas.transaction import RegisterRequest, LoginRequest, UserOut, AuthResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── 密码哈希上下文 ──────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "smartspend-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user_id(token: str) -> str:
    """从 JWT token 中解析 user_id（供其他路由调用）"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )


# ── 注册 ───────────────────────────────────────────────────────────────────────
@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    try:
        # 检查邮箱重复
        if db.query(User).filter(User.email == body.email).first():
            raise HTTPException(status_code=400, detail="该邮箱已被注册")

        # 检查用户名重复
        if db.query(User).filter(User.username == body.username).first():
            raise HTTPException(status_code=400, detail="该用户名已被使用")

        user = User(
            id=uuid.uuid4(),
            username=body.username,
            email=body.email,
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
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")


# ── 登录 ───────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user or not _verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="邮箱或密码错误")

        token = _create_token(str(user.id), user.email)
        return AuthResponse(
            token=token,
            user=UserOut(id=str(user.id), username=user.username, email=user.email),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")
