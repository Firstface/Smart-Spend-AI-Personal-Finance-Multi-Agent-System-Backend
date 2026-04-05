"""
自反思循环（Layer 6）。

仅在 LLM 回退（Layer 5）置信度低于阈值时触发。
用独立的"审查员"提示词重新审视分类结果，迭代优化。

课程对应：
- Self-Reflection Pattern（Day2 PPT Slide 45-46）
  — Agent 对自身输出进行批判性评估，形成改进循环
- 两个 LLM 调用使用不同 temperature：
    classifier  temperature=0   （确定性）
    reflector   temperature=0.1 （允许轻微发散以发现不同视角）
- 反思轮数上限 = REFLECTION_MAX_ROUNDS，防止无限循环（LLM04 缓解）
"""
import logging
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from schemas.transaction import CategoryEnum
from agents.categorization.config import (
    CATEGORIES_DISPLAY,
    REFLECTION_MAX_ROUNDS,
    REFLECTION_TEMPERATURE,
    LLM_MODEL,
    LLM_MAX_TOKENS,
)

logger = logging.getLogger("categorization.reflection")

# ── 反思提示词 ─────────────────────────────────────────────────────────────────
REFLECTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个分类质量审查员。上一个分类器给出了低置信度结果，请独立审视并给出你的判断。

上次分类结果：
- 类别：{previous_category}
- 置信度：{previous_confidence}
- 理由：{previous_rationale}

可选类别列表：
{categories}

审查要点：
1. 上次的分类是否合理？是否有更准确的类别？
2. 置信度是否真实反映了不确定性？
3. 如果你同意上次结果，请提升置信度并说明原因
4. 如果你不同意，请给出新的分类并说明修正理由

只输出 JSON，不输出其他文字：
{{"category": "...", "confidence": 0.0, "rationale": "...", "agrees_with_previous": true}}"""),
    ("human", "商家：{counterparty}\n商品描述：{description}"),
])


# ── 反思主函数 ─────────────────────────────────────────────────────────────────
async def reflect_on_classification(
    counterparty: str,
    description: Optional[str],
    previous_category: str,
    previous_confidence: float,
    previous_rationale: str,
    max_rounds: int = REFLECTION_MAX_ROUNDS,
) -> tuple[CategoryEnum, float, str, int]:
    """
    自反思循环：对低置信度 LLM 结果进行迭代优化。

    决策逻辑（每轮）：
    ┌─────────────────────────────────────────────────────────────┐
    │ agrees=True  AND new_conf ≥ current_conf → 接受，提升置信度  │
    │ agrees=False AND new_conf > current_conf → 采纳新分类        │
    │ 其他（反思未改善）                        → 提前终止         │
    └─────────────────────────────────────────────────────────────┘

    返回：(最终CategoryEnum, 最终置信度, 最终证据字符串, 实际反思轮数)
    """
    from agents.categorization.llm.classifier import _get_llm  # 复用 LLM 工厂

    llm = _get_llm()
    # 反思器使用略高 temperature，允许发现不同视角
    if hasattr(llm, "temperature"):
        llm.temperature = REFLECTION_TEMPERATURE

    chain = REFLECTION_PROMPT | llm | JsonOutputParser()

    current_cat = previous_category
    current_conf = previous_confidence
    current_rationale = previous_rationale
    actual_rounds = 0

    valid_cats = {e.value for e in CategoryEnum}

    for i in range(max_rounds):
        try:
            result = await chain.ainvoke({
                "previous_category": current_cat,
                "previous_confidence": f"{current_conf:.2f}",
                "previous_rationale": current_rationale,
                "categories": CATEGORIES_DISPLAY,
                "counterparty": counterparty,
                "description": description or "无描述",
            })
        except Exception as e:
            logger.error(f"反思第{i+1}轮调用失败: {e}")
            break

        # ── 输出解析与验证 ────────────────────────────────────────────────────
        new_cat_str = result.get("category", current_cat)
        if new_cat_str not in valid_cats:
            logger.warning(f"反思输出非法类别 '{new_cat_str}'，保持原值")
            new_cat_str = current_cat

        new_conf = float(result.get("confidence", current_conf))
        new_conf = max(0.0, min(1.0, new_conf))
        new_rationale = result.get("rationale", "")
        agrees = result.get("agrees_with_previous", True)
        actual_rounds = i + 1

        logger.info(
            f"反思第{actual_rounds}轮: "
            f"{current_cat}({current_conf:.2f}) → {new_cat_str}({new_conf:.2f}) "
            f"agrees={agrees} counterparty='{counterparty}'"
        )

        if agrees and new_conf >= current_conf:
            # 反思确认原分类，接受置信度提升
            current_conf = new_conf
            current_cat = new_cat_str
            current_rationale = f"[反思确认第{actual_rounds}轮] {new_rationale}"
            break

        elif not agrees and new_conf > current_conf:
            # 反思发现更好的分类，采纳
            current_cat = new_cat_str
            current_conf = new_conf
            current_rationale = f"[反思修正第{actual_rounds}轮] {new_rationale}"
            # 继续下一轮验证新分类
            continue

        else:
            # 反思未能改善结果，提前终止，避免浪费 LLM 调用
            logger.info(f"反思未改善，提前终止（第{actual_rounds}轮）")
            break

    # 最终安全验证
    final_cat = CategoryEnum(current_cat) if current_cat in valid_cats else CategoryEnum.OTHER

    return (final_cat, current_conf, current_rationale, actual_rounds)
