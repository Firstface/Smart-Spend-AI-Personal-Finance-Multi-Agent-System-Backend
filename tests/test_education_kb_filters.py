from agents.education import retrieval


class _DummyRows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _DummyDB:
    def __init__(self, rows):
        self._rows = rows
        self.closed = False

    def execute(self, _sql, _params):
        # Return fixed retrieval candidates ordered by distance.
        return _DummyRows(self._rows)

    def close(self):
        self.closed = True


def test_retrieve_documents_applies_distance_threshold_and_max_k(monkeypatch):
    # Retrieval should filter by max_distance, then limit to max_k.
    rows = [
        {"id": 1, "doc_id": "Doc_01", "doc_title": "T1", "chunk_index": 0, "content": "A", "metadata": {}, "distance": 0.30},
        {"id": 2, "doc_id": "Doc_02", "doc_title": "T2", "chunk_index": 0, "content": "B", "metadata": {}, "distance": 0.60},
        {"id": 3, "doc_id": "Doc_03", "doc_title": "T3", "chunk_index": 0, "content": "C", "metadata": {}, "distance": 1.20},
    ]
    db = _DummyDB(rows)
    monkeypatch.setattr(retrieval, "get_query_embedding", lambda _q: [0.1, 0.2, 0.3])
    monkeypatch.setattr(retrieval, "SessionLocal", lambda: db)

    results = retrieval.retrieve_documents(
        question="How do I budget better?",
        initial_k=8,
        max_k=2,
        max_distance=0.8,
    )

    assert len(results) == 2
    assert [r["doc_id"] for r in results] == ["Doc_01", "Doc_02"]
    assert all(r["distance"] <= 0.8 for r in results)
    assert db.closed is True


def test_retrieve_documents_without_threshold_returns_top_k(monkeypatch):
    # If threshold is None, only max_k should cap results.
    rows = [
        {"id": 1, "doc_id": "Doc_11", "doc_title": "T1", "chunk_index": 0, "content": "A", "metadata": {}, "distance": 0.40},
        {"id": 2, "doc_id": "Doc_12", "doc_title": "T2", "chunk_index": 0, "content": "B", "metadata": {}, "distance": 1.40},
    ]
    monkeypatch.setattr(retrieval, "get_query_embedding", lambda _q: [0.9])
    monkeypatch.setattr(retrieval, "SessionLocal", lambda: _DummyDB(rows))

    results = retrieval.retrieve_documents(
        question="query",
        initial_k=5,
        max_k=1,
        max_distance=None,
    )

    assert len(results) == 1
    assert results[0]["doc_id"] == "Doc_11"
