"""
SQLAlchemy 数据库连接配置。
使用 Neon PostgreSQL 云数据库，pool_pre_ping=True 处理 Neon 休眠后的重连。
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 环境变量未设置")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # 处理 Neon 休眠后重连
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：获取数据库 session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()