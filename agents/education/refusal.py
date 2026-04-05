import re
from typing import Tuple

# this module is responsible for checking if a user question should be refused based on certain patterns
SAFE_PHRASES = [
    "emergency fund",
    "saving fund"
]

INVESTMENT_KEYWORDS = [
    "stock", "stocks",
    "crypto", "cryptocurrency",
    "bitcoin", "ethereum",
    "bond", "bonds",
    "etf", "etfs",
    "portfolio",
    "trading",
    "investment", "investing", "invest"
]

PRODUCT_KEYWORDS = [
    "financial product",
    "insurance product",
    "best fund",
    "best investment product",
    "best insurance",
    "recommend a fund",
    "recommend a product",
    "which product",
    "which fund",
    "mutual fund",
    "index fund",
    "unit trust"
]

PERSONALIZED_DECISION_PATTERNS = [
    "should i invest",
    "should i buy",
    "what should i buy",
    "where should i invest",
    "which stock should i buy",
    "which fund should i buy",
    "what is the best investment",
    "what should i do with my money",
    "how can i get rich fast",
    "fastest way to become rich",
    "how to maximize returns",
    "highest returns"
]


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def contains_phrase(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def contains_whole_word(text: str, words: list[str]) -> bool:
    for word in words:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, text):
            return True
    return False


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
    q = normalize_text(question)

    # 0. Safe phrases should be allowed first
    if contains_phrase(q, SAFE_PHRASES):
        return False, "none", ""

    # 1. Personalized decision-making has highest priority
    if contains_phrase(q, PERSONALIZED_DECISION_PATTERNS):
        return (
            True,
            "personalized_advice",
            "Sorry, I cannot provide personalized financial or investment decisions. "
            "I can only provide general educational information about budgeting, saving, "
            "spending habits, and basic financial concepts."
        )

    # 2. Specific product recommendation
    if contains_phrase(q, PRODUCT_KEYWORDS):
        return (
            True,
            "financial_product",
            "Sorry, I cannot recommend specific financial products such as funds, insurance, "
            "or other investment products. I can only provide general educational information."
        )

    # 3. General investment-related questions
    if contains_whole_word(q, INVESTMENT_KEYWORDS):
        return (
            True,
            "investment",
            "Sorry, I cannot provide investment advice such as recommending stocks, "
            "funds, crypto, or other investment options. I can help explain general "
            "financial concepts instead."
        )

    return False, "none", ""


if __name__ == "__main__":
    test_questions = [
        "What is an emergency fund?",
        "How much money should I keep in an emergency fund?",
        "What stocks should I buy right now?",
        "Can you recommend a good investment fund?",
        "Should I invest in crypto this year?",
        "How can I save money more effectively?",
        "What should I do with my money to get rich fast?"
    ]

    for q in test_questions:
        should_refuse, refusal_type, refusal_message = check_refusal(q)
        print("=" * 80)
        print("Question:", q)
        print("Should refuse:", should_refuse)
        print("Refusal type:", refusal_type)
        print("Refusal message:", refusal_message)