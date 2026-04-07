"""
LLM fallback classifier (Layer 5).

Only invoked when all four preceding rule layers miss, minimizing LLM cost.

Course reference:
- Structured Output (Day2)         — JSON Schema constrained output to prevent hallucinated categories
- Tool Use Pattern (Day2)           — LangChain Tool definition, discoverable by Orchestrator
- LLM06 Excessive Agency mitigation (Day3) — LLM only returns classification suggestions, no side effects
- LLMSecOps prompt versioning       — PROMPT_VERSION for tracking

Dual LLM path:
- Primary: OPENAI_API_KEY (gpt-4o-mini)
- Fallback: GROQ_API_KEY (llama-3.1-8b-instant) when no OpenAI key
"""
import os
import logging
from functools import lru_cache
from typing import Optional

import httpx

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.tools import tool

from schemas.transaction import CategoryEnum
from agents.categorization.config import (
    CATEGORIES_DISPLAY, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE, PROMPT_VERSION
)

logger = logging.getLogger("categorization.llm")


@lru_cache(maxsize=1)
def _build_http_clients() -> tuple[httpx.Client, httpx.AsyncClient]:
    # Disable environment proxy inheritance so httpx 0.28+ does not receive the
    # removed `proxies=` argument through LangChain/OpenAI internals.
    sync_client = httpx.Client(trust_env=False)
    async_client = httpx.AsyncClient(trust_env=False)
    return sync_client, async_client

# ── Prompt template (versioned) ─────────────────────────────────────────────────
CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", f"""You are a personal expense categorization assistant (prompt version {PROMPT_VERSION}).
Based on the merchant name and goods description, classify the transaction into one of the following categories:
{{categories}}

Strict requirements:
1. Output JSON only — no other text
2. category must be exactly one of the category names listed above (full Chinese name)
3. subcategory is optional — a more specific sub-label (e.g. "milk tea", "taxi"); use null if none
4. rationale: one sentence explaining the classification reasoning
5. confidence range 0.0-1.0; use below 0.6 when uncertain — do NOT inflate scores
6. Do not infer category from amount size — base decision solely on merchant name and description

Output format (strict JSON):
{{{{"category": "...", "subcategory": "...", "rationale": "...", "confidence": 0.0}}}}"""),
    ("human", "Merchant: {{counterparty}}\nGoods description: {{description}}"),
])


# ── LangChain Tool definition (discoverable by Orchestrator) ────────────────────
@tool
def classify_transaction_tool(counterparty: str, description: str) -> dict:
    """Use LLM to classify a transaction that couldn't be matched by rules. Input merchant name and goods description, returns classification result."""
    # Actual logic executed asynchronously via llm_classify()
    pass


# ── LLM factory: OpenAI preferred, Groq fallback ───────────────────────────────
def _get_llm():
    """
    Returns an available LLM instance.
    Prefers gpt-4o-mini (OpenAI); falls back to llama-3.1-8b-instant (Groq) if no key.
    """
    openai_key = os.getenv("OPENAI_API_KEY", "")
    groq_key = os.getenv("GROQ_API_KEY", "")

    if openai_key and openai_key != "sk-xxx":
        from langchain_openai import ChatOpenAI
        logger.debug("LLM path: OpenAI gpt-4o-mini")
        http_client, http_async_client = _build_http_clients()
        return ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            api_key=openai_key,
            http_client=http_client,
            http_async_client=http_async_client,
        )
    elif groq_key:
        try:
            from langchain_groq import ChatGroq
            logger.debug("LLM path: Groq llama-3.1-8b-instant")
            return ChatGroq(
                model="llama-3.1-8b-instant",
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                api_key=groq_key,
            )
        except ImportError:
            logger.warning("langchain_groq not installed, falling back to OpenAI (even with placeholder key)")
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=LLM_MODEL,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )
    else:
        from langchain_openai import ChatOpenAI
        logger.warning("No valid LLM key detected, using default OpenAI (may fail)")
        return ChatOpenAI(model=LLM_MODEL, temperature=LLM_TEMPERATURE, max_tokens=LLM_MAX_TOKENS)


# ── Main classification function ────────────────────────────────────────────────
async def llm_classify(
    counterparty: str,
    description: Optional[str],
) -> tuple[CategoryEnum, str, float]:
    """
    Constrained LLM classifier.
    Returns (CategoryEnum, rationale string, confidence float).

    Output guardrails:
    - category must be a valid CategoryEnum value; otherwise downgrades to OTHER
    - confidence is clamped to [0.0, 1.0]
    - On JSON parse failure, returns safe default (OTHER, conf=0.3)
    """
    llm = _get_llm()
    chain = CLASSIFY_PROMPT | llm | JsonOutputParser()

    try:
        result = await chain.ainvoke({
            "categories": CATEGORIES_DISPLAY,
            "counterparty": counterparty,
            "description": description or "No description",
        })

        # ── Output validation (Guardrail) ─────────────────────────────────────
        cat_str = result.get("category", "其他")
        valid_cats = {e.value for e in CategoryEnum}
        if cat_str not in valid_cats:
            logger.warning(
                f"LLM returned invalid category '{cat_str}', downgrading to '其他'."
                f" counterparty={counterparty}"
            )
            cat_str = "其他"

        confidence = float(result.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        rationale = result.get("rationale", "LLM classification")
        subcategory = result.get("subcategory") or None

        logger.info(
            f"llm_classify: '{counterparty}' → {cat_str} "
            f"conf={confidence:.2f} prompt_ver={PROMPT_VERSION}"
        )

        # Append subcategory to rationale; pipeline layer can extract it
        if subcategory:
            rationale = f"[{subcategory}] {rationale}"

        return (CategoryEnum(cat_str), rationale, confidence)

    except Exception as e:
        logger.error(f"LLM classification failed: {counterparty} — {e}")
        # Safe fallback: OTHER + low confidence to ensure review queue entry
        return (CategoryEnum.OTHER, f"LLM call failed: {str(e)[:80]}", 0.3)
