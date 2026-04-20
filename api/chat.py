"""
POST /api/chat — Chat entry point (includes quick expense entry).

Flow:
  1. Determine whether the message is a quick expense entry command (contains amount pattern)
  2. Yes → parse merchant + amount, run classification pipeline, write to DB, return formatted confirmation
  3. No  → if intent looks like personal-finance education → Education RAG agent; else general reply

Response format:
  { "reply": "...", "type": "quick_entry" | "education" | "insights" | "general" | "error", "transaction": {...}, "insights": {...} }
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from agents.categorization.quick_entry import parse_quick_entry
from agents.categorization.agent import run_single
from agents.chat_routing import should_route_to_education, should_route_to_insights, should_route_to_planning
from agents.planning.agent import PlanningAgent
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


def _build_insights_reply(insights: dict, original_message: str) -> str:
    summary = insights.get("monthly_summary") or {}
    total_expense = float(summary.get("total_expense") or 0.0)
    top_categories = summary.get("top_categories") or []
    unusual = insights.get("unusual_spending") or []
    subscriptions = (insights.get("subscriptions") or {}).get("subscriptions") or []
    recommendations = insights.get("recommendations") or []

    if total_expense <= 0 and not top_categories and not unusual and not subscriptions:
        return (
            f"I checked your recent spending for \"{original_message}\", but there isn't enough confirmed expense "
            "data yet. Add a few categorized transactions first, then ask again."
        )

    top_label = ""
    if isinstance(top_categories, list) and top_categories:
        top = top_categories[0] or {}
        category = str(top.get("category") or "Unknown")
        percentage = float(top.get("percentage") or 0.0)
        top_label = f"Top category: {category} ({percentage:.1f}%)."

    return (
        f"I reviewed your recent spending. Total expense is ¥{total_expense:.2f}. "
        f"{top_label} Detected {len(unusual)} unusual transaction(s), "
        f"{len(subscriptions)} subscription item(s), and {len(recommendations)} suggestion(s)."
    ).strip()


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

    # ── Step 4: Intent routing → Insights / Education agent or general reply ───
    if should_route_to_insights(message):
        try:
            from agents.insights.agent import generate_insights

            insights = await generate_insights(user_id=user_id, db=db, use_llm=False)
            insights_payload = insights.model_dump(mode="json")
            return {
                "reply": _build_insights_reply(insights_payload, message),
                "type": "insights",
                "insights": insights_payload,
            }
        except Exception as e:
            logger.warning("insights agent from chat failed: %s", e)

    if should_route_to_planning(message):
        logger.info(f"Routing to PlanningAgent based on message: '{message}'")
        try:
            # 直接调用你的 Agent 处理函数
            # 它会返回解析并处理后的 Markdown 字符串
            planning_agent = PlanningAgent()
            reply_text = await planning_agent.handle(message, user_id, db)
            
            return {
                "reply": reply_text,
                "type": "planning",  # 给前端一个明确的类型，方便做样式区分
            }
        except Exception as e:
            logger.error(f"planning agent from chat failed: {e}")
            return {"reply": f"Sorry, I had trouble processing your planning request: {str(e)[:80]}", "type": "error"}
            # 如果失败了，可以选择报错或者继续往下走让 general 兜底

    if should_route_to_education(message):
        logger.info(f"Routing to Education agent based on message: '{message}'")
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
