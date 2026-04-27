"""
Categorization Agent main entry point.

Exposes two functions:
  run_batch(transactions, user_id, db)  — Batch classification (file upload flow)
  run_single(txn, user_id, db)          — Single classification (chat quick-entry flow)

Full Agent loop as per course (Day2 PPT Slide 17):
  1. Receive input
  2. Tool selection (rules / similarity / LLM)
  3. Execute
  4. Evaluate (self-reflection)
  5. Output + write to database

Production improvements:
  - Batch concurrency control: asyncio.Semaphore limits simultaneous LLM calls
  - graceful degradation: asyncio.gather(return_exceptions=True) so one failure
    does not abort the entire batch
"""
import asyncio
import uuid
import logging
from typing import List

from sqlalchemy.orm import Session

from database import SessionLocal
from schemas.transaction import (
    TransactionRaw, CategorizedTransaction,
    ClassificationResult, CategoryEnum, DirectionEnum,
    DecisionSourceEnum,
)
from agents.categorization.pipeline import classify_single
from agents.categorization.similarity.matcher import SimilarityMatcher
from agents.categorization.config import BATCH_CONCURRENCY
from models.transaction import Transaction
from models.review_queue import ReviewItem

logger = logging.getLogger("categorization.agent")


# ── Batch classification entry point ────────────────────────────────────────────
async def run_batch(
    transactions: List[TransactionRaw],
    user_id: str,
    db: Session,
) -> ClassificationResult:
    """
    Batch classification pipeline main function.
    1. Load user's historical transactions from DB as long-term memory
    2. Initialize similarity matcher with historical data
    3. Classify each transaction (neutral transactions are directly marked OTHER)
    4. Bulk-write to transactions + review_queue tables
    5. Return ClassificationResult
    """
    # ── Step 1: Load historical memory (Selective Memory Sharing) ──────────────
    history = _load_history(db, user_id)
    logger.info(f"Loaded {len(history)} historical transactions for user_id={user_id}")

    # ── Step 2: Initialize similarity matcher ──────────────────────────────────
    matcher = SimilarityMatcher()
    matcher.fit(history)

    # ── Step 3: Classify transactions concurrently (bounded by semaphore) ─────
    # Semaphore limits simultaneous LLM calls to avoid overwhelming providers.
    # return_exceptions=True prevents one failed transaction from aborting the batch.
    semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)

    async def _classify_bounded(txn):
        async with semaphore:
            return await classify_single(txn, history, matcher)

    raw_results = await asyncio.gather(
        *[_classify_bounded(txn) for txn in transactions],
        return_exceptions=True,
    )

    results: List[CategorizedTransaction] = []
    stats_by_source: dict = {}
    failed_count = 0

    for i, outcome in enumerate(raw_results):
        if isinstance(outcome, Exception):
            failed_count += 1
            logger.error(
                "Transaction %d/%d classification failed: %s",
                i + 1, len(transactions), outcome,
            )
            continue
        results.append(outcome)
        src = outcome.decision_source.value if hasattr(outcome.decision_source, "value") else outcome.decision_source
        stats_by_source[src] = stats_by_source.get(src, 0) + 1

    if failed_count:
        logger.warning("Batch: %d/%d transactions failed classification", failed_count, len(transactions))

    # ── Step 4: Write to database ──────────────────────────────────────────────
    review_queue = _save_batch(db, user_id, results)

    # ── Step 5: Audit log ──────────────────────────────────────────────────────
    logger.info(
        f"audit | agent=categorization action=batch_classify "
        f"user={user_id} total={len(results)} "
        f"review={len(review_queue)} by_source={stats_by_source}"
    )

    return ClassificationResult(
        categorized=results,
        review_queue=review_queue,
        stats=_build_stats(results, review_queue, stats_by_source),
    )


# ── Single classification entry point (chat quick-entry) ────────────────────────
async def run_single(
    txn: TransactionRaw,
    user_id: str,
    db: Session,
) -> CategorizedTransaction:
    """
    Single transaction classification pipeline.
    Reuses the same six-layer pipeline as batch, writes to database and returns result.
    """
    history = _load_history(db, user_id)
    matcher = SimilarityMatcher()
    matcher.fit(history)

    cat_txn = await classify_single(txn, history, matcher)
    _save_single(db, user_id, cat_txn)

    logger.info(
        f"audit | agent=categorization action=single_classify "
        f"user={user_id} counterparty='{cat_txn.counterparty}' "
        f"category={cat_txn.category} conf={cat_txn.confidence:.2f}"
    )
    return cat_txn


# ── Private helper functions ────────────────────────────────────────────────────
def _load_history(db: Session, user_id: str) -> List[CategorizedTransaction]:
    """Load confirmed historical transactions from DB (needs_review=False)."""
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.needs_review == False,
            Transaction.category.isnot(None),
        )
        .order_by(Transaction.transaction_time.desc())
        .limit(500)          # Cap at most recent 500 to avoid slow vectorization
        .all()
    )
    return [_orm_to_schema(r) for r in rows]


