from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.chat import router
from api.deps import get_user_id
from database import get_db


def _make_chat_client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_id] = lambda: "test-user"
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_chat_routes_to_education_and_returns_education_type(monkeypatch):
    # Integration-style route test: /api/chat -> education branch.
    from api import chat as chat_api
    from agents.education import service as edu_service

    async def _fake_parse_quick_entry(_message):
        return SimpleNamespace(success=False, transaction=None)

    monkeypatch.setattr(chat_api, "parse_quick_entry", _fake_parse_quick_entry)
    monkeypatch.setattr(chat_api, "should_route_to_education", lambda _message: True)
    monkeypatch.setattr(
        edu_service,
        "answer_question",
        lambda question, user_id=None: {
            "status": "answer",
            "answer": "Budgeting starts with tracking expenses.",
            "citations": [{"title": "Budgeting Basics"}],
        },
    )

    client = _make_chat_client()
    resp = client.post("/api/chat", json={"message": "How can I improve budgeting?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "education"
    assert "Budgeting starts" in body["reply"]
    assert "Budgeting Basics" in body["reply"]


def test_chat_returns_general_when_not_quick_entry_and_not_education(monkeypatch):
    # Integration-style route test: /api/chat -> general branch.
    from api import chat as chat_api

    async def _fake_parse_quick_entry(_message):
        return SimpleNamespace(success=False, transaction=None)

    monkeypatch.setattr(chat_api, "parse_quick_entry", _fake_parse_quick_entry)
    monkeypatch.setattr(chat_api, "should_route_to_education", lambda _message: False)

    client = _make_chat_client()
    resp = client.post("/api/chat", json={"message": "hello there"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "general"
    assert "quick expense entry" in body["reply"].lower()
