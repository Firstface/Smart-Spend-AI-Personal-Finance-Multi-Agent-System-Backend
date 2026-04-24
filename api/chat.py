"""
POST /api/chat — Chat entry point (includes quick expense entry).

Flow:
  1. Determine whether the message is a quick expense entry command (contains amount pattern)
  2. Yes → parse merchant + amount, run classification pipeline, write to DB, return formatted confirmation
  3. No  → if intent looks like personal-finance education → Education RAG agent; else general reply

Response format:
  { "reply": "...", "type": "quick_entry" | "education" | "general" | "error", "transaction": {...} }
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from agents.categorization.quick_entry import parse_quick_entry
from agents.chat_routing import should_route_to_education
from api.deps import get_user_id

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger("api.chat")

# Emoji mapping for categories (keyed by DB value)
EMOJI_MAP = {
    "Food & Dining": "🍜",
    "Transportation": "🚗",
    "Housing": "🏠",
    "Shopping": "🛒",
    "Entertainment": "🎭",
    "Subscriptions": "📱",
    "Healthcare": "🏥",
    "Daily Essentials": "📦",
    "Education": "📚",
    "Other": "❓",
}

# English display names for categories (DB value → English label)
CATEGORY_DISPLAY = {
    "Food & Dining": "Food & Dining",
    "Transportation": "Transportation",
    "Housing": "Housing",
    "Shopping": "Shopping",
    "Entertainment": "Entertainment",
    "Subscriptions": "Subscriptions",
    "Healthcare": "Healthcare",
    "Daily Essentials": "Daily Essentials",
    "Education": "Education",
    "Other": "Other",
}


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    message = body.message.strip()
    if not message:
        return {"reply": "Please enter a message", "type": "error"}

    logger.info(f"chat | user={user_id} message='{message[:60]}'")

    # ── Step 1: Attempt quick expense entry parsing ────────────────────────────
    entry_result = await parse_quick_entry(message)

    if entry_result.success and entry_result.transaction:
        # ── Step 2: Run full classification pipeline and write to database ─────
        try:
            # Lazy import avoids loading heavy LLM stack during module import
            # when quick-entry classification is not needed (e.g., many tests).
            from agents.categorization.agent import run_single
            cat_txn = await run_single(entry_result.transaction, user_id, db)
        except Exception as e:
            logger.error(f"quick_entry classify failed: {e}")
            return {
                "reply": f"Expense parsed successfully, but classification/save failed: {str(e)[:80]}\nPlease try again later.",
                "type": "error",
            }

        # ── Step 3: Generate reply message ────────────────────────────────────
        cat_name = cat_txn.category.value if hasattr(cat_txn.category, "value") else str(cat_txn.category)
        emoji = EMOJI_MAP.get(cat_name, "❓")
        cat_display = CATEGORY_DISPLAY.get(cat_name, cat_name)

        reply_lines = [
            f"✅ Recorded: **{cat_txn.counterparty}** ¥{cat_txn.amount:.2f}",
            f"Category: {emoji} {cat_display} (confidence {cat_txn.confidence:.2f})",
            f"Evidence: {cat_txn.evidence}",
        ]

        if cat_txn.needs_review:
            reply_lines.append(
                "\n⚠️ Low confidence — added to the review queue. Please visit the Classification page to confirm."
            )

        reply = "\n".join(reply_lines)

        logger.info(
            f"quick_entry success | user={user_id} "
            f"counterparty='{cat_txn.counterparty}' amount={cat_txn.amount} "
            f"category={cat_name} conf={cat_txn.confidence:.2f}"
        )

        return {
            "reply": reply,
            "type": "quick_entry",
            "transaction": cat_txn.model_dump(mode="json"),
        }

    # ── Step 4: Intent routing → Education agent or general reply ───────────────
    if should_route_to_education(message):
        try:
            from agents.education.service import answer_question

            edu = answer_question(question=message, user_id=user_id)
            reply_text = edu.get("answer") or ""
            citations = edu.get("citations") or []
            if isinstance(citations, list) and citations:
                titles: list[str] = []
                seen_t: set[str] = set()
                for c in citations:
                    if not isinstance(c, dict):
                        continue
                    t = str(c.get("title") or "").strip()
                    if t and t not in seen_t:
                        seen_t.add(t)
                        titles.append(t)
                if titles:
                    reply_text = reply_text.rstrip() + "\n\n📚 " + ", ".join(titles[:6])

            return {
                "reply": reply_text,
                "type": "education",
            }
        except Exception as e:
            logger.warning("education agent from chat failed: %s", e)

    general_reply = (
        f"Got your message: \"{message}\"\n\n"
        "The chat currently supports **quick expense entry**, for example:\n"
        "• `Starbucks $5.50`\n"
        "• `Grab $12.80`\n"
        "• `Netflix $15.99`\n"
        "• `Lunch Meituan $10`\n\n"
        "Ask a **personal finance learning** question (e.g. budgeting, saving, credit) "
        "to use the education assistant, or try quick entry above."
    )

    return {
        "reply": general_reply,
        "type": "general",
    }
