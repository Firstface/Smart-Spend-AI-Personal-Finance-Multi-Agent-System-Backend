import os

import pytest

from agents.chat_routing.intent import should_route_to_education


@pytest.fixture(autouse=True)
def disable_llm_router(monkeypatch):
    monkeypatch.setenv("CHAT_EDUCATION_LLM_ROUTER", "0")


def test_keyword_english_budget():
    assert should_route_to_education("How do I make a monthly budget?") is True


def test_keyword_chinese():
    assert should_route_to_education("什么是复利") is True


def test_smalltalk_not_education():
    assert should_route_to_education("thanks") is False
    assert should_route_to_education("你好") is False


def test_non_question_short_without_keyword():
    assert should_route_to_education("random words only") is False


def test_investment_advice_routes_even_without_keyword_or_llm():
    """LLM router often classifies buy-a-stock questions as non-education; refusal still needs Education."""
    assert should_route_to_education("What stocks should I buy right now?") is True


def test_llm_router_respects_env_zero(monkeypatch):
    monkeypatch.setenv("CHAT_EDUCATION_LLM_ROUTER", "0")
    # No keyword, question-shaped — without LLM should stay False
    assert should_route_to_education("What is the capital of France?") is False
