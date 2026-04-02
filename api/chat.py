"""
POST /api/chat — 聊天入口（含快速记账）。

流程：
  1. 判断消息是否为快速记账指令（含金额模式）
  2. 是 → 解析出商家+金额，跑分类管线，写入数据库，返回格式化确认
  3. 否 → 返回通用回复（后续由教育Agent/规划Agent接管）

返回格式：
  { "reply": "...", "type": "quick_entry" | "general", "transaction": {...} }
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from agents.categorization.quick_entry import parse_quick_entry
from agents.categorization.agent import run_single
from api.deps import get_user_id

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger("api.chat")

# emoji 映射
EMOJI_MAP = {
    "餐饮美食": "🍜",
    "交通出行": "🚗",
    "居住":     "🏠",
    "购物":     "🛒",
    "娱乐休闲": "🎭",
    "订阅服务": "📱",
    "医疗健康": "🏥",
    "日用百货": "📦",
    "教育":     "📚",
    "其他":     "❓",
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
        return {"reply": "请输入消息", "type": "error"}

    logger.info(f"chat | user={user_id} message='{message[:60]}'")

    # ── Step 1: 尝试快速记账解析 ───────────────────────────────────────────────
    entry_result = await parse_quick_entry(message)

    if entry_result.success and entry_result.transaction:
        # ── Step 2: 跑完整分类管线并写入数据库 ───────────────────────────────
        try:
            cat_txn = await run_single(entry_result.transaction, user_id, db)
        except Exception as e:
            logger.error(f"quick_entry classify failed: {e}")
            return {
                "reply": f"记账解析成功，但分类写入失败：{str(e)[:80]}\n请稍后重试。",
                "type": "error",
            }

        # ── Step 3: 生成回复消息 ──────────────────────────────────────────────
        cat_name = cat_txn.category.value if hasattr(cat_txn.category, "value") else str(cat_txn.category)
        emoji = EMOJI_MAP.get(cat_name, "❓")

        reply_lines = [
            f"✅ 已记录：**{cat_txn.counterparty}** ¥{cat_txn.amount:.2f}",
            f"分类：{emoji} {cat_name}（置信度 {cat_txn.confidence:.2f}）",
            f"依据：{cat_txn.evidence}",
        ]

        if cat_txn.needs_review:
            reply_lines.append(
                "\n⚠️ 置信度较低，已加入待审查队列，请前往「分类结果」页确认。"
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

    # ── Step 4: 不是记账指令 → 通用回复 ──────────────────────────────────────
    general_reply = (
        f"收到你的消息：「{message}」\n\n"
        "目前聊天功能支持**快速记账**，例如：\n"
        "• `星巴克 38元`\n"
        "• `Grab $12.80`\n"
        "• `Netflix $15.99`\n"
        "• `午饭 美团 45元`\n\n"
        "教育助手和规划助手即将上线，敬请期待 🚀"
    )

    return {
        "reply": general_reply,
        "type": "general",
    }
