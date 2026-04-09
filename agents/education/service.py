import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .retrieval import retrieve_documents
from .refusal import check_refusal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set in .env")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)

client = OpenAI(api_key=OPENAI_API_KEY)

RETRIEVAL_INITIAL_K = int(os.getenv("RETRIEVAL_INITIAL_K", "8"))
RETRIEVAL_MAX_K = int(os.getenv("RETRIEVAL_MAX_K", "3"))
RETRIEVAL_DISTANCE_THRESHOLD = float(
    os.getenv("RETRIEVAL_DISTANCE_THRESHOLD", "1.05")
)


def is_not_grounded(results: list[dict[str, Any]]) -> bool:
    """
    Return True when no retrieved chunk passes the retrieval threshold.
    """
    return len(results) == 0


def build_context_block(docs: list[dict[str, Any]]) -> str:
    """
    Build the retrieval context block for the LLM.
    Each chunk includes doc_id and title so the answer stays grounded.
    """
    context_parts = []

    for i, doc in enumerate(docs, start=1):
        doc_id = doc.get("doc_id", f"Doc_{i}")
        title = doc.get("doc_title", "Untitled")
        content = doc.get("content", "").strip()

        part = (
            f"[Source {i}]\n"
            f"doc_id: {doc_id}\n"
            f"title: {title}\n"
            f"content: {content}"
        )
        context_parts.append(part)

    return "\n\n".join(context_parts)


def build_answer_with_gpt(question: str, docs: list[dict[str, Any]]) -> str:
    """
    Use GPT to rewrite the final answer based only on retrieved documents.

    Requirements:
    - Answer only from the provided docs
    - Do not add outside knowledge
    - Say clearly when the docs are insufficient
    - Keep citations out of the answer text itself
    """
    if not docs:
        return "Sorry, I do not have enough information to answer this question."

    context_block = build_context_block(docs)

    if os.getenv("DEBUG_RAG", "0") == "1":
        print("===== RAG CONTEXT =====")
        print(context_block)
        print("=======================")
        print(f"Top-1 distance: {docs[0]['distance']}")
        print("===== END DEBUG =====")

    system_prompt = """
You are an education finance assistant using retrieval-augmented generation (RAG).

Your job:
1. Answer the user's question ONLY based on the provided knowledge sources.
2. Do NOT add outside facts, assumptions, or advice beyond the sources.
3. If the sources do not contain enough information, say so clearly.
4. Write a concise, natural, student-friendly answer.
5. Do not mention 'Source 1' / 'Source 2' in the final answer unless necessary.
6. Do not fabricate examples, laws, products, or recommendations not present in the sources.
"""

    user_prompt = f"""
User question:
{question}

Knowledge sources:
{context_block}

Please write the final answer based only on the knowledge sources above.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        answer = (response.choices[0].message.content or "").strip()

        if not answer:
            return "Sorry, I do not have enough information to answer this question."

        return answer

    except Exception as e:
        print(f"OpenAI generation failed: {e}")
        return fallback_build_answer(docs)


def fallback_build_answer(docs: list[dict[str, Any]]) -> str:
    """
    Build a simple fallback answer when LLM generation fails.
    """
    if not docs:
        return "Sorry, I do not have enough information to answer this question."

    top_doc = docs[0]["content"].strip()

    if len(docs) == 1:
        return f"Based on the available knowledge, {top_doc}"

    second_doc = docs[1]["content"].strip()

    return (
        f"Based on the available knowledge, {top_doc} "
        f"In addition, related guidance suggests that {second_doc.lower()}"
    )


def build_citations(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build deduplicated citations for frontend display.
    Each citation includes doc_id, title, chunk_index, and distance.
    """
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for doc in docs:
        key = (doc["doc_id"], doc["chunk_index"])
        if key in seen:
            continue

        citations.append({
            "doc_id": doc["doc_id"],
            "title": doc["doc_title"],
            "chunk_index": doc["chunk_index"],
            "distance": round(float(doc["distance"]), 4),
        })
        seen.add(key)

    return citations


def compute_retrieval_confidence(results: list[dict[str, Any]]) -> float:
    """
    Map distance to a simple confidence score.
    Smaller distance means higher confidence.
    """
    if not results:
        return 0.0

    best_distance = results[0]["distance"]
    confidence = max(0.0, min(1.0, 1.2 - best_distance))
    return round(confidence, 4)


def build_retrieval_metadata(
    results: list[dict[str, Any]],
    initial_k: int,
    max_k: int,
    threshold: float,
) -> dict[str, Any]:
    """
    Build retrieval metadata for the structured API response.
    """
    return {
        "initial_k": initial_k,
        "max_k": max_k,
        "used_k": len(results),
        "threshold": threshold,
        "confidence": compute_retrieval_confidence(results),
        "top_distance": round(float(results[0]["distance"]), 4) if results else None,
    }


def extract_retrieved_doc_ids(results: list[dict[str, Any]]) -> list[str]:
    """
    Extract unique doc_ids from retrieved results for logging.
    """
    doc_ids: list[str] = []
    seen: set[str] = set()

    for doc in results:
        doc_id = doc["doc_id"]
        if doc_id in seen:
            continue
        doc_ids.append(doc_id)
        seen.add(doc_id)

    return doc_ids


