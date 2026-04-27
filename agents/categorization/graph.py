"""
LangGraph-based Categorization Agent — formal StateGraph implementation.

Translates the six-layer classification pipeline into a directed graph with:
  - CategorizationState  : typed state container (TypedDict)
  - Node functions       : one per pipeline layer (Tools in the Tool Use pattern)
  - Conditional edges    : skip remaining layers once a match is found
  - Self-reflection node : triggered only when LLM confidence is low

This file implements the architecture diagrams shown in the project report and
makes the agent's decision process inspectable via LangGraph's built-in tooling
(e.g. graph.get_graph().draw_mermaid()).

Course reference:
- Tool Use Pattern (Day2)            — each node is a discrete, callable tool
- Self-Reflection Pattern (Day2)     — reflect node with conditional re-entry
- Single-path Plan Generator (Day2)  — deterministic priority routing via edges
- LangGraph AgentState (Day2)        — CategorizationState as the shared memory

Usage (demonstration):
    from agents.categorization.graph import categorization_graph, CategorizationState

    initial_state: CategorizationState = {
        "counterparty": "美团外卖",
        "description": "晚餐",
        "amount": 35.0,
        "history": [],
        "similarity_matcher": None,
        "category": None,
        "confidence": 0.0,
        "evidence": "",
        "decision_source": "",
        "reflection_rounds": 0,
        "needs_review": False,
    }
    final_state = await categorization_graph.ainvoke(initial_state)
"""
from __future__ import annotations

import logging
from typing import TypedDict, Optional, List

from langgraph.graph import StateGraph, END

from agents.categorization.rules.merchant_map import match_merchant
from agents.categorization.rules.keyword_rules import match_keywords
from agents.categorization.rules.subscription import detect_subscription
from agents.categorization.similarity.matcher import SimilarityMatcher
from agents.categorization.llm.classifier import llm_classify
from agents.categorization.reflection import reflect_on_classification
from agents.categorization.config import CONFIDENCE_THRESHOLD
from schemas.transaction import CategorizedTransaction

logger = logging.getLogger("categorization.graph")


# ── Agent State ──────────────────────────────────────────────────────────────────
class CategorizationState(TypedDict):
    """
    Shared state container passed between all LangGraph nodes.

    Input fields are set once at graph entry.
    Output fields are progressively filled as nodes fire.
    """
    # ── Inputs (set at graph entry, read-only by nodes) ──────────────────────
    counterparty: str
    description: str
    amount: float
    history: List[CategorizedTransaction]
    similarity_matcher: Optional[SimilarityMatcher]

    # ── Outputs (populated incrementally by nodes) ────────────────────────────
    category: Optional[str]          # None until a layer produces a match
    confidence: float
    evidence: str
    decision_source: str
    reflection_rounds: int
    needs_review: bool               # set by finalize_node


# ── Node functions ───────────────────────────────────────────────────────────────

def merchant_map_node(state: CategorizationState) -> CategorizationState:
    """Layer 1 — Deterministic merchant keyword lookup (conf = 1.0)."""
    result = match_merchant(state["counterparty"])
    if result:
        cat, conf, evidence = result
        logger.info("[graph:L1] merchant_map → %s", cat.value)
        return {**state, "category": cat.value, "confidence": conf,
                "evidence": evidence, "decision_source": "merchant_map"}
    return state


def keyword_rules_node(state: CategorizationState) -> CategorizationState:
    """Layer 2 — Regex keyword rules (conf = 0.85)."""
    result = match_keywords(state["counterparty"], state["description"])
    if result:
        cat, conf, evidence = result
        logger.info("[graph:L2] keyword_rule → %s", cat.value)
        return {**state, "category": cat.value, "confidence": conf,
                "evidence": evidence, "decision_source": "keyword_rule"}
    return state


def subscription_node(state: CategorizationState) -> CategorizationState:
    """Layer 3 — Recurring-charge subscription detection (conf = 0.90)."""
    result = detect_subscription(
        state["counterparty"], state["amount"], state["history"]
    )
    if result:
        cat, conf, evidence = result
        logger.info("[graph:L3] subscription → %s", cat.value)
        return {**state, "category": cat.value, "confidence": conf,
                "evidence": evidence, "decision_source": "subscription"}
    return state


def similarity_node(state: CategorizationState) -> CategorizationState:
    """Layer 4 — TF-IDF character n-gram similarity (conf ≤ 0.82)."""
    matcher: Optional[SimilarityMatcher] = state.get("similarity_matcher")
    if matcher and matcher.is_fitted:
        result = matcher.match(state["counterparty"], state["description"])
        if result:
            cat, conf, evidence = result
            logger.info("[graph:L4] similarity → %s conf=%.2f", cat.value, conf)
            return {**state, "category": cat.value, "confidence": conf,
                    "evidence": evidence, "decision_source": "similarity"}
    return state


