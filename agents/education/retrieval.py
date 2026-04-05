import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)

EMBEDDING_MODEL = "text-embedding-3-small"


def get_query_embedding(question: str) -> list[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=question
    )
    return response.data[0].embedding


def retrieve_documents(question: str, top_k: int = 3) -> list[dict[str, Any]]:
    """
    根据用户问题生成 embedding，并在 knowledge_chunks 中做向量检索。
    返回最相似的 top_k 条结果。
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
        LIMIT :top_k
    """)

    db = SessionLocal()
    try:
        rows = db.execute(
            sql,
            {
                "query_embedding": embedding_str,
                "top_k": top_k,
            }
        ).mappings().all()

        results = []
        for row in rows:
            row_dict = dict(row)
            results.append({
                "id": str(row_dict["id"]),
                "doc_id": row_dict["doc_id"],
                "doc_title": row_dict["doc_title"],
                "chunk_index": row_dict["chunk_index"],
                "content": row_dict["content"],
                "metadata": row_dict["metadata"],
                "distance": float(row_dict["distance"]),
            })

        return results

    finally:
        db.close()


if __name__ == "__main__":
    test_question = "I spend all my money every month. How should I manage it better?"
    docs = retrieve_documents(test_question, top_k=3)

    print(f"\nQuestion: {test_question}\n")
    for i, doc in enumerate(docs, start=1):
        print(f"Result {i}")
        print(f"doc_id: {doc['doc_id']}")
        print(f"title: {doc['doc_title']}")
        print(f"distance: {doc['distance']:.6f}")
        print(f"content: {doc['content']}")
        print("-" * 60)