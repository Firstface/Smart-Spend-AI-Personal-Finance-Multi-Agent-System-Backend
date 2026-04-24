from types import SimpleNamespace

from agents.education import service


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content
        self.last_kwargs = None

    def create(self, **kwargs):
        # Save call arguments so tests can assert prompt structure.
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._content)
                )
            ]
        )


def test_build_answer_with_gpt_uses_question_and_context(monkeypatch):
    # Prompt should include both user question and retrieved content.
    fake = _FakeCompletions("Use a simple monthly budget and track spending.")
    monkeypatch.setattr(
        service,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=fake)),
    )

    docs = [{"doc_id": "Doc_01", "doc_title": "Budgeting", "content": "Track daily expenses.", "distance": 0.4}]
    answer = service.build_answer_with_gpt("How do I budget better?", docs)

    assert answer.startswith("Use a simple monthly budget")
    messages = fake.last_kwargs["messages"]
    assert "How do I budget better?" in messages[1]["content"]
    assert "Track daily expenses." in messages[1]["content"]


def test_build_answer_with_gpt_returns_default_message_when_empty_docs():
    # No retrieval data should directly return a safe fallback.
    answer = service.build_answer_with_gpt("Any question", [])
    assert "do not have enough information" in answer


def test_build_answer_with_gpt_fallback_when_model_raises(monkeypatch):
    # GPT errors should fallback to deterministic answer builder.
    def _raise(**_kwargs):
        raise RuntimeError("simulated OpenAI failure")

    monkeypatch.setattr(
        service,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_raise))),
    )

    docs = [
        {"content": "Saving small amounts regularly helps.", "distance": 0.31},
        {"content": "Automation increases consistency.", "distance": 0.48},
    ]
    answer = service.build_answer_with_gpt("How can I save?", docs)
    assert answer.startswith("Based on the available knowledge,")
