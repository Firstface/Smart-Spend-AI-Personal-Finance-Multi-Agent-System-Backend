"""
POST /api/review/{transaction_id} — Human review (HITL — Human-in-the-Loop).

Course reference:
- Human-Reflection Pattern (Day2 PPT Slide 49)
- IMDA Human Involvement Level 3: AI makes suggestions, human makes final decision
- User correction feedback is written back to the database as a continuous learning signal
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
    Confirm or correct the classification result for a transaction.

    action="confirm" → Accept AI classification, clear the needs_review flag
    action="correct" → Overwrite with corrected_category, set confidence to 1.0
    """
    # ── Find transaction ───────────────────────────────────────────────────────
    txn = (
        db.query(Transaction)
        .filter(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found or access denied")

    # ── Find associated review record ──────────────────────────────────────────
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
            txn.evidence = f"Manually corrected by user: {old_category} → {body.corrected_category.value}"

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
        logger.error(f"Review write failed: {e}")
        raise HTTPException(status_code=500, detail=f"Review update failed: {str(e)}")

    return {"status": "updated", "transaction_id": transaction_id}
