import re
from typing import Tuple

# Questions containing these substrings are allowed through (educational / saving context).
SAFE_PHRASES = [
    "emergency fund",
    "saving fund",
]

# English: buying / picking / timing investments (substring match on normalized text).
INVESTMENT_ADVICE_SUBSTRINGS_EN: tuple[str, ...] = (
    "buy stock",
    "buy stocks",
    "buy a stock",
    "buy shares",
    "buy share",
    "buy an etf",
    "buy etf",
    "buy etfs",
    "buying stock",
    "buying stocks",
    "buying an etf",
    "buying etf",
    "buying etfs",
    "buy bond",
    "buy bonds",
    "buy crypto",
    "buy bitcoin",
    "buy ethereum",
    "sell my stock",
    "sell my stocks",
    "sell stock",
    "sell stocks",
    "which stock",
    "what stock",
    "pick a stock",
    "picking stocks",
    "stock picks",
    "stock pick",
    "stock tip",
    "stock tips",
    "recommend a stock",
    "recommend stocks",
    "recommend an etf",
    "recommend etf",
    "recommend etfs",
    "good stock to",
    "best stock to",
    "stocks to buy",
    "stock to buy",
    "shares to buy",
    "ticker to buy",
    "what to invest",
    "where to invest",
    "how much to invest in",
    "portfolio allocation",
    "rebalance my",
    "my portfolio",
    "asset allocation",
    "market timing",
    "time the market",
    "beat the market",
    "get rich",
    "maximize return",
    "maximise return",
    "high return",
    "passive income from invest",
    "dividend stock",
    "growth stock",
    "value stock",
    "day trade",
    "day trading",
    "swing trade",
    "options trade",
    "call option",
    "put option",
    "forex trade",
    "margin trade",
    "leverage trade",
    "ipo buy",
    "buy ipo",
    "short sell",
    "shorting ",
    "robo-advisor",
    "robo advisor",
    "which broker",
    "best broker",
    "open a brokerage",
)

# Chinese: 购买/推荐/选股等理财投资实操咨询（子串匹配，不依赖分词）。
INVESTMENT_ADVICE_SUBSTRINGS_ZH: tuple[str, ...] = (
    "买股票",
    "买哪只股票",
    "买什么股票",
    "买港股",
    "买美股",
    "买a股",
    "选股",
    "荐股",
    "推荐股票",
    "推荐个股",
    "炒股",
    "怎么炒股",
    "如何炒股",
    "股票推荐",
    "股票该买",
    "股票能买",
    "抄底",
    "追涨",
    "加仓",
    "减仓",
    "止损",
    "止盈",
    "买基金",
    "买什么基金",
    "买哪只基金",
    "哪只基金好",
    "哪个基金好",
    "推荐基金",
    "推荐一只",
    "推荐个基金",
    "基金推荐",
    "基金定投",
    "定投哪只",
    "定投什么",
    "申购哪只",
    "认购哪只",
    "基金经理推荐",
    "买理财",
    "买什么理财",
    "哪个理财产品",
    "理财产品推荐",
    "推荐理财",
    "理财推荐",
    "保本理财",
    "高收益理财",
    "买比特币",
    "买以太坊",
    "买虚拟币",
    "买币",
    "炒币",
    "合约",
    "杠杆",
    "配资",
    "开户推荐",
    "哪个券商",
    "推荐券商",
    "荐基",
    "跟投",
    "财富自由",
    "快速致富",
    "暴富",
)

INVESTMENT_KEYWORDS = [
    "crypto",
    "cryptocurrency",
    "bitcoin",
    "ethereum",
    "bond",
    "bonds",
    "etf",
    "etfs",
    "trading",
    "investment",
    "investing",
    "invest",
    "forex",
    "futures",
    "options",
    "derivatives",
    "reit",
    "reits",
    "securities",
    "equities",
    "equity",
    "shares",
    "portfolio",
    "brokerage",
    "broker",
    "dividend",
    "ipo",
    "mutual fund",
    "index fund",
    "hedge fund",
    "unit trust",
    "401k",
    "ira",
    "roth",
    "tfsa",
    "rrsp",
]

PRODUCT_KEYWORDS = [
    "financial product",
    "insurance product",
    "wealth product",
    "best fund",
    "best etf",
    "best stock",
    "best investment product",
    "best insurance",
    "recommend a fund",
    "recommend a product",
    "recommend insurance",
    "which product",
    "which fund",
    "which insurance",
    "which policy",
    "good fund",
    "good etf",
    "理财产品",
    "保险推荐",
    "推荐保险",
    "哪个保险",
    "买什么保险",
    "定投产品",
]

