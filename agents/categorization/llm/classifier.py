"""
LLM fallback classifier (Layer 5).

Only invoked when all four preceding rule layers miss, minimising LLM cost.

Improvements over v1.2:
- Prompt v1.3: RGC (Role-Goal-Context) structure + 3 few-shot examples
- Input sanitization via guardrails.sanitize_field (LLM01 defence)
- Per-call timeout (asyncio.wait_for) + exponential-backoff retry

Course reference:
- Structured Output (Day2)          — JSON Schema constrained output
- Tool Use Pattern (Day2)           — LangChain Tool definition
- Few-Shot Prompting (Day2)         — 3 labelled examples in system prompt
- RGC Prompt Pattern (Day2)         — Role / Goal / Context sections
- Input Guardrail (Day2/Day3)       — sanitize_field before LLM call
- LLM06 Excessive Agency (Day3)     — LLM only returns suggestions, no side effects
- LLMSecOps prompt versioning       — PROMPT_VERSION for audit tracking

Dual LLM path:
- Primary:  OPENAI_API_KEY  → gpt-4o-mini
- Fallback: GROQ_API_KEY    → llama-3.1-8b-instant
"""
import asyncio
import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.tools import tool

from schemas.transaction import CategoryEnum
from agents.categorization.config import (
    CATEGORIES_DISPLAY, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE,
    PROMPT_VERSION, LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES,
)
from agents.categorization.guardrails import sanitize_field

logger = logging.getLogger("categorization.llm")

# Ensure .env is loaded even if uvicorn is started from a different cwd.
BACKEND_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(BACKEND_ROOT / ".env", override=False)


# ── Few-shot examples (embedded in system prompt) ────────────────────────────────
# Braces doubled so ChatPromptTemplate does not interpret them as template vars.
_FEW_SHOT_EXAMPLES = """
## Examples — follow this exact JSON format

Input: Merchant="美团外卖", Description="晚餐 汉堡"
Output: {{"category": "Food & Dining", "subcategory": "food delivery", "rationale": "美团外卖 is a Chinese food delivery app; 晚餐汉堡 confirms a meal purchase", "confidence": 0.95, "evidence_terms": ["美团外卖", "晚餐", "汉堡"]}}

Input: Merchant="Grab", Description="ride to Changi Airport"
Output: {{"category": "Transportation", "subcategory": "ride-hailing", "rationale": "Grab is a ride-hailing service; ride to airport confirms transport purpose", "confidence": 0.97, "evidence_terms": ["Grab", "ride"]}}

Input: Merchant="未知收款方", Description="转账"
Output: {{"category": "Other", "subcategory": null, "rationale": "Insufficient evidence from input to determine spending category", "confidence": 0.25, "evidence_terms": []}}
"""


# ── Prompt template v1.3 (RGC structure + few-shot) ─────────────────────────────
CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", f"""## Role
You are a personal expense categorization assistant specialised in Chinese/English mixed transactions (prompt version {PROMPT_VERSION}).

## Goal
Given a merchant name and goods description, return the single most accurate spending category from the allowed list. Base your decision ONLY on evidence present in the input — never infer from amount size or assumed context.

## Context
Allowed categories: {{categories}}
User locale: mixed Chinese / English

## Constraints
1. Output JSON only — no other text
2. category must be exactly one of the category names listed above
3. subcategory is optional (e.g. "food delivery", "taxi"); use null if not evident from input
4. rationale: one sentence grounded in exact words from the input
5. confidence range 0.0–1.0; use below 0.6 when uncertain — do NOT inflate scores
6. evidence_terms: list the specific words from the INPUT that justify your choice
7. If evidence is insufficient, return category="Other", confidence≤0.4
8. Never fabricate details not present in the input

{_FEW_SHOT_EXAMPLES}

Output format (strict JSON):
{{{{"category": "...", "subcategory": "...", "rationale": "...", "confidence": 0.0, "evidence_terms": ["..."]}}}}"""),
    ("human", "Merchant: {{counterparty}}\nGoods description: {{description}}"),
])


# ── LangChain Tool definition (discoverable by Orchestrator) ────────────────────
@tool
def classify_transaction_tool(counterparty: str, description: str) -> dict:
    """Use LLM to classify a transaction that couldn't be matched by rules. Input merchant name and goods description, returns classification result."""
    # Actual logic executed asynchronously via llm_classify()
    pass


# ── LLM factory: OpenAI preferred, Groq fallback ───────────────────────────────
@lru_cache(maxsize=1)
def _build_http_clients() -> tuple[httpx.Client, httpx.AsyncClient]:
    sync_client = httpx.Client(trust_env=False)
    async_client = httpx.AsyncClient(trust_env=False)
    return sync_client, async_client


@lru_cache(maxsize=8)
def _get_llm_from_keys(openai_key: str, groq_key: str):
    """
    Returns an available LLM instance.
    Prefers gpt-4o-mini (OpenAI); falls back to llama-3.1-8b-instant (Groq) if no key.
    """
    def _build_openai(api_key: Optional[str] = None):
        from langchain_openai import ChatOpenAI
        http_client, http_async_client = _build_http_clients()
        return ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            api_key=api_key,
            http_client=http_client,
            http_async_client=http_async_client,
        )

    if openai_key and openai_key != "sk-xxx":
        logger.debug("LLM path: OpenAI gpt-4o-mini")
        return _build_openai(openai_key)
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
            logger.warning("langchain_groq not installed; trying OpenAI fallback")
            if openai_key and openai_key != "sk-xxx":
                return _build_openai(openai_key)
            logger.warning("No valid OpenAI key available; LLM fallback disabled")
            return None
    else:
        logger.warning("No valid LLM key detected; LLM fallback disabled")
        return None


