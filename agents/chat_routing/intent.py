"""
Heuristic + optional LLM routing: decide whether a chat message should go to the Education agent.

Team members can extend EDUCATION_PHRASES_EN / EDUCATION_PHRASES_ZH for keyword hits.
Set CHAT_EDUCATION_LLM_ROUTER=0 to disable the small classifier when keywords miss.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from agents.education.refusal import check_refusal

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

# Greetings / filler — never send to Education
_SMALLTALK_PATTERNS = re.compile(
    r"^(hi+|hello|hey|thanks|thank you|thx|ok+|okay|bye|goodbye|yo|sup)\b[\s!?.，。！？…]*$",
    re.I,
)
_SMALLTALK_ZH = re.compile(
    r"^(你好|在吗|谢谢|多谢|好的|嗯|嗯嗯|拜拜|再见|早上好|晚上好)[\s!?.，。！？…]*$",
)

# Obvious education / personal-finance learning (English substrings, lowercased text)
EDUCATION_PHRASES_EN: tuple[str, ...] = (
    "budget",
    "budgeting",
    "save money",
    "saving money",
    "emergency fund",
    "compound interest",
    "interest rate",
    "credit score",
    "credit card",
    "debt",
    "student loan",
    "financial literacy",
    "spending habit",
    "track expenses",
    "expense track",
    "401k",
    "ira",
    "inflation",
    "deductible",
    "tax bracket",
    "net worth",
    "pay yourself first",
    "living paycheck",
    "rainy day",
)

# Chinese substrings (original message)
EDUCATION_PHRASES_ZH: tuple[str, ...] = (
    "预算",
    "存钱",
    "储蓄",
    "理财",
    "复利",
    "利息",
    "债务",
    "欠债",
    "信用卡",
    "征信",
    "贷款",
    "省钱",
    "开销",
    "支出",
    "记账",
    "财商",
    "金融知识",
    "消费观",
    "零花钱",
    "应急金",
    "定投",
    "基金知识",
    "保险知识",
    "税务",
    "个税",
    "资产配置",
    "管钱",
)

_QUESTIONISH = re.compile(
    r"[\?？]|^(how|what|why|when|where|which|who|can you|could you|explain|define|difference between|tell me about)\b",
    re.I,
)
_QUESTIONISH_ZH = re.compile(r"^(什么|怎么|如何|为啥|为什么|是否|能不能|请问|请教|解释|介绍|讲讲)")


def _normalize_en(text: str) -> str:
    return " ".join(text.lower().split())


def _keyword_education(message: str) -> bool:
    raw = message.strip()
    if not raw:
        return False
    low = _normalize_en(raw)
    if any(p in low for p in EDUCATION_PHRASES_EN):
        return True
    if any(p in raw for p in EDUCATION_PHRASES_ZH):
        return True
    return False


def _smalltalk(message: str) -> bool:
    s = message.strip()
    if len(s) > 40:
        return False
    if _SMALLTALK_PATTERNS.match(s):
        return True
    if _SMALLTALK_ZH.match(s):
        return True
    return False


def _looks_question_like(message: str) -> bool:
    s = message.strip()
    if len(s) < 8:
        return False
    if _QUESTIONISH.search(s):
        return True
    if _QUESTIONISH_ZH.match(s):
        return True
    return False


def _llm_education_intent(message: str) -> bool | None:
    """
    Returns True/False when the model responds; None on skip or error.
    """
    if os.getenv("CHAT_EDUCATION_LLM_ROUTER", "1").strip().lower() in ("0", "false", "no"):
        return None
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key or key == "sk-xxx":
        return None
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=key)
    system = (
        "You route messages for a personal finance assistant app.\n"
        'Reply with a single JSON object: {"intent":"education"} or {"intent":"other"}.\n'
        'Use "education" when the user wants to LEARN general personal finance concepts '
        "(budgeting, saving, debt, credit, taxes, financial literacy, definitions, comparisons of concepts).\n"
        'Use "other" for greetings, chitchat, unrelated topics, coding, weather, jokes, '
        "or actionable commands that are not educational questions."
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=32,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message.strip()[:2000]},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        data = json.loads(text)
        intent = str(data.get("intent", "")).lower().strip()
        if intent == "education":
            return True
        if intent == "other":
            return False
    except Exception as e:
        logger.warning("education intent LLM router failed: %s", e)
    return None


def should_route_to_education(message: str) -> bool:
    """
    True → hand off to Education RAG agent (after quick expense entry already failed).
    """
    msg = message.strip()
    if not msg:
        return False
    if _smalltalk(msg):
        return False
    # Investment / product / personalized advice: always hand to Education so
    # check_refusal there returns a clear policy message (LLM router often labels these "other").
    should_refuse, _, _ = check_refusal(msg)
    if should_refuse:
        return True
    if _keyword_education(msg):
        return True
    if not _looks_question_like(msg):
        return False
    llm = _llm_education_intent(msg)
    if llm is not None:
        return llm
    return False
