"""
Six-layer classification pipeline orchestration (+ self-reflection).

Priority chain (core course principle: deterministic rules before LLM):
  Layer 1: Merchant map      conf=1.00  deterministic, zero cost
  Layer 2: Keyword rules     conf=0.85  deterministic, zero cost
  Layer 3: Subscription det. conf=0.90  heuristic, zero cost
  Layer 4: Similarity match  conf≤0.82  compute-intensive, zero LLM cost
  Layer 5: LLM fallback      conf varies  has cost, last resort
  Layer 6: Self-reflection   triggers on low confidence  extra LLM cost, improves quality

Improvements over previous version:
- Per-step structured trace: each layer appends to a `trace` list
- End-of-classification JSON log: full decision path, elapsed_ms, llm_invoked flag
- Latency monitoring: elapsed_ms recorded for every transaction

Course reference:
- Single-path Plan Generator (Day2) — fixed priority chain, no branching
- Guardrail (Day2/Day3)             — each layer has a confidence ceiling
- Explainability (XRAI)             — evidence field + trace for decision audit
"""
import json
import logging
import re
import time
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

    Emits a structured JSON log entry at completion with:
      - decision_layer, final_category, final_confidence
      - layers_traversed, llm_invoked, elapsed_ms
      - trace: per-layer hit/miss record
    """
    start_time = time.monotonic()
    trace: list = []          # per-layer decision record for observability

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
    trace.append({"layer": "merchant_map", "hit": result is not None,
                  "confidence": result[1] if result else None})
    if result:
        cat, conf, evidence = result
        logger.info("[L1 merchant_map] '%s' → %s", counterparty, cat.value)
        _log_complete(counterparty, cat.value, conf, "merchant_map", trace, start_time, llm_invoked=False)
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.MERCHANT_MAP)

    # ── Layer 2: Keyword rules ─────────────────────────────────────────────────
    result = match_keywords(counterparty, description)
    trace.append({"layer": "keyword_rules", "hit": result is not None,
                  "confidence": result[1] if result else None})
    if result:
        cat, conf, evidence = result
        logger.info("[L2 keyword_rule] '%s' → %s", counterparty, cat.value)
        _log_complete(counterparty, cat.value, conf, "keyword_rule", trace, start_time, llm_invoked=False)
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.KEYWORD_RULE)

    # ── Layer 3: Subscription detection ───────────────────────────────────────
    result = detect_subscription(counterparty, txn.amount, history)
    trace.append({"layer": "subscription", "hit": result is not None,
                  "confidence": result[1] if result else None})
    if result:
        cat, conf, evidence = result
        logger.info("[L3 subscription] '%s' → %s", counterparty, cat.value)
        _log_complete(counterparty, cat.value, conf, "subscription", trace, start_time, llm_invoked=False)
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.SUBSCRIPTION)

    # ── Layer 4: Similarity matching ───────────────────────────────────────────
    result = similarity_matcher.match(counterparty, description)
    trace.append({"layer": "similarity", "hit": result is not None,
                  "confidence": result[1] if result else None})
    if result:
        cat, conf, evidence = result
        logger.info("[L4 similarity] '%s' → %s conf=%.2f", counterparty, cat.value, conf)
        _log_complete(counterparty, cat.value, conf, "similarity", trace, start_time, llm_invoked=False)
        return _build_result(txn, cat, conf, evidence, DecisionSourceEnum.SIMILARITY)

    # ── Layer 5: LLM fallback ──────────────────────────────────────────────────
    cat, rationale, conf = await llm_classify(counterparty, description)
    source = DecisionSourceEnum.LLM
    trace.append({"layer": "llm", "hit": True, "confidence": conf})
    logger.info("[L5 llm] '%s' → %s conf=%.2f", counterparty, cat.value, conf)

    # ── Layer 6: Self-reflection (triggered only on low confidence) ────────────
    if conf < CONFIDENCE_THRESHOLD and not _is_low_information_input(counterparty, description):
        logger.info(
            "[L6 reflection] Triggering self-reflection: '%s' conf=%.2f < %.2f",
            counterparty, conf, CONFIDENCE_THRESHOLD,
        )
        ref_cat, ref_conf, ref_rationale, rounds = await reflect_on_classification(
            counterparty=counterparty,
            description=description,
            previous_category=cat.value,
            previous_confidence=conf,
            previous_rationale=rationale,
        )
        trace.append({"layer": "reflection", "hit": ref_conf > conf,
                      "rounds": rounds, "confidence_before": conf, "confidence_after": ref_conf})
        if ref_conf > conf:
            cat, conf, rationale = ref_cat, ref_conf, ref_rationale
            source = DecisionSourceEnum.LLM_REFLECTED
            logger.info(
                "[L6 reflection] Improved: '%s' conf=%.2f (%d rounds)",
                counterparty, conf, rounds,
            )

    _log_complete(counterparty, cat.value, conf, source.value, trace, start_time, llm_invoked=True)
    return _build_result(txn, cat, conf, rationale, source)


# ── Helper: structured completion log ───────────────────────────────────────────
def _log_complete(
    counterparty: str,
    category: str,
    confidence: float,
    decision_layer: str,
    trace: list,
    start_time: float,
    llm_invoked: bool,
) -> None:
    elapsed_ms = round((time.monotonic() - start_time) * 1000, 1)
    logger.info(
        json.dumps({
            "event": "classification_complete",
            "counterparty": counterparty,
            "final_category": category,
            "final_confidence": round(confidence, 4),
            "decision_layer": decision_layer,
            "layers_traversed": len(trace),
            "llm_invoked": llm_invoked,
            "elapsed_ms": elapsed_ms,
            "trace": trace,
        }, ensure_ascii=False)
    )


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
