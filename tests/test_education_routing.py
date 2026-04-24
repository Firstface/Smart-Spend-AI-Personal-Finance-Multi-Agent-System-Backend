import pytest

from agents.chat_routing import intent


@pytest.fixture(autouse=True)
def disable_llm_router(monkeypatch):
    # Keep tests deterministic by disabling network-based router.
    monkeypatch.setenv("CHAT_EDUCATION_LLM_ROUTER", "0")


def test_routes_keyword_message_to_education():
    # Budget keywords should route directly.
    assert intent.should_route_to_education("Help me build a budget plan.") is True


def test_routes_refusal_intent_to_education_for_policy_reply():
    # Investment advice questions should still hit Education for refusal messaging.
    assert intent.should_route_to_education("Which ETF should I buy this month?") is True


def test_does_not_route_smalltalk():
    # Simple greetings should not trigger Education routing.
    assert intent.should_route_to_education("hello") is False
    assert intent.should_route_to_education("谢谢") is False


def test_llm_result_true_is_used_when_keyword_misses(monkeypatch):
    # If question-shaped and LLM says education, route should be True.
    monkeypatch.setattr(intent, "_llm_education_intent", lambda _msg: True)
    assert intent.should_route_to_education("Can you explain deductible and premium?") is True


def test_llm_result_false_is_used_when_keyword_misses(monkeypatch):
    # If question-shaped and LLM says other, route should be False.
    monkeypatch.setattr(intent, "_llm_education_intent", lambda _msg: False)
    assert intent.should_route_to_education("What is the weather in Singapore today?") is False
