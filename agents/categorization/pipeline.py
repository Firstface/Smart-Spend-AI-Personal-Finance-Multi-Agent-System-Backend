"""
四层分类管线编排（+ 自反思）。

优先级链（课程核心原则：确定性优先于 LLM）：
  Layer 1: 商家映射     conf=1.00  确定性，零成本
  Layer 2: 关键词规则   conf=0.85  确定性，零成本
  Layer 3: 订阅检测     conf=0.90  启发式，零成本
  Layer 4: 相似度匹配   conf≤0.82  计算密集，零 LLM 成本
  Layer 5: LLM 回退    conf 不定   有成本，最后手段
  Layer 6: 自反思      仅低置信触发  额外 LLM 成本，提升质量

课程对应：
- Single-path Plan Generator（Day2）— 固定优先级链，无分支
- Guardrail（Day2/Day3）           — 每层有置信度上限，LLM 不能伪装成高确定规则
- 可解释性（XRAI）                 — evidence 字段记录决策来源
"""
import logging
from typing import List, Optional

from schemas.transaction import (
    TransactionRaw, CategorizedTransaction,
    CategoryEnum, DecisionSourceEnum, DirectionEnum,
)
from agents.categorization.rules.merchant_map import match_merchant
from agents.categorization.rules.keyword_rules import match_keywords
from agents.categorization.rules.subscription import detect_subscription
from agents.categorization.similarity.matcher import SimilarityMatcher
from agents.categorization.llm.classifier import llm_classify
from agents.categorization.reflection import reflect_on_classification
from agents.categorization.config import CONFIDENCE_THRESHOLD

logger = logging.getLogger("categorization.pipeline")


# ── 单条交易分类 ────────────────────────────────────────────────────────────────
async def classify_single(
    txn: TransactionRaw,
    history: List[CategorizedTransaction],
    similarity_matcher: SimilarityMatcher,
) -> CategorizedTransaction:
    """
    对单条交易跑完整六层管线。
    中性交易（退款/充值）直接返回 OTHER，不进入管线。
    """
    # 中性交易不参与分类
    if txn.direction == DirectionEnum.NEUTRAL:
        return _build_result(
            txn,
            CategoryEnum.OTHER,
            confidence=1.0,
            evidence="中性交易（退款/充值等），不参与分类",
            source=DecisionSourceEnum.MERCHANT_MAP,
        )

    counterparty = txn.counterparty or ""
    description = txn.goods_description or ""

    # ── Layer 1: 商家映射 ──────────────────────────────────────────────────────
    result = match_merchant(counterparty)
    if result:
        cat, conf, evidence = result
        logger.info(f"[L1 merchant_map] '{counterparty}' → {cat.value}")
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.MERCHANT_MAP)

    # ── Layer 2: 关键词规则 ────────────────────────────────────────────────────
    result = match_keywords(counterparty, description)
    if result:
        cat, conf, evidence = result
        logger.info(f"[L2 keyword_rule] '{counterparty}' → {cat.value}")
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.KEYWORD_RULE)

    # ── Layer 3: 订阅检测 ──────────────────────────────────────────────────────
    result = detect_subscription(counterparty, txn.amount, history)
    if result:
        cat, conf, evidence = result
        logger.info(f"[L3 subscription] '{counterparty}' → {cat.value}")
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.SUBSCRIPTION)

    # ── Layer 4: 相似度匹配 ────────────────────────────────────────────────────
    result = similarity_matcher.match(counterparty, description)
    if result:
        cat, conf, evidence = result
        logger.info(f"[L4 similarity] '{counterparty}' → {cat.value} conf={conf:.2f}")
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.SIMILARITY)

    # ── Layer 5: LLM 回退 ─────────────────────────────────────────────────────
    cat, rationale, conf = await llm_classify(counterparty, description)
    source = DecisionSourceEnum.LLM
    logger.info(f"[L5 llm] '{counterparty}' → {cat.value} conf={conf:.2f}")

    # ── Layer 6: 自反思（仅低置信度触发）──────────────────────────────────────
    if conf < CONFIDENCE_THRESHOLD:
        logger.info(
            f"[L6 reflection] 触发自反思: '{counterparty}' conf={conf:.2f} < {CONFIDENCE_THRESHOLD}"
        )
        ref_cat, ref_conf, ref_rationale, rounds = await reflect_on_classification(
            counterparty=counterparty,
            description=description,
            previous_category=cat.value,
            previous_confidence=conf,
            previous_rationale=rationale,
        )
        if ref_conf > conf:
            cat, conf, rationale = ref_cat, ref_conf, ref_rationale
            source = DecisionSourceEnum.LLM_REFLECTED
            logger.info(
                f"[L6 reflection] 反思提升: '{counterparty}' "
                f"{conf:.2f}（{rounds}轮）"
            )

    return _build_result(txn, cat, conf, rationale, source)


# ── 辅助：构建输出对象 ──────────────────────────────────────────────────────────
def _build_result(
    txn: TransactionRaw,
    category: CategoryEnum,
    confidence: float,
    evidence: str,
    source: DecisionSourceEnum,
) -> CategorizedTransaction:
    return CategorizedTransaction(
        source=txn.source,
        transaction_time=txn.transaction_time,
        counterparty=txn.counterparty,
        goods_description=txn.goods_description,
        direction=txn.direction,
        amount=txn.amount,
        currency=txn.currency,
        payment_method=txn.payment_method,
        original_category=txn.original_category,
        category=category,
        confidence=round(confidence, 4),
        evidence=evidence,
        decision_source=source,
        needs_review=confidence < CONFIDENCE_THRESHOLD,
    )
