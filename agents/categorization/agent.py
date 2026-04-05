"""
分类 Agent 主入口。

对外暴露两个函数：
  run_batch(transactions, user_id, db)  — 批量分类（文件上传流程）
  run_single(txn, user_id, db)          — 单条分类（聊天快速记账流程）

课程对应的完整 Agent 循环（Day2 PPT Slide 17）：
  1. 接收输入
  2. 工具选择（规则 / 相似度 / LLM）
  3. 执行
  4. 评估（自反思）
  5. 输出 + 写入数据库
"""
import uuid
import logging
from typing import List

from sqlalchemy.orm import Session

from schemas.transaction import (
    TransactionRaw, CategorizedTransaction,
    ClassificationResult, CategoryEnum, DirectionEnum,
    DecisionSourceEnum,
)
from agents.categorization.pipeline import classify_single
from agents.categorization.similarity.matcher import SimilarityMatcher
from models.transaction import Transaction
from models.review_queue import ReviewItem

logger = logging.getLogger("categorization.agent")


# ── 批量分类入口 ────────────────────────────────────────────────────────────────
async def run_batch(
    transactions: List[TransactionRaw],
    user_id: str,
    db: Session,
) -> ClassificationResult:
    """
    批量分类管线主函数。
    1. 从数据库加载用户历史交易作为长期记忆
    2. 用历史数据初始化相似度匹配器
    3. 逐条分类（仅对支出/收入，中性直接标 OTHER）
    4. 批量写入 transactions + review_queue 表
    5. 返回 ClassificationResult
    """
    # ── Step 1: 加载历史记忆（Selective Memory Sharing）────────────────────────
    history = _load_history(db, user_id)
    logger.info(f"加载历史交易 {len(history)} 条 user_id={user_id}")

    # ── Step 2: 初始化相似度匹配器 ────────────────────────────────────────────
    matcher = SimilarityMatcher()
    matcher.fit(history)

    # ── Step 3: 逐条分类 ───────────────────────────────────────────────────────
    results: List[CategorizedTransaction] = []
    stats_by_source: dict = {}

    for txn in transactions:
        cat_txn = await classify_single(txn, history, matcher)
        results.append(cat_txn)
        src = cat_txn.decision_source.value if hasattr(cat_txn.decision_source, "value") else cat_txn.decision_source
        stats_by_source[src] = stats_by_source.get(src, 0) + 1

    # ── Step 4: 写入数据库 ─────────────────────────────────────────────────────
    review_queue = _save_batch(db, user_id, results)

    # ── Step 5: 审计日志 ───────────────────────────────────────────────────────
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


# ── 单条分类入口（聊天快速记账）──────────────────────────────────────────────────
async def run_single(
    txn: TransactionRaw,
    user_id: str,
    db: Session,
) -> CategorizedTransaction:
    """
    单条分类管线。
    复用与批量相同的六层管线，写入数据库后返回结果。
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


# ── 私有辅助函数 ────────────────────────────────────────────────────────────────
def _load_history(db: Session, user_id: str) -> List[CategorizedTransaction]:
    """从数据库加载用户已确认的历史交易（needs_review=False）"""
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.needs_review == False,
            Transaction.category.isnot(None),
        )
        .order_by(Transaction.transaction_time.desc())
        .limit(500)          # 最多取最近 500 条，避免向量化过慢
        .all()
    )
    return [_orm_to_schema(r) for r in rows]


def _save_batch(
    db: Session,
    user_id: str,
    results: List[CategorizedTransaction],
) -> List[CategorizedTransaction]:
    """批量写入 transactions 和 review_queue，返回需审查的子集"""
    review_queue = []
    try:
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
            db.add(db_txn)
            cat_txn.id = str(txn_id)

            if cat_txn.needs_review:
                db.add(ReviewItem(
                    transaction_id=txn_id,
                    user_id=user_id,
                    suggested_category=cat_txn.category.value,
                    confidence=cat_txn.confidence,
                    evidence=cat_txn.evidence,
                    status="pending",
                ))
                review_queue.append(cat_txn)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"批量写入数据库失败: {e}")
        raise
    return review_queue


def _save_single(
    db: Session,
    user_id: str,
    cat_txn: CategorizedTransaction,
) -> None:
    """写入单条交易记录"""
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

        if cat_txn.needs_review:
            db.add(ReviewItem(
                transaction_id=txn_id,
                user_id=user_id,
                suggested_category=cat_txn.category.value,
                confidence=cat_txn.confidence,
                evidence=cat_txn.evidence,
                status="pending",
            ))

        db.commit()
        cat_txn.id = str(txn_id)
    except Exception as e:
        db.rollback()
        logger.error(f"单条写入数据库失败: {e}")
        raise


def _orm_to_schema(row: Transaction) -> CategorizedTransaction:
    """ORM 行转 Pydantic 模型"""
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
