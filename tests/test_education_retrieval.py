import pytest

from agents.education import service


def test_build_context_block_includes_required_fields():
    # Context text should preserve source id, title, and content.
    docs = [
        {"doc_id": "Doc_01", "doc_title": "Budgeting Basics", "content": "Track your expenses."},
        {"doc_id": "Doc_02", "doc_title": "Saving Basics", "content": "Pay yourself first."},
    ]

    context = service.build_context_block(docs)

    assert "[Source 1]" in context
    assert "doc_id: Doc_01" in context
    assert "title: Budgeting Basics" in context
    assert "content: Track your expenses." in context
    assert "[Source 2]" in context


def test_build_citations_deduplicates_same_doc_and_chunk():
    # Duplicate (doc_id, chunk_index) pairs should appear only once.
    docs = [
        {"doc_id": "Doc_01", "doc_title": "T1", "chunk_index": 0, "distance": 0.81234},
        {"doc_id": "Doc_01", "doc_title": "T1", "chunk_index": 0, "distance": 0.81234},
        {"doc_id": "Doc_01", "doc_title": "T1", "chunk_index": 1, "distance": 0.90001},
    ]

    citations = service.build_citations(docs)

    assert len(citations) == 2
    assert citations[0]["distance"] == 0.8123
    assert citations[1]["chunk_index"] == 1


def test_extract_retrieved_doc_ids_keeps_order_and_uniqueness():
    # Returned ids should be ordered by first appearance.
    docs = [
        {"doc_id": "Doc_09"},
        {"doc_id": "Doc_03"},
        {"doc_id": "Doc_09"},
        {"doc_id": "Doc_05"},
    ]

    assert service.extract_retrieved_doc_ids(docs) == ["Doc_09", "Doc_03", "Doc_05"]


@pytest.mark.parametrize(
    "distance,expected",
    [
        (0.2, 1.0),
        (0.8, 0.4),
        (1.2, 0.0),
    ],
)
def test_compute_retrieval_confidence(distance, expected):
    # Confidence uses the distance -> score mapping in service.py.
    results = [{"distance": distance}]
    assert service.compute_retrieval_confidence(results) == expected


def test_build_retrieval_metadata_uses_top_distance_and_count():
    # Metadata should be consistent with retrieval results.
    results = [
        {"distance": 0.45678},
        {"distance": 0.89123},
    ]

    meta = service.build_retrieval_metadata(
        results=results,
        initial_k=8,
        max_k=3,
        threshold=1.05,
    )

    assert meta["initial_k"] == 8
    assert meta["max_k"] == 3
    assert meta["used_k"] == 2
    assert meta["threshold"] == 1.05
    assert meta["top_distance"] == 0.4568
    assert meta["confidence"] == 0.7432