def _sanitize_key(raw: Optional[str]) -> str:
    if not raw:
        return ""
    return raw.strip().strip('"').strip("'")


def _get_llm():
    """Resolve provider with runtime env values: OpenAI first, then Groq fallback."""
    openai_key = _sanitize_key(os.getenv("OPENAI_API_KEY", ""))
    groq_key = _sanitize_key(os.getenv("GROQ_API_KEY", ""))
    return _get_llm_from_keys(openai_key, groq_key)


# ── Retry helper (exponential back-off, no extra dependency) ────────────────────
async def _invoke_with_timeout_retry(chain, params: dict) -> dict:
    """
    Invoke a LangChain chain with per-call timeout and exponential-backoff retry.

    Retries on asyncio.TimeoutError and ConnectionError (transient network issues).
    On final failure, raises the last exception so the caller can fall back gracefully.
    """
    last_err: Exception = RuntimeError("LLM call never attempted")
    for attempt in range(LLM_MAX_RETRIES):
        try:
            return await asyncio.wait_for(
                chain.ainvoke(params),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, ConnectionError) as exc:
            last_err = exc
            wait = 2 ** attempt  # 1 s, 2 s, …
            logger.warning(
                "LLM call attempt %d/%d failed (%s); retrying in %ds",
                attempt + 1, LLM_MAX_RETRIES, type(exc).__name__, wait,
            )
            if attempt < LLM_MAX_RETRIES - 1:
                await asyncio.sleep(wait)
    raise last_err


# ── Main classification function ─────────────────────────────────────────────────
async def llm_classify(
    counterparty: str,
    description: Optional[str],
) -> tuple[CategoryEnum, str, float]:
    """
    Constrained LLM classifier with input sanitization and output guardrails.
    Returns (CategoryEnum, rationale string, confidence float).

    Guardrails applied:
    - Input:  sanitize_field() truncates and detects prompt injection (LLM01)
    - Output: category validated against CategoryEnum; confidence clamped [0,1]
    - Output: evidence_terms must appear in original input (anti-hallucination)
    """
    try:
        other_label = CategoryEnum.OTHER.value
        llm = _get_llm()
        if llm is None:
            return (CategoryEnum.OTHER, "LLM unavailable: no valid provider configured", 0.3)

        # ── Input sanitization (LLM01 — Prompt Injection defence) ─────────────
        safe_counterparty = sanitize_field(counterparty, "counterparty")
        safe_description = sanitize_field(description, "description")

        chain = CLASSIFY_PROMPT | llm | JsonOutputParser()
        result = await _invoke_with_timeout_retry(chain, {
            "categories": CATEGORIES_DISPLAY,
            "counterparty": safe_counterparty,
            "description": safe_description or "No description",
        })

        # ── Output validation (Guardrail) ─────────────────────────────────────
        cat_str = result.get("category", other_label)
        valid_cats = {e.value for e in CategoryEnum}
        if cat_str not in valid_cats:
            logger.warning(
                "LLM returned invalid category '%s', downgrading to '%s'. counterparty=%s",
                cat_str, other_label, counterparty,
            )
            cat_str = other_label

        confidence = float(result.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        rationale = result.get("rationale", "LLM classification")
        subcategory = result.get("subcategory") or None

        # Evidence guard: model must cite terms that actually appear in input.
        observed_text = f"{counterparty} {description or ''}".lower()
        evidence_terms_raw = result.get("evidence_terms", [])
        evidence_terms = []
        if isinstance(evidence_terms_raw, list):
            evidence_terms = [str(t).strip().lower() for t in evidence_terms_raw if str(t).strip()]

        if cat_str != other_label:
            has_valid_evidence = False
            if evidence_terms:
                has_valid_evidence = any(term in observed_text for term in evidence_terms)
            else:
                has_valid_evidence = (
                    counterparty.lower() in rationale.lower()
                    or (description or "").lower() in rationale.lower()
                )

            if not has_valid_evidence:
                logger.warning(
                    "LLM evidence guard triggered, downgrade to OTHER. "
                    "counterparty=%s rationale=%s",
                    counterparty, rationale,
                )
                cat_str = other_label
                confidence = min(confidence, 0.35)
                rationale = "Insufficient evidence from input"
                subcategory = None

        logger.info(
            "llm_classify: '%s' → %s conf=%.2f prompt_ver=%s",
            counterparty, cat_str, confidence, PROMPT_VERSION,
        )

        if subcategory:
            rationale = f"[{subcategory}] {rationale}"

        return (CategoryEnum(cat_str), rationale, confidence)

    except (asyncio.TimeoutError, ConnectionError) as exc:
        logger.error("LLM call timed out / connection failed for '%s': %s", counterparty, exc)
        return (CategoryEnum.OTHER, f"LLM unavailable ({type(exc).__name__})", 0.3)
    except Exception as exc:
        logger.error("LLM classification failed: %s — %s", counterparty, exc)
        return (CategoryEnum.OTHER, f"LLM call failed: {str(exc)[:80]}", 0.3)
