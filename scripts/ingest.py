import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

# kb.json
DEFAULT_KB_PATH = BASE_DIR / "data" / "kb.json"
LEGACY_KB_PATH = Path(__file__).resolve().parent / "kb.json"
KB_PATH = DEFAULT_KB_PATH if DEFAULT_KB_PATH.exists() else LEGACY_KB_PATH

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)


def load_kb(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"kb.json not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("kb.json must contain a list of documents")

    return data


def document_exists(db, doc_id: str) -> bool:
    sql = text("""
        SELECT 1
        FROM knowledge_chunks
        WHERE doc_id = :doc_id
        LIMIT 1
    """)
    result = db.execute(sql, {"doc_id": doc_id}).fetchone()
    return result is not None


def insert_document(db, doc: dict[str, Any]) -> None:
    metadata = {
        "topic": doc["topic"],
        "source": "local_kb",
        "version": "v1"
    }

    sql = text("""
        INSERT INTO knowledge_chunks (
            doc_id,
            doc_title,
            chunk_index,
            content,
            metadata
        )
        VALUES (
            :doc_id,
            :doc_title,
            :chunk_index,
            :content,
            CAST(:metadata AS jsonb)
        )
    """)

    db.execute(
        sql,
        {
            "doc_id": doc["id"],
            "doc_title": doc["title"],
            "chunk_index": 0,
            "content": doc["content"],
            "metadata": json.dumps(metadata),
        },
    )


def validate_document(doc: dict[str, Any], index: int) -> None:
    required_fields = ["id", "topic", "title", "content"]
    for field in required_fields:
        if field not in doc:
            raise ValueError(f"Document at index {index} is missing field: {field}")

    if not all(isinstance(doc[field], str) and doc[field].strip() for field in required_fields):
        raise ValueError(f"Document at index {index} has empty or invalid string fields")


def main() -> None:
    docs = load_kb(KB_PATH)

    inserted = 0
    skipped = 0

    db = SessionLocal()
    try:
        for i, doc in enumerate(docs):
            validate_document(doc, i)

            if document_exists(db, doc["id"]):
                print(f"Skipped existing doc: {doc['id']}")
                skipped += 1
                continue

            insert_document(db, doc)
            print(f"Inserted: {doc['id']} - {doc['title']}")
            inserted += 1

        db.commit()
        print("\nDone.")
        print(f"Inserted: {inserted}")
        print(f"Skipped: {skipped}")

    except Exception as e:
        db.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()