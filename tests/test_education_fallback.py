from types import SimpleNamespace

from agents.education import service


def test_fallback_build_answer_no_docs():
    # No docs should return the default insufficient-information response.
    answer = service.fallback_build_answer([])
    assert "do not have enough information" in answer


def test_fallback_build_answer_single_doc():
    # With one doc, fallback should return a concise grounded answer.
    docs = [{"content": "Build an emergency fund before investing."}]
    answer = service.fallback_build_answer(docs)
    assert answer.startswith("Based on the available knowledge,")
    assert "emergency fund" in answer.lower()


def test_fallback_build_answer_two_docs():
    # With two docs, fallback should include both top snippets.
    docs = [
        {"content": "Track all expenses weekly."},
        {"content": "Set automatic savings transfers."},
    ]
    answer = service.fallback_build_answer(docs)
    assert "Track all expenses weekly." in answer
    assert "set automatic savings transfers." in answer


def test_build_answer_with_gpt_uses_fallback_on_empty_model_output(monkeypatch):
    # Empty model output should map to default insufficient-information message.
    fake = SimpleNamespace(
        create=lambda **_kwargs: SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="   "))]
        )
    )
    monkeypatch.setattr(service, "client", SimpleNamespace(chat=SimpleNamespace(completions=fake)))

    docs = [{"doc_id": "Doc_10", "doc_title": "Title", "content": "Some content", "distance": 0.3}]
    answer = service.build_answer_with_gpt("question", docs)
    assert "do not have enough information" in answer
