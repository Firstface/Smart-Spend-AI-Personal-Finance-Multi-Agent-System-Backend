import pytest

from agents.education.refusal import check_refusal


@pytest.mark.parametrize(
    "question,expected_type",
    [
        ("Should I buy Bitcoin now?", "personalized_advice"),
        ("Recommend a good ETF for me.", "financial_product"),
        ("Which stock should I buy this week?", "personalized_advice"),
    ],
)
def test_guardrails_block_actionable_investment_content(question: str, expected_type: str):
    # Actionable investment requests should be blocked by policy.
    should_refuse, refusal_type, msg = check_refusal(question)
    assert should_refuse is True
    assert refusal_type == expected_type
    assert msg.startswith("Sorry")


@pytest.mark.parametrize(
    "question",
    [
        "What is compound interest?",
        "How can I build an emergency fund?",
        "Explain debt snowball strategy in simple terms.",
    ],
)
def test_guardrails_allow_educational_finance_questions(question: str):
    # General education questions should pass.
    should_refuse, refusal_type, msg = check_refusal(question)
    assert should_refuse is False
    assert refusal_type == "none"
    assert msg == ""
