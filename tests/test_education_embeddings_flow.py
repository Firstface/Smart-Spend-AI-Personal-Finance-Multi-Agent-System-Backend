from types import SimpleNamespace

from agents.education import retrieval


def test_get_query_embedding_returns_vector_from_client(monkeypatch):
    # The helper should return the first embedding vector from OpenAI response.
    fake_response = SimpleNamespace(data=[SimpleNamespace(embedding=[0.11, 0.22, 0.33])])
    fake_embeddings = SimpleNamespace(create=lambda **_kwargs: fake_response)
    monkeypatch.setattr(retrieval, "client", SimpleNamespace(embeddings=fake_embeddings))

    vector = retrieval.get_query_embedding("What is a budget?")

    assert vector == [0.11, 0.22, 0.33]


def test_retrieve_documents_formats_id_and_distance_types(monkeypatch):
    # Returned structure should normalize id to str and distance to float.
    class _Rows:
        def mappings(self):
            return self

        def all(self):
            return [
                {
                    "id": 99,
                    "doc_id": "Doc_99",
                    "doc_title": "Title",
                    "chunk_index": 2,
                    "content": "C",
                    "metadata": {"topic": "budgeting"},
                    "distance": "0.1234",
                }
            ]

    class _DB:
        def execute(self, _sql, _params):
            return _Rows()

        def close(self):
            return None

    monkeypatch.setattr(retrieval, "get_query_embedding", lambda _q: [0.1, 0.2])
    monkeypatch.setattr(retrieval, "SessionLocal", lambda: _DB())

    docs = retrieval.retrieve_documents(
        question="q",
        initial_k=3,
        max_k=3,
        max_distance=1.0,
    )

    assert len(docs) == 1
    assert docs[0]["id"] == "99"
    assert isinstance(docs[0]["distance"], float)
    assert docs[0]["distance"] == 0.1234
