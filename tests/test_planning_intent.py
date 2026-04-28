import pytest

from agents.chat_routing.intent import should_route_to_education, should_route_to_planning


@pytest.fixture(autouse=True)
def disable_planning_llm_router(monkeypatch):
    monkeypatch.setenv("CHAT_PLANNING_LLM_ROUTER", "0")


@pytest.mark.parametrize(
    "message",
    [
        "show my plan",
        "view budget for next month",
        "my plans",
        "budget list",
    ],
)
def test_planning_view_keywords(message):
    assert should_route_to_planning(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "create plan for next month",
        "generate budget",
        "make a budget",
        "start planning",
    ],
)
def test_planning_create_keywords(message):
    assert should_route_to_planning(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "adjust my budget",
        "refine my plan",
        "lower the budget",
        "update plan",
    ],
)
def test_planning_refine_keywords(message):
    assert should_route_to_planning(message) is True


def test_planning_smalltalk_does_not_route():
    assert should_route_to_planning("hello") is False


def test_planning_non_question_without_keyword_does_not_route():
    assert should_route_to_planning("random words only") is False


def test_planning_keyword_has_priority_over_education_budget_question():
    message = "How do I make a budget plan for next month?"
    assert should_route_to_planning(message) is True
    assert should_route_to_education(message) is False


def test_planning_keyword_does_not_capture_spending_analysis():
    assert should_route_to_planning("Analyze my recent spending") is False
