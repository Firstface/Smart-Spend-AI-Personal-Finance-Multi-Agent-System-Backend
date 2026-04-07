"""
GET    /api/transactions              — Paginated query of classified transactions.
DELETE /api/transactions/{id}         — Delete a single transaction.
POST   /api/transactions/bulk-delete  — Delete multiple transactions by ID list.

Query parameters (GET):
  page     int   default 1
  size     int   default 20, max 100
  filter   str   all | review | reviewed
  search   str   fuzzy search by merchant name
  category str   filter by category (e.g. "餐饮美食")
"""
import logging
import uuid as uuid_module
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db
from models.transaction import Transaction
from models.review_queue import ReviewItem
from schemas.transaction import CategorizedTransaction, DirectionEnum
from api.deps import get_user_id

router = APIRouter(prefix="/api", tags=["transactions"])
logger = logging.getLogger("api.transactions")


# ── GET /api/transactions ────────────────────────────────────────────────────────
@router.get("/transactions")
def get_transactions(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    filter: Optional[str] = Query(default="all"),       # all | review | reviewed
    search: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Return classified transactions with pagination, supporting filter, search, and category options.
    Also returns aggregate statistics (unaffected by pagination).
    """
    # ── Build query ────────────────────────────────────────────────────────────
    q = db.query(Transaction).filter(Transaction.user_id == user_id)

    # Filter mode
    if filter == "review":
        q = q.filter(Transaction.needs_review == True)
    elif filter == "reviewed":
        q = q.filter(Transaction.needs_review == False)

    # Fuzzy merchant name search
    if search:
        q = q.filter(
            or_(
                Transaction.counterparty.ilike(f"%{search}%"),
                Transaction.goods_description.ilike(f"%{search}%"),
            )
        )

    # Category filter
    if category:
        q = q.filter(Transaction.category == category)

    # Total count
    total = q.count()

    # Sort + paginate
    items_orm = (
        q.order_by(Transaction.transaction_time.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = [_orm_to_schema(r) for r in items_orm]

    # ── Aggregate stats (based on all user data, unaffected by filters) ────────
    stats = _build_stats(db, user_id)

    logger.info(
        f"get_transactions | user={user_id} filter={filter} "
        f"search={search} page={page} total={total}"
    )

    return {
        "items": [i.model_dump() for i in items],
        "total": total,
        "page": page,
        "size": size,
        "stats": stats,
    }


# ── DELETE /api/transactions/{transaction_id} ────────────────────────────────────
@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Delete a single transaction (and its review_queue entry if present)."""
    txn = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == user_id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found or access denied")

    # Delete review_queue entry first (FK constraint)
    db.query(ReviewItem).filter(ReviewItem.transaction_id == transaction_id).delete(synchronize_session=False)
    db.delete(txn)
    db.commit()

    logger.info(f"delete_transaction | user={user_id} txn={transaction_id}")
    return Response(status_code=204)


# ── POST /api/transactions/bulk-delete ──────────────────────────────────────────
class BulkDeleteRequest(BaseModel):
    ids: List[str]


@router.post("/transactions/bulk-delete")
def bulk_delete_transactions(
    body: BulkDeleteRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Delete multiple transactions by ID list. Only deletes rows owned by the current user."""
    if not body.ids:
        return {"deleted": 0}

    # Verify ownership and collect valid IDs
    txns = (
        db.query(Transaction)
        .filter(Transaction.id.in_(body.ids), Transaction.user_id == user_id)
        .all()
    )
    valid_ids = [str(t.id) for t in txns]

    if valid_ids:
        db.query(ReviewItem).filter(
            ReviewItem.transaction_id.in_(valid_ids)
        ).delete(synchronize_session=False)
        db.query(Transaction).filter(
            Transaction.id.in_(valid_ids)
        ).delete(synchronize_session=False)
        db.commit()

    logger.info(f"bulk_delete | user={user_id} requested={len(body.ids)} deleted={len(valid_ids)}")
    return {"deleted": len(valid_ids)}


# ── Private helpers ─────────────────────────────────────────────────────────────
def _orm_to_schema(row: Transaction) -> CategorizedTransaction:
    return CategorizedTransaction(
        id=str(row.id),
        source=row.source,
        transaction_time=row.transaction_time,
        counterparty=row.counterparty,
        goods_description=row.goods_description,
        direction=row.direction,
        amount=row.amount,
        currency=row.currency or "CNY",
        payment_method=row.payment_method,
        original_category=row.original_category,
        category=row.category or "其他",
        confidence=row.confidence or 0.0,
        evidence=row.evidence or "",
        decision_source=row.decision_source or "merchant_map",
        needs_review=row.needs_review or False,
    )


def _build_stats(db: Session, user_id: str) -> dict:
    """Compute aggregate statistics for all of the user's transactions."""
    all_rows = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .all()
    )
    total = len(all_rows)
    if total == 0:
        return {
            "total": 0, "expense": 0, "income": 0, "neutral": 0,
            "auto_classified": 0, "needs_review": 0, "llm_fallback": 0,
            "by_source": {},
        }

    by_source: dict = {}
    expense = income = neutral = needs_review = llm_fallback = 0
    for r in all_rows:
        if r.direction == "expense":
            expense += 1
        elif r.direction == "income":
            income += 1
        else:
            neutral += 1
        if r.needs_review:
            needs_review += 1
        src = r.decision_source or "unknown"
        by_source[src] = by_source.get(src, 0) + 1
        if src in ("llm", "llm_reflected"):
            llm_fallback += 1

    return {
        "total": total,
        "expense": expense,
        "income": income,
        "neutral": neutral,
        "auto_classified": total - needs_review,
        "needs_review": needs_review,
        "llm_fallback": llm_fallback,
        "by_source": by_source,
    }
