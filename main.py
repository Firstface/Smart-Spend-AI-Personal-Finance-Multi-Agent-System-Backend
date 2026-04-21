"""
Smart Spend AI — Categorization Agent backend entry point.
FastAPI application: mounts all routers and configures CORS for frontend access.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configure structured logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

app = FastAPI(
    title="Smart Spend AI — Categorization Agent",
    version="1.0.0",
    description="Personal finance categorization agent backend: multi-layer rule engine + LLM fallback + self-reflection loop",
)

# CORS: allow frontend access from localhost:3000 / 5173 / 3001
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

# Security Middleware - Protects against SQL injection, XSS, prompt injection, etc.
from api.security_middleware import SecurityMiddleware
app.add_middleware(SecurityMiddleware)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "smart-spend-categorization-agent"}


from api.auth import router as auth_router
from api.upload import router as upload_router
from api.transactions import router as transactions_router
from api.review import router as review_router
from api.chat import router as chat_router
from api.insights import router as insights_router

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

app.include_router(education_router)
app.include_router(insights_router)