def log_education_result(
    question: str,
    answer: str,
    citations: list[dict[str, Any]],
    refused: bool,
    retrieval_confidence: float,
    user_id: str | None = None,
    status: str | None = None,
    refusal_type: str | None = None,
    retrieved_doc_ids: list[str] | None = None,
    retrieved_count: int | None = None,
    top_distance: float | None = None,
    retrieval_threshold: float | None = None,
) -> None:
    """
    Write one education result row into education_logs.
    """
    db = SessionLocal()
    try:
        sql = text("""
            INSERT INTO education_logs (
                user_id,
                question,
                answer,
                citations,
                refused,
                retrieval_confidence,
                status,
                refusal_type,
                retrieved_doc_ids,
                retrieved_count,
                top_distance,
                retrieval_threshold
            )
            VALUES (
                :user_id,
                :question,
                :answer,
                CAST(:citations AS jsonb),
                :refused,
                :retrieval_confidence,
                :status,
                :refusal_type,
                CAST(:retrieved_doc_ids AS jsonb),
                :retrieved_count,
                :top_distance,
                :retrieval_threshold
            )
        """)

        db.execute(
            sql,
            {
                "user_id": user_id,
                "question": question,
                "answer": answer,
                "citations": json.dumps(citations),
                "refused": refused,
                "retrieval_confidence": retrieval_confidence,
                "status": status,
                "refusal_type": refusal_type,
                "retrieved_doc_ids": json.dumps(retrieved_doc_ids or []),
                "retrieved_count": retrieved_count,
                "top_distance": top_distance,
                "retrieval_threshold": retrieval_threshold,
            },
        )
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"Failed to write education log: {e}")

    finally:
        db.close()


def answer_question(question: str, user_id: str | None = None) -> dict[str, Any]:
    """
    Main Education Agent flow:
    1. Refusal check
    2. Retrieval with dynamic top-k and threshold filter
    3. Grounding check
    4. GPT answer generation
    5. Logging
    6. Structured response
    """
    question = question.strip()

    if not question:
        result = {
            "status": "refuse",
            "answer": "Sorry, your question is empty.",
            "citations": [],
            "refusal_type": "empty_question",
            "retrieval": {
                "initial_k": RETRIEVAL_INITIAL_K,
                "max_k": RETRIEVAL_MAX_K,
                "used_k": 0,
                "threshold": RETRIEVAL_DISTANCE_THRESHOLD,
                "confidence": 0.0,
                "top_distance": None,
            }
        }

        log_education_result(
            question=question,
            answer=result["answer"],
            citations=result["citations"],
            refused=True,
            retrieval_confidence=0.0,
            user_id=user_id,
            status=result["status"],
            refusal_type=result["refusal_type"],
            retrieved_doc_ids=[],
            retrieved_count=0,
            top_distance=None,
            retrieval_threshold=RETRIEVAL_DISTANCE_THRESHOLD,
        )
        return result

    should_refuse, refusal_type, refusal_message = check_refusal(question)

    if should_refuse:
        result = {
            "status": "refuse",
            "answer": refusal_message,
            "citations": [],
            "refusal_type": refusal_type,
            "retrieval": {
                "initial_k": RETRIEVAL_INITIAL_K,
                "max_k": RETRIEVAL_MAX_K,
                "used_k": 0,
                "threshold": RETRIEVAL_DISTANCE_THRESHOLD,
                "confidence": 0.0,
                "top_distance": None,
            }
        }

        log_education_result(
            question=question,
            answer=result["answer"],
            citations=result["citations"],
            refused=True,
            retrieval_confidence=0.0,
            user_id=user_id,
            status=result["status"],
            refusal_type=result["refusal_type"],
            retrieved_doc_ids=[],
            retrieved_count=0,
            top_distance=None,
            retrieval_threshold=RETRIEVAL_DISTANCE_THRESHOLD,
        )
        return result

    results = retrieve_documents(
        question=question,
        initial_k=RETRIEVAL_INITIAL_K,
        max_k=RETRIEVAL_MAX_K,
        max_distance=RETRIEVAL_DISTANCE_THRESHOLD,
    )

    if is_not_grounded(results):
        result = {
            "status": "refuse",
            "answer": (
                "Sorry, I do not have enough information in my knowledge base "
                "to answer this question."
            ),
            "citations": [],
            "refusal_type": "not_grounded",
            "retrieval": {
                "initial_k": RETRIEVAL_INITIAL_K,
                "max_k": RETRIEVAL_MAX_K,
                "used_k": 0,
                "threshold": RETRIEVAL_DISTANCE_THRESHOLD,
                "confidence": 0.0,
                "top_distance": None,
            }
        }

        log_education_result(
            question=question,
            answer=result["answer"],
            citations=result["citations"],
            refused=True,
            retrieval_confidence=0.0,
            user_id=user_id,
            status=result["status"],
            refusal_type=result["refusal_type"],
            retrieved_doc_ids=[],
            retrieved_count=0,
            top_distance=None,
            retrieval_threshold=RETRIEVAL_DISTANCE_THRESHOLD,
        )
        return result

    answer = build_answer_with_gpt(question, results)
    citations = build_citations(results)
    retrieval_metadata = build_retrieval_metadata(
        results=results,
        initial_k=RETRIEVAL_INITIAL_K,
        max_k=RETRIEVAL_MAX_K,
        threshold=RETRIEVAL_DISTANCE_THRESHOLD,
    )
    retrieved_doc_ids = extract_retrieved_doc_ids(results)

    result = {
        "status": "answer",
        "answer": answer,
        "citations": citations,
        "retrieval": retrieval_metadata,
    }

    log_education_result(
        question=question,
        answer=answer,
        citations=citations,
        refused=False,
        retrieval_confidence=retrieval_metadata["confidence"],
        user_id=user_id,
        status=result["status"],
        refusal_type=None,
        retrieved_doc_ids=retrieved_doc_ids,
        retrieved_count=len(results),
        top_distance=retrieval_metadata["top_distance"],
        retrieval_threshold=RETRIEVAL_DISTANCE_THRESHOLD,
    )

    return result