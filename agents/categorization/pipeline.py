"""
Six-layer classification pipeline orchestration (+ self-reflection).

Priority chain (core course principle: deterministic rules before LLM):
  Layer 1: Merchant map      conf=1.00  deterministic, zero cost
  Layer 2: Keyword rules     conf=0.85  deterministic, zero cost
  Layer 3: Subscription det. conf=0.90  heuristic, zero cost
  Layer 4: Similarity match  conf≤0.82  compute-intensive, zero LLM cost
  Layer 5: LLM fallback      conf varies  has cost, last resort
  Layer 6: Self-reflection   triggers on low confidence  extra LLM cost, improves quality

Course reference:
- Single-path Plan Generator (Day2) — fixed priority chain, no branching
- Guardrail (Day2/Day3)             — each layer has a confidence ceiling;
                                      LLM cannot masquerade as a high-certainty rule
- Explainability (XRAI)             — evidence field records decision source
"""
import logging
import re
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


def _is_low_information_input(counterparty: str, description: str) -> bool:
    # Very short/generic identifiers like "song" or "data" with no description
    # should not trigger reflection over-correction.
    return (not description.strip()) and bool(re.fullmatch(r"[A-Za-z0-9_\-]{1,12}", counterparty.strip()))


# ── Single transaction classification ───────────────────────────────────────────
async def classify_single(
    txn: TransactionRaw,
    history: List[CategorizedTransaction],
    similarity_matcher: SimilarityMatcher,
) -> CategorizedTransaction:
    """
    Run the full six-layer pipeline on a single transaction.
    Neutral transactions (refunds/top-ups) return OTHER immediately without entering the pipeline.
    """
    # Neutral transactions are not classified
    if txn.direction == DirectionEnum.NEUTRAL:
        return _build_result(
            txn,
            CategoryEnum.OTHER,
            confidence=1.0,
            evidence="Neutral transaction (refund/top-up etc.), not classified",
            source=DecisionSourceEnum.MERCHANT_MAP,
        )

    counterparty = txn.counterparty or ""
    description = txn.goods_description or ""

    # ── Layer 1: Merchant map ──────────────────────────────────────────────────
    result = match_merchant(counterparty)
    if result:
        cat, conf, evidence = result
        logger.info(f"[L1 merchant_map] '{counterparty}' → {cat.value}")
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.MERCHANT_MAP)

    # ── Layer 2: Keyword rules ─────────────────────────────────────────────────
    result = match_keywords(counterparty, description)
    if result:
        cat, conf, evidence = result
        logger.info(f"[L2 keyword_rule] '{counterparty}' → {cat.value}")
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.KEYWORD_RULE)

    # ── Layer 3: Subscription detection ───────────────────────────────────────
    result = detect_subscription(counterparty, txn.amount, history)
    if result:
        cat, conf, evidence = result
        logger.info(f"[L3 subscription] '{counterparty}' → {cat.value}")
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.SUBSCRIPTION)

    # ── Layer 4: Similarity matching ───────────────────────────────────────────
    result = similarity_matcher.match(counterparty, description)
    if result:
        cat, conf, evidence = result
        logger.info(f"[L4 similarity] '{counterparty}' → {cat.value} conf={conf:.2f}")
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.SIMILARITY)

    # ── Layer 5: LLM fallback ──────────────────────────────────────────────────
    cat, rationale, conf = await llm_classify(counterparty, description)
    source = DecisionSourceEnum.LLM
    logger.info(f"[L5 llm] '{counterparty}' → {cat.value} conf={conf:.2f}")

    # ── Layer 6: Self-reflection (triggered only on low confidence) ────────────
    if conf < CONFIDENCE_THRESHOLD and not _is_low_information_input(counterparty, description):
        logger.info(
            f"[L6 reflection] Triggering self-reflection: '{counterparty}' conf={conf:.2f} < {CONFIDENCE_THRESHOLD}"
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
                f"[L6 reflection] Improved: '{counterparty}' "
                f"conf={conf:.2f} ({rounds} rounds)"
            )

    return _build_result(txn, cat, conf, rationale, source)


# ── Helper: build output object ─────────────────────────────────────────────────
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
