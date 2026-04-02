"""
POST /api/review/{transaction_id} — 人工审查（HITL 人在回路）。

课程对应：
- Human-Reflection Pattern（Day2 PPT Slide 49）
- IMDA 人类参与度 Level 3：AI 给建议，人做最终决策
- 用户纠正反馈作为持续学习信号写回数据库
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.transaction import Transaction
from models.review_queue import ReviewItem
from schemas.transaction import ReviewRequest
from api.deps import get_user_id

router = APIRouter(prefix="/api", tags=["review"])
logger = logging.getLogger("api.review")


@router.post("/review/{transaction_id}")
def review_transaction(
    transaction_id: str,
    body: ReviewRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    确认或纠正一条交易的分类结果。

    action="confirm" → 确认 AI 分类，清除待审查标记
    action="correct" → 用 corrected_category 覆盖原分类，置信度设为 1.0
    """
    # ── 查找交易 ───────────────────────────────────────────────────────────────
    txn = (
        db.query(Transaction)
        .filter(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="交易不存在或无权访问")

    # ── 关联审查记录 ───────────────────────────────────────────────────────────
    review = (
        db.query(ReviewItem)
        .filter(ReviewItem.transaction_id == transaction_id)
        .first()
    )

    now = datetime.now(timezone.utc)

    try:
        if body.action == "confirm":
            txn.needs_review = False
            if review:
                review.status = "confirmed"
                review.reviewed_at = now

            logger.info(
                f"review confirm | user={user_id} txn={transaction_id} "
                f"category={txn.category}"
            )

        elif body.action == "correct":
            old_category = txn.category
            txn.category = body.corrected_category.value
            txn.decision_source = "user_corrected"
            txn.needs_review = False
            txn.confidence = 1.0
            txn.evidence = f"用户手动纠正: {old_category} → {body.corrected_category.value}"

            if review:
                review.status = "corrected"
                review.corrected_category = body.corrected_category.value
                review.reviewed_at = now

            logger.info(
                f"review correct | user={user_id} txn={transaction_id} "
                f"{old_category} → {body.corrected_category.value}"
            )

        db.commit()

    except Exception as e:
        db.rollback()
        logger.error(f"审查写入失败: {e}")
        raise HTTPException(status_code=500, detail=f"审查更新失败: {str(e)}")

    return {"status": "updated", "transaction_id": transaction_id}
