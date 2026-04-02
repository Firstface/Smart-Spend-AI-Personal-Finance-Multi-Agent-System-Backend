"""
POST /api/upload — 文件上传 + 批量分类。

接受 multipart/form-data，字段名 file，限制 10 MB。
流程：解析文件 → 跑六层分类管线 → 写入数据库 → 返回统计+结果。
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
    上传微信支付 Excel（.xlsx）或支付宝账单 CSV（.csv），
    批量分类后写入数据库，返回分类统计和结果列表。
    """
    # ── 文件大小检查 ───────────────────────────────────────────────────────────
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(content)//1024} KB），最大支持 10 MB",
        )

    logger.info(
        f"upload | user={user_id} filename='{file.filename}' "
        f"size={len(content)} bytes"
    )

    # ── 解析文件 ───────────────────────────────────────────────────────────────
    try:
        raw_txns = parse_file(file.filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"文件解析异常: {e}")
        raise HTTPException(status_code=400, detail=f"文件解析失败: {str(e)}")

    if not raw_txns:
        raise HTTPException(status_code=400, detail="文件中没有有效交易记录")

    logger.info(f"解析完成: {len(raw_txns)} 条原始交易")

    # ── 批量分类 ───────────────────────────────────────────────────────────────
    try:
        result = await run_batch(raw_txns, user_id, db)
    except Exception as e:
        logger.error(f"分类管线异常: {e}")
        raise HTTPException(status_code=500, detail=f"分类处理失败: {str(e)}")

    logger.info(
        f"分类完成 | total={result.stats['total']} "
        f"needs_review={result.stats['needs_review']} "
        f"llm_fallback={result.stats.get('llm_fallback', 0)}"
    )
    return result
