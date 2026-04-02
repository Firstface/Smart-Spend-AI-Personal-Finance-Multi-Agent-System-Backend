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

# 可改：embedding 模型
EMBEDDING_MODEL = "text-embedding-3-small"


def fetch_rows_without_embedding(db) -> list[dict[str, Any]]:
    sql = text("""
        SELECT id, doc_id, doc_title, content
        FROM knowledge_chunks
        WHERE embedding IS NULL
        ORDER BY created_at ASC
    """)
    rows = db.execute(sql).mappings().all()
    return [dict(row) for row in rows]


def get_embedding(text_value: str) -> list[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text_value
    )
    return response.data[0].embedding


def update_embedding(db, row_id: str, embedding: list[float]) -> None:
    # pgvector 支持用字符串形式 '[0.1,0.2,...]' 写入
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    sql = text("""
        UPDATE knowledge_chunks
        SET embedding = CAST(:embedding AS vector)
        WHERE id = :row_id
    """)

    db.execute(
        sql,
        {
            "embedding": embedding_str,
            "row_id": row_id,
        },
    )


def main() -> None:
    db = SessionLocal()
    updated = 0

    try:
        rows = fetch_rows_without_embedding(db)

        if not rows:
            print("No rows need embeddings. Everything is already updated.")
            return

        print(f"Found {len(rows)} rows without embeddings.\n")

        for row in rows:
            print(f"Processing: {row['doc_id']} - {row['doc_title']}")
            embedding = get_embedding(row["content"])
            update_embedding(db, row["id"], embedding)
            updated += 1
            print(f"Updated embedding for {row['doc_id']}")

        db.commit()
        print("\nDone.")
        print(f"Embeddings added: {updated}")

    except Exception as e:
        db.rollback()
        print(f"\nError: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()