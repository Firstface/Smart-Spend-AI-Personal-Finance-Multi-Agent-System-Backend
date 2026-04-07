"""
POST /api/upload — File upload + batch classification.

Accepts multipart/form-data with field name 'file', max 10 MB.
Flow: parse file → run six-layer classification pipeline → write to database → return stats + results.
"""
import logging
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from agents.categorization.parser import parse_file
from agents.categorization.agent import run_batch
from schemas.transaction import ClassificationResult
from api.deps import get_user_id

router = APIRouter(prefix="/api", tags=["upload"])
logger = logging.getLogger("api.upload")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=ClassificationResult)
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Upload a WeChat Pay Excel (.xlsx) or Alipay bill CSV (.csv),
    batch-classify, write to database, and return classification stats and results.
    """
    # ── File size check ────────────────────────────────────────────────────────
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content)//1024} KB), maximum supported size is 10 MB",
        )

    logger.info(
        f"upload | user={user_id} filename='{file.filename}' "
        f"size={len(content)} bytes"
    )

    # ── Parse file ─────────────────────────────────────────────────────────────
    try:
        raw_txns = parse_file(file.filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"File parse error: {e}")
        raise HTTPException(status_code=400, detail=f"File parsing failed: {str(e)}")

    if not raw_txns:
        raise HTTPException(status_code=400, detail="No valid transactions found in the file")

    logger.info(f"Parse complete: {len(raw_txns)} raw transactions")

    # ── Batch classification ───────────────────────────────────────────────────
    try:
        result = await run_batch(raw_txns, user_id, db)
    except Exception as e:
        logger.error(f"Classification pipeline error: {e}")
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")

    logger.info(
        f"Classification complete | total={result.stats['total']} "
        f"needs_review={result.stats['needs_review']} "
        f"llm_fallback={result.stats.get('llm_fallback', 0)}"
    )
    return result
