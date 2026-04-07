"""
Self-reflection loop (Layer 6).

Triggered only when the LLM fallback (Layer 5) confidence is below the threshold.
An independent "reviewer" prompt re-evaluates the classification result and iteratively improves it.

Course reference:
- Self-Reflection Pattern (Day2 PPT Slide 45-46)
  — Agent critically evaluates its own output, forming an improvement loop
- Two LLM calls use different temperatures:
    classifier  temperature=0   (deterministic)
    reflector   temperature=0.1 (slight randomness to explore different perspectives)
- Reflection rounds capped at REFLECTION_MAX_ROUNDS to prevent infinite loops (LLM04 mitigation)
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

# ── Reflection prompt ───────────────────────────────────────────────────────────
REFLECTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a classification quality reviewer. The previous classifier returned a low-confidence result. Please independently evaluate it and provide your judgment.

Previous classification result:
- Category: {previous_category}
- Confidence: {previous_confidence}
- Rationale: {previous_rationale}

Available categories:
{categories}

Review criteria:
1. Is the previous classification reasonable? Is there a more accurate category?
2. Does the confidence truly reflect the uncertainty?
3. If you agree with the previous result, increase the confidence and explain why
4. If you disagree, provide a new category and explain your correction

Output JSON only — no other text:
{{"category": "...", "confidence": 0.0, "rationale": "...", "agrees_with_previous": true}}"""),
    ("human", "Merchant: {counterparty}\nGoods description: {description}"),
])


# ── Reflection main function ────────────────────────────────────────────────────
async def reflect_on_classification(
    counterparty: str,
    description: Optional[str],
    previous_category: str,
    previous_confidence: float,
    previous_rationale: str,
    max_rounds: int = REFLECTION_MAX_ROUNDS,
) -> tuple[CategoryEnum, float, str, int]:
    """
    Self-reflection loop: iteratively improves low-confidence LLM results.

    Decision logic (per round):
    ┌──────────────────────────────────────────────────────────────────────┐
    │ agrees=True  AND new_conf ≥ current_conf → accept, boost confidence  │
    │ agrees=False AND new_conf > current_conf → adopt new classification  │
    │ Otherwise (reflection did not improve)   → early termination         │
    └──────────────────────────────────────────────────────────────────────┘

    Returns: (final CategoryEnum, final confidence, final evidence string, actual rounds used)
    """
    from agents.categorization.llm.classifier import _get_llm  # reuse LLM factory

    llm = _get_llm()
    # Reflector uses slightly higher temperature to explore different perspectives
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
                "description": description or "No description",
            })
        except Exception as e:
            logger.error(f"Reflection round {i+1} call failed: {e}")
            break

        # ── Output parsing and validation ──────────────────────────────────────
        new_cat_str = result.get("category", current_cat)
        if new_cat_str not in valid_cats:
            logger.warning(f"Reflection returned invalid category '{new_cat_str}', keeping original")
            new_cat_str = current_cat

        new_conf = float(result.get("confidence", current_conf))
        new_conf = max(0.0, min(1.0, new_conf))
        new_rationale = result.get("rationale", "")
        agrees = result.get("agrees_with_previous", True)
        actual_rounds = i + 1

        logger.info(
            f"Reflection round {actual_rounds}: "
            f"{current_cat}({current_conf:.2f}) → {new_cat_str}({new_conf:.2f}) "
            f"agrees={agrees} counterparty='{counterparty}'"
        )

        if agrees and new_conf >= current_conf:
            # Reflection confirms original classification; accept confidence boost
            current_conf = new_conf
            current_cat = new_cat_str
            current_rationale = f"[Reflection confirmed round {actual_rounds}] {new_rationale}"
            break

        elif not agrees and new_conf > current_conf:
            # Reflection found a better classification; adopt it
            current_cat = new_cat_str
            current_conf = new_conf
            current_rationale = f"[Reflection corrected round {actual_rounds}] {new_rationale}"
            # Continue to next round to validate the new classification
            continue

        else:
            # Reflection did not improve the result; terminate early to avoid wasting LLM calls
            logger.info(f"Reflection did not improve, early termination (round {actual_rounds})")
            break

    # Final safety validation
    final_cat = CategoryEnum(current_cat) if current_cat in valid_cats else CategoryEnum.OTHER

    return (final_cat, current_conf, current_rationale, actual_rounds)