async def llm_node(state: CategorizationState) -> CategorizationState:
    """Layer 5 — LLM fallback (gpt-4o-mini / Groq llama-3.1-8b-instant)."""
    cat, rationale, conf = await llm_classify(
        state["counterparty"], state["description"]
    )
    logger.info("[graph:L5] llm → %s conf=%.2f", cat.value, conf)
    return {**state, "category": cat.value, "confidence": conf,
            "evidence": rationale, "decision_source": "llm"}


async def reflection_node(state: CategorizationState) -> CategorizationState:
    """
    Layer 6 — Self-reflection.

    Triggered only when LLM confidence is below CONFIDENCE_THRESHOLD.
    An independent reviewer LLM re-evaluates the classification and may:
      - Boost confidence if it agrees with the original result.
      - Override to a better category if it disagrees (and confidence improves).
      - Leave unchanged if no improvement is found (early termination).
    """
    ref_cat, ref_conf, ref_rationale, rounds = await reflect_on_classification(
        counterparty=state["counterparty"],
        description=state["description"],
        previous_category=state["category"],
        previous_confidence=state["confidence"],
        previous_rationale=state["evidence"],
    )
    if ref_conf > state["confidence"]:
        logger.info(
            "[graph:L6] reflection improved %.2f → %.2f (%d rounds)",
            state["confidence"], ref_conf, rounds,
        )
        return {**state, "category": ref_cat.value, "confidence": ref_conf,
                "evidence": ref_rationale, "decision_source": "llm_reflected",
                "reflection_rounds": rounds}
    logger.info("[graph:L6] reflection: no improvement (%d rounds)", rounds)
    return {**state, "reflection_rounds": rounds}


def finalize_node(state: CategorizationState) -> CategorizationState:
    """Set needs_review flag and ensure a fallback category exists."""
    category = state.get("category") or "Other"
    confidence = state.get("confidence", 0.0)
    return {
        **state,
        "category": category,
        "needs_review": confidence < CONFIDENCE_THRESHOLD,
    }


# ── Routing helpers ──────────────────────────────────────────────────────────────

def _route_or_advance(state: CategorizationState, next_node: str) -> str:
    """If a category has already been assigned, jump to finalize."""
    return "finalize" if state.get("category") else next_node


def _route_after_llm(state: CategorizationState) -> str:
    """After LLM: trigger reflection only for low-confidence results."""
    return "reflect" if state["confidence"] < CONFIDENCE_THRESHOLD else "finalize"


# ── Graph construction ───────────────────────────────────────────────────────────

def build_categorization_graph() -> StateGraph:
    """Build and return the compiled LangGraph StateGraph."""
    graph = StateGraph(CategorizationState)

    # Register nodes
    graph.add_node("merchant_map",  merchant_map_node)
    graph.add_node("keyword_rules", keyword_rules_node)
    graph.add_node("subscription",  subscription_node)
    graph.add_node("similarity",    similarity_node)
    graph.add_node("llm_classify",  llm_node)
    graph.add_node("reflect",       reflection_node)
    graph.add_node("finalize",      finalize_node)

    # Entry point
    graph.set_entry_point("merchant_map")

    # Conditional edges — each layer short-circuits to finalize on hit
    graph.add_conditional_edges(
        "merchant_map",
        lambda s: _route_or_advance(s, "keyword_rules"),
        {"finalize": "finalize", "keyword_rules": "keyword_rules"},
    )
    graph.add_conditional_edges(
        "keyword_rules",
        lambda s: _route_or_advance(s, "subscription"),
        {"finalize": "finalize", "subscription": "subscription"},
    )
    graph.add_conditional_edges(
        "subscription",
        lambda s: _route_or_advance(s, "similarity"),
        {"finalize": "finalize", "similarity": "similarity"},
    )
    graph.add_conditional_edges(
        "similarity",
        lambda s: _route_or_advance(s, "llm_classify"),
        {"finalize": "finalize", "llm_classify": "llm_classify"},
    )
    graph.add_conditional_edges(
        "llm_classify",
        _route_after_llm,
        {"reflect": "reflect", "finalize": "finalize"},
    )
    graph.add_edge("reflect",   "finalize")
    graph.add_edge("finalize",  END)

    return graph


# Compiled graph — importable as a drop-in replacement for pipeline.classify_single
categorization_graph = build_categorization_graph().compile()
