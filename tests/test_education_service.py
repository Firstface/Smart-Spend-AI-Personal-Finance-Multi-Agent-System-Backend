from agents.education import service as education_service


def _sample_docs():
    return [
        {
            "doc_id": "doc-1",
            "doc_title": "Emergency Fund Basics",
            "chunk_index": 0,
            "distance": 0.42,
            "content": "An emergency fund helps cover unexpected expenses.",
        },
        {
            "doc_id": "doc-2",
            "doc_title": "Budgeting 101",
            "chunk_index": 1,
            "distance": 0.58,
            "content": "A monthly budget helps track essential and discretionary spending.",
        },
    ]


def test_answer_question_empty_question(monkeypatch):
    monkeypatch.setattr(education_service, "log_education_result", lambda **kwargs: None)

    result = education_service.answer_question("   ", user_id="test-user")

    assert result["status"] == "refuse"
    assert result["refusal_type"] == "empty_question"
    assert result["citations"] == []
    assert result["retrieval"]["used_k"] == 0


def test_answer_question_refusal_branch(monkeypatch):
    monkeypatch.setattr(
        education_service,
        "check_refusal",
        lambda question: (True, "investment", "Sorry, I cannot provide investment advice."),
    )
    monkeypatch.setattr(education_service, "log_education_result", lambda **kwargs: None)

    result = education_service.answer_question("What stock should I buy?", user_id="test-user")

    assert result["status"] == "refuse"
    assert result["refusal_type"] == "investment"
    assert "cannot provide investment advice" in result["answer"]
    assert result["retrieval"]["used_k"] == 0


def test_answer_question_not_grounded(monkeypatch):
    monkeypatch.setattr(education_service, "check_refusal", lambda question: (False, "none", ""))
    monkeypatch.setattr(education_service, "retrieve_documents", lambda **kwargs: [])
    monkeypatch.setattr(education_service, "log_education_result", lambda **kwargs: None)

    result = education_service.answer_question("How do I save money?", user_id="test-user")

    assert result["status"] == "refuse"
    assert result["refusal_type"] == "not_grounded"
    assert "do not have enough information" in result["answer"]
    assert result["retrieval"]["used_k"] == 0


def test_answer_question_grounded_answer(monkeypatch):
    monkeypatch.setattr(education_service, "check_refusal", lambda question: (False, "none", ""))
    monkeypatch.setattr(education_service, "retrieve_documents", lambda **kwargs: _sample_docs())
    monkeypatch.setattr(
        education_service,
        "build_answer_with_gpt",
        lambda question, docs: "Build an emergency fund before taking more financial risk.",
    )
    monkeypatch.setattr(education_service, "log_education_result", lambda **kwargs: None)

    result = education_service.answer_question("How should I prepare for emergencies?", user_id="test-user")

    assert result["status"] == "answer"
    assert result["answer"] == "Build an emergency fund before taking more financial risk."
    assert len(result["citations"]) == 2
    assert result["retrieval"]["used_k"] == 2
    assert result["retrieval"]["top_distance"] == 0.42


def test_build_citations_deduplicates_chunks():
    docs = _sample_docs() + [
        {
            "doc_id": "doc-1",
            "doc_title": "Emergency Fund Basics",
            "chunk_index": 0,
            "distance": 0.41,
            "content": "Duplicate chunk should be removed.",
        }
    ]

    citations = education_service.build_citations(docs)

    assert len(citations) == 2
    assert citations[0]["doc_id"] == "doc-1"
    assert citations[1]["doc_id"] == "doc-2"


def test_build_retrieval_metadata_contains_confidence():
    metadata = education_service.build_retrieval_metadata(
        results=_sample_docs(),
        initial_k=8,
        max_k=3,
        threshold=1.05,
    )

    assert metadata["initial_k"] == 8
    assert metadata["max_k"] == 3
    assert metadata["used_k"] == 2
    assert metadata["top_distance"] == 0.42
    assert 0.0 <= metadata["confidence"] <= 1.0
