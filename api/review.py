"""
POST /api/review/{transaction_id} — Human review (HITL — Human-in-the-Loop).

Course reference:
- Human-Reflection Pattern (Day2 PPT Slide 49)
- IMDA Human Involvement Level 3: AI makes suggestions, human makes final decision
- Long-term Memory (Day2): user corrections update the personalised merchant map,
  closing the learning loop so the agent improves over time.

Improvements:
- Learning loop: `correct` action writes to user_merchant_map (Layer 0 override)
- Persistent audit log: every review action is recorded in classification_audit_log
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.transaction import Transaction
from models.review_queue import ReviewItem
from models.user_merchant_map import UserMerchantMap
from models.audit_log import ClassificationAuditLog
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
    action="correct" → Overwrite with corrected_category, set confidence to 1.0,
                       and write the merchant→category mapping to user_merchant_map
                       so future uploads learn from this correction.
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
    old_category = txn.category     # capture before mutation

    try:
        if body.action == "confirm":
            txn.needs_review = False
            if review:
                review.status = "confirmed"
                review.reviewed_at = now

            logger.info(
                "review confirm | user=%s txn=%s category=%s",
                user_id, transaction_id, txn.category,
            )

        elif body.action == "correct":
            txn.category = body.corrected_category.value
            txn.decision_source = "user_corrected"
            txn.needs_review = False
            txn.confidence = 1.0
            txn.evidence = (
                f"Manually corrected by user: {old_category} → {body.corrected_category.value}"
            )

            if review:
                review.status = "corrected"
                review.corrected_category = body.corrected_category.value
                review.reviewed_at = now

            logger.info(
                "review correct | user=%s txn=%s %s → %s",
                user_id, transaction_id, old_category, body.corrected_category.value,
            )

            # ── Learning loop: personalised merchant map ────────────────────────
            # Write (or update) the user's merchant→category mapping so the agent
            # classifies this merchant correctly in all future uploads (Layer 0).
            merchant_key = (txn.counterparty or "").lower().strip()
            if merchant_key:
                existing = (
                    db.query(UserMerchantMap)
                    .filter_by(user_id=user_id, merchant_key=merchant_key)
                    .first()
                )
                if existing:
                    existing.category = body.corrected_category.value
                    existing.learn_count = (existing.learn_count or 0) + 1
                    logger.info(
                        "user_merchant_map updated | user=%s merchant='%s' → %s (count=%d)",
                        user_id, merchant_key, body.corrected_category.value, existing.learn_count,
                    )
                else:
                    db.add(UserMerchantMap(
                        user_id=user_id,
                        merchant_key=merchant_key,
                        category=body.corrected_category.value,
                    ))
                    logger.info(
                        "user_merchant_map created | user=%s merchant='%s' → %s",
                        user_id, merchant_key, body.corrected_category.value,
                    )

        db.commit()

        # ── Persistent audit log ───────────────────────────────────────────────
        # Written after the main commit so a failure here never rolls back the review.
        try:
            event_type = "human_confirmed" if body.action == "confirm" else "human_corrected"
            db.add(ClassificationAuditLog(
                transaction_id=transaction_id,
                user_id=user_id,
                event_type=event_type,
                decision_source=txn.decision_source,
                old_category=old_category,
                new_category=txn.category,
                confidence=txn.confidence,
                evidence=txn.evidence,
                actor="human",
            ))
            db.commit()
        except Exception as audit_err:
            db.rollback()
            logger.warning("Audit log write failed (non-fatal): %s", audit_err)

    except Exception as e:
        db.rollback()
        logger.error("Review write failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Review update failed: {str(e)}")

    return {"status": "updated", "transaction_id": transaction_id}
