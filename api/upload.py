"""  
POST /api/upload — File upload + batch classification.

Accepts multipart/form-data with field name 'file', max 10 MB.
Flow: parse file → run six-layer classification pipeline → write to database → return stats + results.
"""
import logging
import time
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from agents.categorization.parser import parse_file
from agents.categorization.agent import run_batch
from schemas.transaction import ClassificationResult
from api.deps import get_user_id
from agents.security.file_upload_checker import get_file_security_checker

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
    start_time = time.time()
    
    logger.info(f"📥 Incoming file upload | user={user_id} filename='{file.filename}'")
    
    # ── Step 1: Read and check file size ────────────────────────────────────────
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content)//1024} KB), maximum supported size is 10 MB",
        )
    
    logger.info(f"📊 File size: {len(content)//1024} KB")
    
    # ── Step 2: Security check ──────────────────────────────────────────────────
    security_checker = get_file_security_checker()
    security_result = security_checker.check_file_upload(
        filename=file.filename,
        content=content,
        content_type=file.content_type,
    )
    
    if not security_result.is_safe:
        process_time = time.time() - start_time
        logger.warning(f"\n{'='*60}")
        logger.warning(f"🚨 FILE UPLOAD SECURITY THREAT DETECTED 🚨")
        logger.warning(f"{'='*60}")
        logger.warning(f"❌ Action: BLOCKED")
        logger.warning(f"📍 Path: /api/upload")
        logger.warning(f"👤 User: {user_id}")
        logger.warning(f"📄 Filename: {file.filename}")
        logger.warning(f"⚠️  Threat Type: {security_result.threat_type}")
        logger.warning(f"📊 Threat Level: {security_result.threat_level}")
        logger.warning(f"⏱️  Detection Time: {process_time:.3f}s")
        logger.warning(f"💬 Message: {security_result.message}")
        if security_result.details and 'reason' in security_result.details:
            logger.warning(f"📝 Reason: {security_result.details['reason']}")
        logger.warning(f"{'='*60}\n")
        
        raise HTTPException(
            status_code=403,
            detail=security_result.message or "文件被安全系统拦截"
        )
    
    logger.info(f"✅ File security check PASSED | time={time.time() - start_time:.3f}s\n")
    
    # ── Step 3: Parse file ──────────────────────────────────────────────────────
    try:
        raw_txns = parse_file(file.filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"File parse error: {e}")
        raise HTTPException(status_code=400, detail=f"File parsing failed: {str(e)}")
    
    if not raw_txns:
        raise HTTPException(status_code=400, detail="No valid transactions found in the file")
    
    logger.info(f"✅ Parse complete: {len(raw_txns)} raw transactions")
    
    # ── Step 4: Check parsed transaction content for security threats ───────────
    # Extract text fields from parsed transactions for security check
    text_content = " ".join([
        f"{txn.counterparty} {txn.goods_description or ''} {txn.remark or ''}"
        for txn in raw_txns[:50]  # Check first 50 transactions
    ])
    
    if text_content.strip():
        from agents.security.agent import SecurityAgent
        security_agent = SecurityAgent()
        content_security = security_agent.check_input(
            text_content,
            context={'check_type': 'parsed_transactions', 'user_id': user_id}
        )
        
        if not content_security.is_safe:
            logger.warning(f"\n{'='*60}")
            logger.warning(f"🚨 PARSED TRANSACTION CONTENT THREAT DETECTED 🚨")
            logger.warning(f"{'='*60}")
            logger.warning(f"❌ Action: BLOCKED")
            logger.warning(f"👤 User: {user_id}")
            logger.warning(f"⚠️  Threat Type: {content_security.threat_type}")
            logger.warning(f"💬 Message: {content_security.message}")
            logger.warning(f"{'='*60}\n")
            
            raise HTTPException(
                status_code=403,
                detail="文件内容被安全系统拦截：可能包含恶意数据"
            )
        
        logger.info(f"✅ Parsed transaction content check PASSED")
    
    # ── Step 5: Batch classification ────────────────────────────────────────────
    try:
        result = await run_batch(raw_txns, user_id, db)
    except Exception as e:
        logger.error(f"Classification pipeline error: {e}")
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")
    
    total_time = time.time() - start_time
    logger.info(
        f"✅ Classification complete | total={result.stats['total']} "
        f"needs_review={result.stats['needs_review']} "
        f"llm_fallback={result.stats.get('llm_fallback', 0)} "
        f"time={total_time:.3f}s"
    )
    
    # Log response
    logger.info(f"\n{'='*60}")
    logger.info(f"📤 File Upload Response Summary")
    logger.info(f"{'='*60}")
    logger.info(f"✅ Status: 200 OK")
    logger.info(f"📊 Total Transactions: {result.stats['total']}")
    logger.info(f"⏱️  Total Time: {total_time:.3f}s")
    logger.info(f"{'='*60}\n")
    
    return result
