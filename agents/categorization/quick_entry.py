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


LOW_QUALITY_MERCHANT_PATTERNS = [
    re.compile(r"我|今天|刚刚|中午|晚上|早上|去|吃了|买了|花了|用了|付款|支付", re.I),
]


def _detect_amount(message: str) -> Optional[float]:
    text = message.strip()
    for pattern in AMOUNT_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            val = float(m.group(1))
            if val > 0:
                return val
        except ValueError:
            continue
    return None


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

    # Narrative sentence cleanup: keep core merchant phrase if present.
    narrative_match = re.search(r'(?:我|今天|刚刚|中午|晚上|早上)?(?:在|去)(.+?)(?:吃|买|消费|花|付|支付|点了)', before)
    if narrative_match:
        before = narrative_match.group(1).strip()

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
        ("system", """Determine whether the user input is a transaction entry for bookkeeping.

If yes:
1. Extract merchant as the most specific store/person/payee name.
2. Extract amount as a positive number.
3. Remove temporal or narrative fillers from merchant (e.g. 我/今天/中午/去/吃了/买了).
4. Put remaining useful context into description.

Examples:
- "我中午去重庆小面吃了碗30块钱的面" -> merchant="重庆小面", amount=30, description="中午吃了一碗面"
- "song 1" -> merchant="song", amount=1, description=null

If no (question, small talk, planning request, etc.), return is_transaction=false.

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

    # Validation guard: merchant should appear in source text; amount should align with input amount when present.
    source_text = message.strip().lower()
    if merchant.lower() not in source_text:
        logger.warning(f"LLM parse rejected: merchant not found in input. merchant='{merchant}' message='{message}'")
        return None

    expected_amount = _detect_amount(message)
    if expected_amount is not None and abs(expected_amount - amount) > 0.01:
        logger.warning(
            f"LLM parse rejected: amount mismatch. parsed={amount} expected={expected_amount} message='{message}'"
        )
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


def _is_low_quality_regex_result(message: str, result: QuickEntryResult) -> bool:
    if not result.transaction:
        return True

    merchant = (result.transaction.counterparty or "").strip()
    description = (result.transaction.goods_description or "").strip()

    if not merchant:
        return True

    # Narrative phrases often indicate regex captured too much context as merchant.
    if any(p.search(merchant) for p in LOW_QUALITY_MERCHANT_PATTERNS):
        return True

    # Very short raw inputs like "song 1" / "data 1" are better handled by LLM parser.
    if re.fullmatch(r"[A-Za-z0-9_\-\s]{1,12}", message.strip()) and not description:
        return True

    return False


async def parse_quick_entry(message: str) -> QuickEntryResult:
    """
    Quick-entry main entry point: regex first, LLM fallback.

    Returns:
      success=True  → transaction field is populated; caller runs classification pipeline
      success=False → not an expense entry command; caller returns a general reply
    """
    # Layer 1: regex (zero cost)
    regex_result = try_regex_parse(message)
    if regex_result and not _is_low_quality_regex_result(message, regex_result):
        return regex_result

    # Layer 2: LLM (has cost) — also used to override low-quality regex parses
    llm_result = await try_llm_parse(message)
    if llm_result:
        return llm_result

    # If regex succeeded but LLM failed/unavailable, keep regex result as graceful fallback.
    if regex_result:
        return regex_result

    # Not an expense entry command
    return QuickEntryResult(
        success=False,
        transaction=None,
        reply_message="",  # Handled by chat route for general messages
    )
