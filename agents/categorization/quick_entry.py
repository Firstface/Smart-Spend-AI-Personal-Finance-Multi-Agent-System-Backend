"""
Chat quick-entry module.

Users type a brief expense record in the chat box; the system automatically extracts
the merchant and amount, runs the classification pipeline, and writes to the database.

Design principles:
- Deterministic regex first; LLM only as fallback (consistent with classification pipeline)
- Do not guess on failure — return a clear "cannot parse" message
- After parsing, reuse the full classification pipeline rather than classifying separately

Supported input formats:
  "Grab $12.80"
  "FairPrice $45.60"
  "Netflix subscription $15.99"
  "午饭 美团 35元"
  "咖啡 18.5"
  "地铁 2.1"
"""
import re
import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from schemas.transaction import TransactionRaw, DirectionEnum

logger = logging.getLogger("categorization.quick_entry")


class QuickEntryResult(BaseModel):
    success: bool
    transaction: Optional[TransactionRaw] = None
    reply_message: str  # Text returned to the chat UI (empty string filled by chat route)


# ── Amount patterns (in priority order) ────────────────────────────────────────
AMOUNT_PATTERNS = [
    # $12.80 or ¥12.80 or ￥12.80 (currency symbol before amount)
    re.compile(r'[\$¥￥]\s*(\d{1,10}(?:\.\d{1,4})?)', re.I),
    # 12.80元 or 12.80块 (currency unit after amount)
    re.compile(r'(\d{1,10}(?:\.\d{1,4})?)\s*(?:元|块|rmb|sgd|usd)', re.I),
    # Trailing bare number (fallback — avoids matching years/IDs)
    re.compile(r'(?<!\d)(\d{1,6}(?:\.\d{1,2})?)\s*$', re.I),
]


def try_regex_parse(message: str) -> Optional[QuickEntryResult]:
    """
    Regex parsing: attempt to extract merchant and amount from short text.

    Strategy:
    1. Scan all amount patterns; take the first match position
    2. Text before the amount is treated as merchant (+ optional description)
    3. Split: first token = merchant, remainder = description
    """
    text = message.strip()

    amount: Optional[float] = None
    amount_span: Optional[tuple] = None

    for pattern in AMOUNT_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                val = float(m.group(1))
                if val > 0:
                    amount = val
                    amount_span = m.span()
                    break
            except ValueError:
                continue

    if amount is None:
        return None

    # Text before the amount is merchant + description
    before = text[:amount_span[0]].strip()
    # Strip residual currency symbols
    before = re.sub(r'[\$¥￥]', '', before).strip()
    # Strip common connective words
    before = re.sub(r'\s*(花了|花|共|合计|总计|支付了|付了)\s*', ' ', before).strip()

    if not before:
        return None

    # Split merchant and description
    parts = before.split(maxsplit=1)
    merchant = parts[0].strip()
    description = parts[1].strip() if len(parts) > 1 else None

    if not merchant or len(merchant) < 1:
        return None

    txn = TransactionRaw(
        source="manual",
        transaction_time=datetime.now(),
        counterparty=merchant,
        goods_description=description,
        direction=DirectionEnum.EXPENSE,
        amount=amount,
        currency="CNY",
    )
    logger.info(f"regex parse: '{message}' → merchant='{merchant}' amount={amount}")
    return QuickEntryResult(success=True, transaction=txn, reply_message="")


async def try_llm_parse(message: str) -> Optional[QuickEntryResult]:
    """
    LLM parsing: fallback when regex fails.
    Uses gpt-4o-mini / Groq to extract structured accounting info from natural language.
    """
    import os
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser

    # Reuse classifier's LLM factory
    from agents.categorization.llm.classifier import _get_llm

    prompt = ChatPromptTemplate.from_messages([
        ("system", """Determine whether the user input is a simple expense entry command.

If yes, extract the merchant name and amount.
If no (question, small talk, math, etc.), return is_transaction=false.

Output JSON only — no other text:
{{"is_transaction": true, "merchant": "merchant name", "amount": 12.80, "currency": "CNY", "description": "optional description"}}
or:
{{"is_transaction": false}}"""),
        ("human", "{message}"),
    ])

    try:
        llm = _get_llm()
        if llm is None:
            logger.warning("Quick-entry LLM parse skipped: no available LLM provider")
            return None

        chain = prompt | llm | JsonOutputParser()
        result = await chain.ainvoke({"message": message})
    except Exception as e:
        logger.error(f"LLM parse failed: {e}")
        return None

    if not result.get("is_transaction", False):
        return None

    merchant = str(result.get("merchant", "")).strip()
    amount_raw = result.get("amount", 0)
    try:
        amount = float(amount_raw)
    except (ValueError, TypeError):
        return None

    if not merchant or amount <= 0:
        return None

    txn = TransactionRaw(
        source="manual",
        transaction_time=datetime.now(),
        counterparty=merchant,
        goods_description=result.get("description") or None,
        direction=DirectionEnum.EXPENSE,
        amount=amount,
        currency=result.get("currency", "CNY"),
    )
    logger.info(f"llm parse: '{message}' → merchant='{merchant}' amount={amount}")
    return QuickEntryResult(success=True, transaction=txn, reply_message="")


async def parse_quick_entry(message: str) -> QuickEntryResult:
    """
    Quick-entry main entry point: regex first, LLM fallback.

    Returns:
      success=True  → transaction field is populated; caller runs classification pipeline
      success=False → not an expense entry command; caller returns a general reply
    """
    # Layer 1: regex (zero cost)
    result = try_regex_parse(message)
    if result:
        return result

    # Layer 2: LLM (has cost, only when regex fails)
    result = await try_llm_parse(message)
    if result:
        return result

    # Not an expense entry command
    return QuickEntryResult(
        success=False,
        transaction=None,
        reply_message="",  # Handled by chat route for general messages
    )
