from agents.education import service


def test_answer_question_empty_input_returns_refusal(monkeypatch):
    # Empty input should return a structured refusal response.
    monkeypatch.setattr(service, "log_education_result", lambda **_kwargs: None)

    result = service.answer_question("   ", user_id="u1")

    assert result["status"] == "refuse"
    assert result["refusal_type"] == "empty_question"
    assert result["citations"] == []
    assert result["retrieval"]["used_k"] == 0


def test_answer_question_refusal_branch_structure(monkeypatch):
    # Policy refusal should include refusal_type and retrieval metadata.
    monkeypatch.setattr(service, "check_refusal", lambda _q: (True, "investment", "refused message"))
    monkeypatch.setattr(service, "log_education_result", lambda **_kwargs: None)

    result = service.answer_question("What stocks should I buy?", user_id="u1")

    assert result["status"] == "refuse"
    assert result["answer"] == "refused message"
    assert result["refusal_type"] == "investment"
    assert "retrieval" in result and result["retrieval"]["used_k"] == 0


def test_answer_question_success_branch_structure(monkeypatch):
    # Successful branch should return answer, citations, and retrieval block.
    docs = [
        {
            "doc_id": "Doc_01",
            "doc_title": "Budgeting Basics",
            "chunk_index": 0,
            "content": "Create a monthly budget and track expenses.",
            "distance": 0.52,
        }
    ]
    monkeypatch.setattr(service, "check_refusal", lambda _q: (False, "none", ""))
    monkeypatch.setattr(service, "retrieve_documents", lambda **_kwargs: docs)
    monkeypatch.setattr(service, "build_answer_with_gpt", lambda _q, _docs: "Try a monthly budget.")
    monkeypatch.setattr(service, "log_education_result", lambda **_kwargs: None)

    result = service.answer_question("How do I improve budgeting?", user_id="u1")

    assert result["status"] == "answer"
    assert result["answer"] == "Try a monthly budget."
    assert isinstance(result["citations"], list) and len(result["citations"]) == 1
    assert set(result["retrieval"].keys()) == {
        "initial_k",
        "max_k",
        "used_k",
        "threshold",
        "confidence",
        "top_distance",
    }
