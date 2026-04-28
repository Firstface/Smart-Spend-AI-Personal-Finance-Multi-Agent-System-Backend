import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY", "") or "").strip() or "ollama"
OPENAI_API_BASE = (os.getenv("OPENAI_API_BASE", "") or "").strip() or None

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()

# Smaller distance means higher relevance.
DEFAULT_RETRIEVAL_DISTANCE_THRESHOLD = float(
    os.getenv("RETRIEVAL_DISTANCE_THRESHOLD", "1.05")
)

DEFAULT_RETRIEVAL_INITIAL_K = int(
    os.getenv("RETRIEVAL_INITIAL_K", "8")
)

DEFAULT_RETRIEVAL_MAX_K = int(
    os.getenv("RETRIEVAL_MAX_K", "3")
)


def get_query_embedding(question: str) -> list[float]:
    if not EMBEDDING_MODEL:
        raise RuntimeError(
            "OPENAI_EMBEDDING_MODEL is not configured; education retrieval is disabled."
        )
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=question
    )
    return response.data[0].embedding


def retrieve_documents(
    question: str,
    initial_k: int = DEFAULT_RETRIEVAL_INITIAL_K,
    max_k: int = DEFAULT_RETRIEVAL_MAX_K,
    max_distance: float | None = DEFAULT_RETRIEVAL_DISTANCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    Generate an embedding for the user question and perform vector retrieval
    in the knowledge_chunks table.

    Steps:
    1. Retrieve more candidate chunks using initial_k.
    2. Apply an optional distance threshold filter.
    3. Return up to max_k grounded results.

    This implements dynamic top-k:
    - retrieve a larger candidate pool first
    - filter low-relevance chunks
    - keep only the best remaining results up to max_k
    """
    query_embedding = get_query_embedding(question)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    sql = text("""
        SELECT
            id,
            doc_id,
            doc_title,
            chunk_index,
            content,
            metadata,
            embedding <-> CAST(:query_embedding AS vector) AS distance
        FROM knowledge_chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <-> CAST(:query_embedding AS vector)
        LIMIT :initial_k
    """)

    db = SessionLocal()
    try:
        rows = db.execute(
            sql,
            {
                "query_embedding": embedding_str,
                "initial_k": initial_k,
            }
        ).mappings().all()

        filtered_results: list[dict[str, Any]] = []

        for row in rows:
            row_dict = dict(row)
            result = {
                "id": str(row_dict["id"]),
                "doc_id": row_dict["doc_id"],
                "doc_title": row_dict["doc_title"],
                "chunk_index": row_dict["chunk_index"],
                "content": row_dict["content"],
                "metadata": row_dict["metadata"],
                "distance": float(row_dict["distance"]),
            }

            if max_distance is None or result["distance"] <= max_distance:
                filtered_results.append(result)

        return filtered_results[:max_k]

    finally:
        db.close()


if __name__ == "__main__":
    test_question = "I spend all my money every month. How should I manage it better?"
    docs = retrieve_documents(
        question=test_question,
        initial_k=DEFAULT_RETRIEVAL_INITIAL_K,
        max_k=DEFAULT_RETRIEVAL_MAX_K,
        max_distance=DEFAULT_RETRIEVAL_DISTANCE_THRESHOLD,
    )

    print(f"\nQuestion: {test_question}\n")
    print(f"Initial candidate pool: {DEFAULT_RETRIEVAL_INITIAL_K}")
    print(f"Max returned chunks: {DEFAULT_RETRIEVAL_MAX_K}")
    print(f"Distance threshold: {DEFAULT_RETRIEVAL_DISTANCE_THRESHOLD}\n")

    if not docs:
        print("No documents passed the distance threshold.")
    else:
        for i, doc in enumerate(docs, start=1):
            print(f"Result {i}")
            print(f"doc_id: {doc['doc_id']}")
            print(f"title: {doc['doc_title']}")
            print(f"chunk_index: {doc['chunk_index']}")
            print(f"distance: {doc['distance']:.6f}")
            print(f"content: {doc['content']}")
            print("-" * 60)
