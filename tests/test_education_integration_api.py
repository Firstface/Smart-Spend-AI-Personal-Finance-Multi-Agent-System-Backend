from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.education import router


def _make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_education_ask_endpoint_returns_structured_answer(monkeypatch):
    # Integration-style check: API schema + service handoff.
    from api import education as education_api

    monkeypatch.setattr(
        education_api,
        "answer_question",
        lambda question, user_id=None: {
            "answer": f"Echo: {question}",
            "citations": [{"doc_id": "Doc_01", "title": "Budgeting Basics"}],
            "status": "answer",
            "refusal_type": None,
        },
    )

    client = _make_client()
    resp = client.post("/education/ask", json={"question": "How to budget?", "user_id": "u-1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "answer"
    assert body["answer"].startswith("Echo:")
    assert body["citations"][0]["doc_id"] == "Doc_01"
    assert body["citations"][0]["title"] == "Budgeting Basics"


def test_education_ask_endpoint_returns_refusal_payload(monkeypatch):
    # Refusal response should keep the expected API response shape.
    from api import education as education_api

    monkeypatch.setattr(
        education_api,
        "answer_question",
        lambda question, user_id=None: {
            "answer": "Sorry, I cannot recommend specific products.",
            "citations": [],
            "status": "refuse",
            "refusal_type": "financial_product",
        },
    )

    client = _make_client()
    resp = client.post("/education/ask", json={"question": "Recommend one ETF"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "refuse"
    assert body["refusal_type"] == "financial_product"
    assert body["citations"] == []
