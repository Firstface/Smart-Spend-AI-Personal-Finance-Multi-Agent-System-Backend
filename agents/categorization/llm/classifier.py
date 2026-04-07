"""
LLM 回退分类器（Layer 5）。

仅在前四层规则全部未命中时调用，最小化 LLM 成本。

课程对应：
- Structured Output（Day2）        — JSON Schema 约束输出，防止幻觉分类
- Tool Use Pattern（Day2）          — LangChain Tool 定义，供 Orchestrator 发现
- LLM06 Excessive Agency 缓解（Day3）— LLM 只返回分类建议，不执行任何副作用
- LLMSecOps 提示词版本化            — PROMPT_VERSION 追踪

双 LLM 路径：
- 优先使用 OPENAI_API_KEY（gpt-4o-mini）
- 无 OpenAI Key 时自动切换到 GROQ_API_KEY（llama-3.1-8b-instant）
"""
import os
import logging
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.tools import tool

from schemas.transaction import CategoryEnum
from agents.categorization.config import (
    CATEGORIES_DISPLAY, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE, PROMPT_VERSION
)

logger = logging.getLogger("categorization.llm")

# ── 提示词模板（版本化管理）─────────────────────────────────────────────────────
CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", f"""你是一个个人支出分类助手（提示词版本 {PROMPT_VERSION}）。
根据商家名和商品描述，将交易分类到以下类别之一：
{{categories}}

严格要求：
1. 只输出 JSON，不输出任何其他文字
2. category 必须是上述类别之一的完整中文名称
3. subcategory 可选，用一个更细的子类别（如 "奶茶"、"打车" 等），没有则填 null
4. rationale 用一句话解释分类依据
5. confidence 范围 0.0-1.0；不确定时应低于 0.6，切勿虚报高分
6. 不要根据金额大小推断分类，只根据商家名和描述内容

输出格式（严格 JSON）：
{{{{"category": "...", "subcategory": "...", "rationale": "...", "confidence": 0.0}}}}"""),
    ("human", "商家：{counterparty}\n商品描述：{description}"),
])


# ── LangChain Tool 定义（供 Orchestrator 发现） ────────────────────────────────
@tool
def classify_transaction_tool(counterparty: str, description: str) -> dict:
    """使用 LLM 对无法被规则匹配的交易进行分类。输入商家名和商品描述，返回分类结果。"""
    # 实际逻辑由 llm_classify() 异步执行
    pass


# ── LLM 工厂：优先 OpenAI，回退 Groq ──────────────────────────────────────────
def _get_llm():
    """
    返回可用的 LLM 实例。
    优先 gpt-4o-mini（OpenAI），无 Key 时回退到 llama-3.1-8b-instant（Groq）。
    """
    openai_key = os.getenv("OPENAI_API_KEY", "")
    groq_key = os.getenv("GROQ_API_KEY", "")

    if openai_key and openai_key != "sk-xxx":
        from langchain_openai import ChatOpenAI
        logger.debug("LLM 路径: OpenAI gpt-4o-mini")
        return ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            api_key=openai_key,
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
            return ChatOpenAI(
                model=LLM_MODEL,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )
    else:
        from langchain_openai import ChatOpenAI
        logger.warning("未检测到有效 LLM Key，使用默认 OpenAI（可能失败）")
        return ChatOpenAI(model=LLM_MODEL, temperature=LLM_TEMPERATURE, max_tokens=LLM_MAX_TOKENS)


# ── 主分类函数 ─────────────────────────────────────────────────────────────────
async def llm_classify(
    counterparty: str,
    description: Optional[str],
) -> tuple[CategoryEnum, str, float]:
    """
    受限 LLM 分类器。
    返回 (CategoryEnum, rationale字符串, confidence浮点数)。

    输出保护：
    - category 必须在 CategoryEnum 合法值内，否则降级为 OTHER
    - confidence 强制夹值到 [0.0, 1.0]
    - JSON 解析失败时返回安全默认值（OTHER, conf=0.3）
    """
    llm = _get_llm()
    chain = CLASSIFY_PROMPT | llm | JsonOutputParser()

    try:
        result = await chain.ainvoke({
            "categories": CATEGORIES_DISPLAY,
            "counterparty": counterparty,
            "description": description or "无描述",
        })

        # ── 输出验证（Guardrail）──────────────────────────────────────────────
        cat_str = result.get("category", "其他")
        valid_cats = {e.value for e in CategoryEnum}
        if cat_str not in valid_cats:
            logger.warning(
                f"LLM 输出非法分类 '{cat_str}'，降级为 '其他'。"
                f" counterparty={counterparty}"
            )
            cat_str = "其他"

        confidence = float(result.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        rationale = result.get("rationale", "LLM分类")
        subcategory = result.get("subcategory") or None

        logger.info(
            f"llm_classify: '{counterparty}' → {cat_str} "
            f"conf={confidence:.2f} prompt_ver={PROMPT_VERSION}"
        )

        # 将 subcategory 附加到 rationale，pipeline 层可提取
        if subcategory:
            rationale = f"[{subcategory}] {rationale}"

        return (CategoryEnum(cat_str), rationale, confidence)

    except Exception as e:
        logger.error(f"LLM 分类失败: {counterparty} — {e}")
        # 安全回退：OTHER + 低置信度，确保进入审查队列
        return (CategoryEnum.OTHER, f"LLM调用失败: {str(e)[:80]}", 0.3)
