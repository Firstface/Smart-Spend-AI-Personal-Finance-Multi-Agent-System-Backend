"""
Smart Spend AI — 分类Agent后端主入口。
FastAPI 应用，挂载所有路由，配置 CORS 允许前端访问。
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 配置结构化日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

app = FastAPI(
    title="Smart Spend AI — Categorization Agent",
    version="1.0.0",
    description="个人财务分类Agent后端：多层规则引擎 + LLM回退 + 自反思循环",
)

# CORS 配置：允许前端 localhost:3000 / 5173 / 3001 访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "smart-spend-categorization-agent"}


from api.auth import router as auth_router
from api.upload import router as upload_router
from api.transactions import router as transactions_router
from api.review import router as review_router
from api.chat import router as chat_router

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(transactions_router)
app.include_router(review_router)
app.include_router(chat_router)

# Education router (optional — guarded for version compatibility)
try:
    from api.education import router as education_router
    app.include_router(education_router)
except Exception as _e:
    import logging as _l
    _l.getLogger(__name__).warning(f"Education router skipped: {_e}")