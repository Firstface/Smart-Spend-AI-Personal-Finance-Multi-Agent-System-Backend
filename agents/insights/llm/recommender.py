"""
LLM 智能建议生成器。

使用大模型生成个性化的财务建议，基于用户的交易数据和财务状况。

双 LLM 路径：
- 优先使用 OPENAI_API_KEY（gpt-4o-mini）
- 无 OpenAI Key 时自动切换到 GROQ_API_KEY（llama-3.1-8b-instant）
"""
import os
import logging
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from schemas.insights import SpendingRecommendation
from agents.insights.config import (
    LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE, PROMPT_VERSION
)

logger = logging.getLogger("insights.llm")

# ── 提示词模板（版本化管理）─────────────────────────────────────────────────────
RECOMMENDATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", f"""你是一位专业的财务顾问（提示词版本 {PROMPT_VERSION}）。
基于用户的财务数据，生成个性化的财务建议。

严格要求：
1. 只输出 JSON，不输出任何其他文字
2. 建议应基于用户的实际支出模式，具有针对性和可操作性
3. 每个建议应包含：type（建议类型）、title（标题）、description（详细描述）、priority（优先级：high/medium/low）
4. 生成 3-5 条建议
5. 建议应多样化，覆盖不同的财务方面

输出格式（严格 JSON）：
{{{{
  "recommendations": [
    {{{{
      "type": "...",
      "title": "...",
      "description": "...",
      "priority": "..."
    }}}}
  ]
}}}}"""),
    ("human", """月度财务摘要：
- 总支出：{total_expense:.2f}元
- 月均支出：{average_monthly_spending:.2f}元
- 前5大支出类别：
{top_categories}

最近的交易：
{recent_transactions}

请生成个性化的财务建议。"""),
])


# ── LLM 工厂：优先 OpenAI，回退 Groq ──────────────────────────────────────────
def _get_llm():
    """
    返回可用的 LLM 实例。
    优先 gpt-4o-mini（OpenAI），无 Key 时回退到 llama-3.1-8b-instant（Groq）。
    """
    logger.debug("开始获取 LLM 实例...")
    
    openai_key = os.getenv("OPENAI_API_KEY", "")
    groq_key = os.getenv("GROQ_API_KEY", "")
    openai_base = os.getenv("OPENAI_API_BASE", "")
    openai_model = os.getenv("OPENAI_MODEL", LLM_MODEL)
    
    logger.debug(f"环境变量检查: OPENAI_API_KEY={'***' if openai_key else '未设置'}")
    logger.debug(f"环境变量检查: GROQ_API_KEY={'***' if groq_key else '未设置'}")
    logger.debug(f"环境变量检查: OPENAI_API_BASE={openai_base if openai_base else '未设置'}")
    logger.debug(f"环境变量检查: OPENAI_MODEL={openai_model}")

    if openai_key and openai_key != "sk-xxx":
        from langchain_openai import ChatOpenAI
        logger.debug(f"LLM 路径: OpenAI {openai_model}")
        logger.debug(f"使用 base_url: {openai_base if openai_base else '默认'}")
        return ChatOpenAI(
            model=openai_model,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            api_key=openai_key,
            base_url=openai_base if openai_base else None,
        )
    elif groq_key:
        try:
            from langchain_groq import ChatGroq
            logger.debug("LLM 路径: Groq llama-3.1-8b-instant")
            return ChatGroq(
                model="llama-3.1-8b-instant",
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                api_key=groq_key,
            )
        except ImportError:
            logger.warning("langchain_groq 未安装，回退到 OpenAI（即使 key 为占位符）")
            from langchain_openai import ChatOpenAI
            logger.debug(f"回退到 OpenAI {openai_model}")
            return ChatOpenAI(
                model=openai_model,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                base_url=openai_base if openai_base else None,
            )
    else:
        from langchain_openai import ChatOpenAI
        logger.warning("未检测到有效 LLM Key，使用默认 OpenAI（可能失败）")
        logger.debug(f"使用默认 OpenAI {openai_model}")
        return ChatOpenAI(
            model=openai_model,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            base_url=openai_base if openai_base else None,
        )


# ── 主建议生成函数 ─────────────────────────────────────────────────────────────
async def generate_ai_recommendations(
    total_expense: float,
    average_monthly_spending: float,
    top_categories: str,
    recent_transactions: str
) -> List[SpendingRecommendation]:
    """
    使用 LLM 生成智能财务建议。
    
    Args:
        total_expense: 总支出
        average_monthly_spending: 月均支出
        top_categories: 前5大支出类别
        recent_transactions: 最近的交易
    
    Returns:
        List[SpendingRecommendation]: AI 生成的建议列表
    """
    logger.debug("开始生成 AI 建议...")
    
    # 获取 LLM 实例
    llm = _get_llm()
    logger.debug(f"获取到 LLM 实例: {type(llm).__name__}")
    
    # 构建 LLM 调用链
    chain = RECOMMENDATION_PROMPT | llm | JsonOutputParser()
    logger.debug("构建 LLM 调用链完成")

    try:
        # 准备输入数据
        input_data = {
            "total_expense": total_expense,
            "average_monthly_spending": average_monthly_spending,
            "top_categories": top_categories,
            "recent_transactions": recent_transactions
        }
        
        logger.debug("开始调用 LLM 生成建议...")
        logger.debug(f"输入数据 - 总支出: {total_expense:.2f}, 月均支出: {average_monthly_spending:.2f}")
        logger.debug(f"前5大支出类别: {top_categories}")
        logger.debug(f"最近交易: {recent_transactions}")
        
        # 调用 LLM
        result = await chain.ainvoke(input_data)
        
        logger.debug(f"LLM 调用成功，返回结果: {result}")

        # ── 输出验证 ─────────────────────────────────────────────────────
        recommendations = []
        for rec in result.get("recommendations", []):
            try:
                recommendation = SpendingRecommendation(
                    type=rec.get("type", "财务建议"),
                    title=rec.get("title", "未命名建议"),
                    description=rec.get("description", ""),
                    priority=rec.get("priority", "medium")
                )
                recommendations.append(recommendation)
            except Exception as e:
                logger.warning(f"解析建议失败: {e}")
                logger.debug(f"失败的建议数据: {rec}")
                continue

        logger.info(f"AI 生成了 {len(recommendations)} 条建议")
        logger.debug(f"生成的建议: {[rec.title for rec in recommendations]}")
        return recommendations

    except Exception as e:
        logger.error(f"LLM 建议生成失败: {e}")
        logger.debug(f"LLM 调用详细错误: {str(e)}")
        logger.debug(f"错误类型: {type(e).__name__}")
        # 安全回退：返回空列表
        return []