PERSONALIZED_DECISION_PATTERNS = [
    "should i invest",
    "should i buy",
    "should i sell",
    "should i hold",
    "what should i buy",
    "what should i sell",
    "where should i invest",
    "which stock should i buy",
    "which fund should i buy",
    "which etf should",
    "is it a good time to buy",
    "worth buying",
    "what is the best investment",
    "what should i do with my money",
    "how can i get rich fast",
    "fastest way to become rich",
    "how to maximize returns",
    "how to maximise returns",
    "highest returns",
    "我该买",
    "要不要买",
    "能不能买",
    "适合买吗",
    "值得买吗",
    "现在能买吗",
    "该卖吗",
    "要卖吗",
    "钱该怎么投",
    "钱放哪",
]


MSG_PERSONALIZED = (
    "Sorry, I cannot answer personalized investment or wealth-management decisions "
    "(for example what to buy or sell, timing the market, or what to do with your money). "
    "I only provide general education on budgeting, saving, spending habits, and basic money concepts."
)

MSG_PRODUCT = (
    "Sorry, I cannot recommend specific financial or wealth products "
    "(such as particular stocks, funds, ETFs, insurance, or platforms). "
    "I only provide general educational information."
)

MSG_INVESTMENT = (
    "Sorry, I cannot provide investment or trading advice "
    "(including stocks, funds, crypto, bonds, portfolios, or similar). "
    "I can help with general personal-finance education—for example budgeting, saving, and everyday money habits."
)


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def contains_phrase(text: str, phrases: list[str] | tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _zh_recommends_fund_or_product(text: str) -> bool:
    """Chinese: 推荐…基金 / 基金…推荐 (spacing between chars is OK)."""
    if re.search(r"推荐.{0,18}基金", text):
        return True
    if re.search(r"基金.{0,12}推荐", text):
        return True
    return False


def contains_whole_word(text: str, words: list[str]) -> bool:
    for word in words:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, text):
            return True
    return False


# Skip broad whole-word investment matches for obvious "concept / definition" questions.
_EDUCATION_QUESTION_PREFIXES: tuple[str, ...] = (
    "what is ",
    "what are ",
    "define ",
    "explain ",
    "tell me about ",
    "how does ",
    "what does ",
)

_EDUCATION_QUESTION_PREFIXES_ZH: tuple[str, ...] = (
    "什么是",
    "什么叫",
    "如何理解",
    "解释一下",
    "介绍",
)


def _looks_like_concept_question(q: str, raw: str) -> bool:
    ql = q.strip().lower()
    if any(ql.startswith(p) for p in _EDUCATION_QUESTION_PREFIXES):
        return True
    r = raw.strip()
    return any(r.startswith(p) for p in _EDUCATION_QUESTION_PREFIXES_ZH)


def check_refusal(question: str) -> Tuple[bool, str, str]:
    """
    Returns:
        (should_refuse, refusal_type, refusal_message)

    refusal_type:
    - investment
    - financial_product
    - personalized_advice
    - none
    """
    raw = question.strip()
    q = normalize_text(raw)

    # 0. Safe phrases — allow through (saving / emergency-fund education).
    if contains_phrase(q, SAFE_PHRASES):
        return False, "none", ""

    # 1. Personalized buy/sell / what to do with money.
    if contains_phrase(q, PERSONALIZED_DECISION_PATTERNS):
        return True, "personalized_advice", MSG_PERSONALIZED

    # 2. Explicit product recommendation wording (EN + ZH).
    if contains_phrase(q, PRODUCT_KEYWORDS) or contains_phrase(raw, PRODUCT_KEYWORDS):
        return True, "financial_product", MSG_PRODUCT
    if not _looks_like_concept_question(q, raw) and _zh_recommends_fund_or_product(raw):
        return True, "financial_product", MSG_PRODUCT

    # 3. Investment / trading advice phrases (EN + ZH substrings).
    if contains_phrase(q, INVESTMENT_ADVICE_SUBSTRINGS_EN) or contains_phrase(
        raw, INVESTMENT_ADVICE_SUBSTRINGS_ZH
    ):
        return True, "investment", MSG_INVESTMENT

    # 4. General investment vocabulary (whole-word English; avoids "stock" alone → "stock photo").
    if not _looks_like_concept_question(q, raw) and contains_whole_word(q, INVESTMENT_KEYWORDS):
        return True, "investment", MSG_INVESTMENT

    return False, "none", ""


if __name__ == "__main__":
    test_questions = [
        "What is an emergency fund?",
        "How much money should I keep in an emergency fund?",
        "What stocks should I buy right now?",
        "Can you recommend a good investment fund?",
        "Should I invest in crypto this year?",
        "How can I save money more effectively?",
        "What should I do with my money to get rich fast?",
        "推荐一只基金",
        "现在买什么股票好？",
    ]

    for q in test_questions:
        should_refuse, refusal_type, refusal_message = check_refusal(q)
        print("=" * 80)
        print("Question:", q)
        print("Should refuse:", should_refuse)
        print("Refusal type:", refusal_type)
        print("Refusal message:", refusal_message)
