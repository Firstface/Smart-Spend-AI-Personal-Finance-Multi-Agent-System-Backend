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

# Obvious follow-up / insights requests based on a user's own spending history.
INSIGHTS_PHRASES_EN: tuple[str, ...] = (
    "spending summary",
    "summarize my spending",
    "summarise my spending",
    "analyze my spending",
    "analyse my spending",
    "my spending trend",
    "expense trend",
    "spending trend",
    "unusual spending",
    "unusual expense",
    "anomaly spending",
    "subscription summary",
    "recurring charges",
    "monthly spending",
    "monthly expense",
    "my expenses this month",
)

INSIGHTS_PHRASES_ZH: tuple[str, ...] = ()

# 查看逻辑 (View)
PLAN_VIEW_KEYWORDS = (
    "查看预算", "看看计划", "我的预算", "预算表", "计划表", "历史计划", "之前的预算",
    "view budget", "show my plan", "current budget", "my plans", "budget list"
)

# 生成逻辑 (Create)
PLAN_CREATE_KEYWORDS = (
    "做个预算", "开启计划", "规划一下", "生成预算", "开始理财",
    "create plan", "generate budget", "make a budget", "plan my month", "start planning"
)

# 优化/反馈逻辑 (Refine)
# 这里特别加入了“太高/太低/减少”等带有反馈性质的词
PLAN_REFINE_KEYWORDS = (
    "修改预算计划", "调整", "优化", "改一下", "太贵了", "调低", "减少支出", "重新规划",
    "adjust", "change", "refine", "too much", "lower the budget", "update plan"
)


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


def should_route_to_insights(message: str) -> bool:
    """
    True → hand off to Follow-up / Insights agent after quick expense entry fails.
    """
    raw = message.strip()
    if not raw:
        return False
    if _smalltalk(raw):
        return False

    low = _normalize_en(raw)
    if any(p in low for p in INSIGHTS_PHRASES_EN):
        return True

    # English-first heuristic for "my spending / expenses" analysis requests.
    has_personal_scope = any(
        phrase in low
        for phrase in ("my spending", "my expense", "my expenses", "this month", "recent spending")
    )
    has_analysis_intent = any(
        phrase in low
        for phrase in ("summary", "summarize", "summarise", "analyze", "analyse", "trend", "unusual", "subscription")
    )

    return has_personal_scope and has_analysis_intent


def _llm_education_intent(message: str) -> bool | None:
    """
    Returns True/False when the model responds; None on skip or error.
    """
    if os.getenv("CHAT_EDUCATION_LLM_ROUTER", "1").strip().lower() in ("0", "false", "no"):
        return None
    base_url = os.getenv("OPENAI_API_BASE", "").strip()
    key = os.getenv("OPENAI_API_KEY", "").strip() or ("ollama" if base_url else "")
    if not key or key == "sk-xxx":
        return None
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=key, base_url=base_url or None)
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

def should_route_to_planning(message: str) -> bool:
    """
    仿照大部队逻辑：判断是否交给 Planning Agent
    """
    msg = message.strip()
    if not msg:
        return False
    
    # 1. 排除闲聊 (Smalltalk)
    if _smalltalk(msg):
        return False
        
    # 2. 检查关键词匹配
    if _keyword_planning(msg):
        return True
        
    # 3. 检查是否像个问题（比如：我该怎么存钱？）
    if not _looks_question_like(msg):
        return False
        
    # 4. LLM 兜底路由 (可选)
    # 你可以修改之前的 _llm_education_intent，或者让 LLM 识别 "planning" 意图
    llm_intent = _llm_planning_intent(msg) 
    if llm_intent is not None:
        return llm_intent
        
    return False


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
    # --- 新增：优先级判定 ---
    # 如果命中了规划类的关键词（如“生成”、“做个”），即使有“预算”二字，也优先给 Planning
    if _keyword_planning(msg):
        return False
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

def _keyword_planning(message: str) -> bool:
    """内部工具：检查是否触发了规划相关的关键词"""
    low = message.lower().strip()
    # 只要命中了 查看、生成 或 优化 中的任何一个关键词，就返回 True
    all_planning_keywords = PLAN_VIEW_KEYWORDS + PLAN_CREATE_KEYWORDS + PLAN_REFINE_KEYWORDS
    return any(p in low for p in all_planning_keywords)

def _llm_planning_intent(message: str) -> bool | None:
    """
    Planning Agent 专属 LLM 路由。
    返回 True: 属于规划/查看/修改预算意图
    返回 False: 属于其他意图（包括闲聊、教育、支出分析等）
    返回 None: 跳过或出错
    """
    if os.getenv("CHAT_PLANNING_LLM_ROUTER", "1").strip().lower() in ("0", "false", "no"):
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
    
    # 针对 Planning Agent 的专项 System Prompt
    system = (
        "You are a router for a personal finance app.\n"
        'Reply with a single JSON object: {"intent":"planning"} or {"intent":"other"}.\n'
        'Use "planning" when the user wants to:\n'
        "- CREATE a new budget plan (e.g., 'Make a plan for next month')\n"
        "- VIEW current or past budget plans (e.g., 'Show my budget', 'What is my plan?')\n"
        "- REFINE/ADJUST a plan based on feedback (e.g., 'Too expensive', 'Lower my dining budget', 'This is wrong')\n"
        'Use "other" for general knowledge questions, spending analysis, greetings, or chitchat.'
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
        
        return intent == "planning"
    except Exception as e:
        logger.warning("planning intent LLM router failed: %s", e)
    return None
