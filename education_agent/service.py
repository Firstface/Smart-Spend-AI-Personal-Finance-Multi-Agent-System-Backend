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

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set in .env")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)

client = OpenAI(api_key=OPENAI_API_KEY)


def is_not_grounded(results: list[dict[str, Any]], max_distance: float = 1.05) -> bool:
    """
    判断检索结果是否足够可靠。
    规则：
    - 没有结果 -> not grounded
    - 最佳结果距离太大 -> not grounded
    """
    if not results:
        return True

    best_distance = results[0]["distance"]
    return best_distance > max_distance


def build_context_block(docs: list[dict[str, Any]]) -> str:
    """
    把检索结果拼成给 LLM 的上下文。
    每段都带 doc_id 和 title，方便模型做 grounded answer。
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
    使用 GPT 基于检索结果重写 answer。
    要求：
    - 只能依据提供的 docs 回答
    - 不允许补充检索外知识
    - 信息不足时直接说不知道
    - 不在 answer 里硬塞 citation 标记，citation 仍由后端结构化返回
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
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        answer = (response.output_text or "").strip()

        if not answer:
            return "Sorry, I do not have enough information to answer this question."

        return answer

    except Exception as e:
        print(f"OpenAI generation failed: {e}")

        # 降级方案：LLM 失败时退回到简单拼接，避免整个服务挂掉
        return fallback_build_answer(docs)


def fallback_build_answer(docs: list[dict[str, Any]]) -> str:
    """
    LLM 失败时的兜底 answer。
    """
    if not docs:
        return "Sorry, I do not have enough information to answer this question."

    top_doc = docs[0]["content"].strip()

    if len(docs) == 1:
        return f"Based on the available knowledge, {top_doc}"

    second_doc = docs[1]["content"].strip()

    answer = (
        f"Based on the available knowledge, {top_doc} "
        f"In addition, related guidance suggests that {second_doc.lower()}"
    )
    return answer


def build_citations(docs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    生成 citations，适合前端显示和日志存储。
    去重后返回：
    [
      {"doc_id": "Doc_01", "title": "Budgeting Basics"},
      ...
    ]
    """
    citations = []
    seen = set()

    for doc in docs:
        doc_id = doc["doc_id"]
        if doc_id in seen:
            continue

        citations.append({
            "doc_id": doc["doc_id"],
            "title": doc["doc_title"]
        })
        seen.add(doc_id)

    return citations


def compute_retrieval_confidence(results: list[dict[str, Any]]) -> float:
    """
    把 distance 粗略映射成 confidence。
    distance 越小，confidence 越高。
    """
    if not results:
        return 0.0

    best_distance = results[0]["distance"]

    confidence = max(0.0, min(1.0, 1.2 - best_distance))
    return round(confidence, 4)


def log_education_result(
    question: str,
    answer: str,
    citations: list[dict[str, str]],
    refused: bool,
    retrieval_confidence: float,
    user_id: str | None = None,
) -> None:
    """
    记录到 education_logs。
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
                retrieval_confidence
            )
            VALUES (
                :user_id,
                :question,
                :answer,
                CAST(:citations AS jsonb),
                :refused,
                :retrieval_confidence
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
    Education Agent 主流程：
    1. refusal check
    2. retrieval
    3. grounding check
    4. answer generation by GPT
    5. logging
    6. return structured output
    """
    question = question.strip()

    if not question:
        result = {
            "answer": "Sorry, your question is empty.",
            "citations": [],
            "status": "refuse"
        }

        log_education_result(
            question=question,
            answer=result["answer"],
            citations=result["citations"],
            refused=True,
            retrieval_confidence=0.0,
            user_id=user_id,
        )
        return result

    should_refuse, refusal_type, refusal_message = check_refusal(question)

    if should_refuse:
        result = {
            "answer": refusal_message,
            "citations": [],
            "status": "refuse",
            "refusal_type": refusal_type
        }

        log_education_result(
            question=question,
            answer=result["answer"],
            citations=result["citations"],
            refused=True,
            retrieval_confidence=0.0,
            user_id=user_id,
        )
        return result

    results = retrieve_documents(question, top_k=3)

    if is_not_grounded(results):
        result = {
            "answer": (
                "Sorry, I do not have enough information in my knowledge base "
                "to answer this question."
            ),
            "citations": [],
            "status": "refuse",
            "refusal_type": "not_grounded"
        }

        log_education_result(
            question=question,
            answer=result["answer"],
            citations=result["citations"],
            refused=True,
            retrieval_confidence=0.0,
            user_id=user_id,
        )
        return result

    answer = build_answer_with_gpt(question, results)
    citations = build_citations(results)
    confidence = compute_retrieval_confidence(results)

    result = {
        "answer": answer,
        "citations": citations,
        "status": "answer"
    }

    log_education_result(
        question=question,
        answer=answer,
        citations=citations,
        refused=False,
        retrieval_confidence=confidence,
        user_id=user_id,
    )

    return result


if __name__ == "__main__":
    test_questions = [
        "How can I save money more effectively?",
        "What is an emergency fund?",
        "I spend all my money every month. How should I manage it better?",
        "What stocks should I buy right now?",
        "How do taxes work for freelancers in Singapore?"
    ]

    for q in test_questions:
        print("\n" + "=" * 80)
        print(f"Question: {q}")
        response = answer_question(
            q,
            user_id="b230c1ef-ed77-46bd-aeca-7139f2e0c370"
        )
        print("Response:")
        print(json.dumps(response, indent=2, ensure_ascii=False))