"""
聊天快速记账模块。

用户在聊天框输入简短消费记录，系统自动提取商家和金额，
跑分类管线后写入数据库。

设计原则：
- 确定性正则优先，LLM 仅作回退（与分类管线一致）
- 失败时不猜测——返回明确的"无法识别"提示
- 解析后复用完整分类管线，不单独做分类

支持格式示例：
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
    reply_message: str  # 返回给聊天界面的文本（空时由 chat 路由填充）


# ── 金额匹配模式（按优先级排列）──────────────────────────────────────────────────
AMOUNT_PATTERNS = [
    # $12.80 或 ¥12.80 或 ￥12.80（货币符号在前）
    re.compile(r'[\$¥￥]\s*(\d{1,10}(?:\.\d{1,4})?)', re.I),
    # 12.80元 或 12.80块（货币单位在后）
    re.compile(r'(\d{1,10}(?:\.\d{1,4})?)\s*(?:元|块|rmb|sgd|usd)', re.I),
    # 行尾纯数字（兜底，避免误匹配年份/编号等）
    re.compile(r'(?<!\d)(\d{1,6}(?:\.\d{1,2})?)\s*$', re.I),
]


def try_regex_parse(message: str) -> Optional[QuickEntryResult]:
    """
    正则解析：尝试从短文本提取商家和金额。

    策略：
    1. 扫描所有金额模式，取第一个命中的位置
    2. 金额前的剩余文本作为商家（+可选描述）
    3. 分割：第一个词为商家，其余为描述
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

    # 金额前的文本作为商家+描述
    before = text[:amount_span[0]].strip()
    # 清理货币符号残留
    before = re.sub(r'[\$¥￥]', '', before).strip()
    # 清理常见连接词
    before = re.sub(r'\s*(花了|花|共|合计|总计|支付了|付了)\s*', ' ', before).strip()

    if not before:
        return None

    # 分割商家和描述
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
    LLM 解析：正则失败时的回退。
    用 gpt-4o-mini / Groq 从自然语言中提取结构化记账信息。
    """
    import os
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser

    # 复用分类器的 LLM 工厂
    from agents.categorization.llm.classifier import _get_llm

    prompt = ChatPromptTemplate.from_messages([
        ("system", """判断用户输入是否是一条简单的消费记账指令。

如果是，提取商家名和金额。
如果不是（提问、闲聊、数学计算等），返回 is_transaction=false。

只输出 JSON，不输出任何其他文字：
{{"is_transaction": true, "merchant": "商家名", "amount": 12.80, "currency": "CNY", "description": "可选描述"}}
或：
{{"is_transaction": false}}"""),
        ("human", "{message}"),
    ])

    try:
        llm = _get_llm()
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
    快速记账主入口：正则优先，LLM 回退。

    返回：
      success=True  → transaction 字段有值，调用方继续跑分类管线
      success=False → 不是记账指令，调用方返回通用回复
    """
    # Layer 1: 正则（零成本）
    result = try_regex_parse(message)
    if result:
        return result

    # Layer 2: LLM（有成本，仅正则失败时）
    result = await try_llm_parse(message)
    if result:
        return result

    # 不是记账指令
    return QuickEntryResult(
        success=False,
        transaction=None,
        reply_message="",  # 由 chat 路由处理通用消息
    )