def _save_batch(
    db: Session,
    user_id: str,
    results: List[CategorizedTransaction],
) -> List[CategorizedTransaction]:
    """Bulk-write transactions and review_queue; returns the subset needing review.
    Uses an independent session to avoid connection timeout after long LLM calls.
    """
    review_queue = []
    fresh_db = SessionLocal()
    try:
        # Pass 1: insert + commit all transactions first
        review_needed: list = []
        for cat_txn in results:
            txn_id = uuid.uuid4()
            db_txn = Transaction(
                id=txn_id,
                user_id=user_id,
                source=cat_txn.source,
                transaction_time=cat_txn.transaction_time,
                counterparty=cat_txn.counterparty,
                goods_description=cat_txn.goods_description,
                direction=cat_txn.direction.value,
                amount=cat_txn.amount,
                currency=cat_txn.currency,
                payment_method=cat_txn.payment_method,
                original_category=cat_txn.original_category,
                category=cat_txn.category.value,
                confidence=cat_txn.confidence,
                evidence=cat_txn.evidence,
                decision_source=(
                    cat_txn.decision_source.value
                    if hasattr(cat_txn.decision_source, "value")
                    else cat_txn.decision_source
                ),
                needs_review=cat_txn.needs_review,
            )
            fresh_db.add(db_txn)
            cat_txn.id = str(txn_id)
            if cat_txn.needs_review:
                review_needed.append((txn_id, cat_txn))

        # Commit transactions first — FK constraint on review_queue requires
        # the referenced transaction rows to already be committed
        fresh_db.commit()

        # Pass 2: insert review_queue rows in a new transaction
        for txn_id, cat_txn in review_needed:
            fresh_db.add(ReviewItem(
                transaction_id=txn_id,
                user_id=user_id,
                suggested_category=cat_txn.category.value,
                confidence=cat_txn.confidence,
                evidence=cat_txn.evidence,
                status="pending",
            ))
            review_queue.append(cat_txn)

        if review_needed:
            fresh_db.commit()
    except Exception as e:
        fresh_db.rollback()
        logger.error(f"Batch database write failed: {e}")
        raise
    finally:
        fresh_db.close()
    return review_queue


def _save_single(
    db: Session,
    user_id: str,
    cat_txn: CategorizedTransaction,
) -> None:
    """Write a single transaction record to the database.

    To avoid FK timing issues, persist the transaction first, then add review_queue
    in a second DB step when needed.
    """
    try:
        txn_id = uuid.uuid4()
        db_txn = Transaction(
            id=txn_id,
            user_id=user_id,
            source=cat_txn.source,
            transaction_time=cat_txn.transaction_time,
            counterparty=cat_txn.counterparty,
            goods_description=cat_txn.goods_description,
            direction=cat_txn.direction.value,
            amount=cat_txn.amount,
            currency=cat_txn.currency,
            payment_method=cat_txn.payment_method,
            original_category=cat_txn.original_category,
            category=cat_txn.category.value,
            confidence=cat_txn.confidence,
            evidence=cat_txn.evidence,
            decision_source=(
                cat_txn.decision_source.value
                if hasattr(cat_txn.decision_source, "value")
                else cat_txn.decision_source
            ),
            needs_review=cat_txn.needs_review,
        )
        db.add(db_txn)
        # Step 1: commit transaction first so FK target definitely exists.
        db.commit()
        cat_txn.id = str(txn_id)

        # Step 2: write review_queue separately (if needed).
        if cat_txn.needs_review:
            try:
                db.add(ReviewItem(
                    transaction_id=txn_id,
                    user_id=user_id,
                    suggested_category=cat_txn.category.value,
                    confidence=cat_txn.confidence,
                    evidence=cat_txn.evidence,
                    status="pending",
                ))
                db.commit()
            except Exception as review_err:
                db.rollback()
                # Never fail quick-entry success response because review_queue write failed.
                logger.error(f"Review queue insert failed for transaction_id={txn_id}: {review_err}")
    except Exception as e:
        db.rollback()
        logger.error(f"Single transaction database write failed: {e}")
        raise


def _orm_to_schema(row: Transaction) -> CategorizedTransaction:
    """Convert ORM row to Pydantic model."""
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


def _build_stats(
    results: List[CategorizedTransaction],
    review_queue: List[CategorizedTransaction],
    by_source: dict,
) -> dict:
    llm_count = by_source.get("llm", 0) + by_source.get("llm_reflected", 0)
    return {
        "total": len(results),
        "expense": sum(1 for r in results if r.direction == DirectionEnum.EXPENSE),
        "income": sum(1 for r in results if r.direction == DirectionEnum.INCOME),
        "neutral": sum(1 for r in results if r.direction == DirectionEnum.NEUTRAL),
        "auto_classified": sum(1 for r in results if not r.needs_review),
        "needs_review": len(review_queue),
        "llm_fallback": llm_count,
        "by_source": by_source,
    }
