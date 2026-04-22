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
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.tools import tool

from schemas.transaction import CategoryEnum
from agents.categorization.config import (
    CATEGORIES_DISPLAY, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE, PROMPT_VERSION
)

logger = logging.getLogger("categorization.llm")

# Ensure .env is loaded even if uvicorn is started from a different cwd.
BACKEND_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(BACKEND_ROOT / ".env", override=False)


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
2. category must be exactly one of the category names listed above
3. subcategory is optional — a more specific sub-label (e.g. "milk tea", "taxi"); use null if none
4. rationale: one sentence explaining the classification reasoning, and it must be grounded in exact words from input
5. confidence range 0.0-1.0; use below 0.6 when uncertain — do NOT inflate scores
6. Do not infer category from amount size — base decision solely on merchant name and description
7. If evidence from input is insufficient, return category="Other", confidence<=0.4, rationale="Insufficient evidence from input"
8. Never fabricate items not present in input (e.g. do not invent "milk tea" if not mentioned)

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


# ── LLM factory: Ollama preferred, then OpenAI, then Groq fallback ───────────────
@lru_cache(maxsize=8)
def _get_llm_from_keys(ollama_base: str, ollama_model: str, openai_key: str, groq_key: str):
    """
    Returns an available LLM instance.
    Prefers Ollama (local); falls back to OpenAI, then Groq.
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

    # Priority 1: Ollama (local LLM)
    if ollama_base and ollama_model:
        try:
            from langchain_openai import ChatOpenAI
            http_client, http_async_client = _build_http_clients()
            logger.debug(f"LLM path: Ollama {ollama_model} at {ollama_base}")
            return ChatOpenAI(
                model=ollama_model,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                openai_api_key="ollama",  # Ollama doesn't require a real key
                openai_api_base=f"{ollama_base}/v1",
                http_client=http_client,
                http_async_client=http_async_client,
            )
        except ImportError:
            logger.warning("langchain_openai not installed; skipping Ollama")
        except Exception as e:
            logger.warning(f"Ollama initialization failed: {e}")

    # Priority 2: OpenAI
    if openai_key and openai_key != "sk-xxx":
        logger.debug("LLM path: OpenAI gpt-4o-mini")
        return _build_openai(openai_key)
    
    # Priority 3: Groq
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
        logger.warning("No valid LLM provider detected; LLM fallback disabled")
        return None


def _sanitize_key(raw: Optional[str]) -> str:
    if not raw:
        return ""
    # Accept keys with accidental spaces/quotes in .env
    return raw.strip().strip('"').strip("'")


def _get_llm():
    """Resolve provider with runtime env values: Ollama first, then OpenAI, then Groq fallback."""
    ollama_base = os.getenv("OLLAMA_BASE_URL", "").strip()
    ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
    openai_key = _sanitize_key(os.getenv("OPENAI_API_KEY", ""))
    groq_key = _sanitize_key(os.getenv("GROQ_API_KEY", ""))
    return _get_llm_from_keys(ollama_base, ollama_model, openai_key, groq_key)


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
    try:
        other_label = CategoryEnum.OTHER.value
        llm = _get_llm()
        if llm is None:
            return (CategoryEnum.OTHER, "LLM unavailable: no valid provider configured", 0.3)

        chain = CLASSIFY_PROMPT | llm | JsonOutputParser()
        result = await chain.ainvoke({
            "categories": CATEGORIES_DISPLAY,
            "counterparty": counterparty,
            "description": description or "No description",
        })

        # ── Output validation (Guardrail) ─────────────────────────────────────
        cat_str = result.get("category", other_label)
        valid_cats = {e.value for e in CategoryEnum}
        if cat_str not in valid_cats:
            logger.warning(
                f"LLM returned invalid category '{cat_str}', downgrading to '{other_label}'."
                f" counterparty={counterparty}"
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
                has_valid_evidence = counterparty.lower() in rationale.lower() or (description or "").lower() in rationale.lower()

            if not has_valid_evidence:
                logger.warning(
                    f"LLM evidence guard triggered, downgrade to OTHER. counterparty={counterparty} rationale={rationale}"
                )
                cat_str = other_label
                confidence = min(confidence, 0.35)
                rationale = "Insufficient evidence from input"
                subcategory = None

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
