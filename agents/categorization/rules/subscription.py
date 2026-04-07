"""
Subscription detection heuristic (Layer 3) — confidence = 0.90.

Detects recurring periodic charges (subscription services) based on transaction history.
Conditions: same merchant appears ≥2 times in history with amount deviation < 10%.

Course reference: Long-term memory (DB transaction history) + heuristic rules, zero LLM cost.
"""
from typing import Optional, List
from schemas.transaction import CategoryEnum, CategorizedTransaction


def detect_subscription(
    counterparty: str,
    amount: float,
    history: List[CategorizedTransaction],
) -> Optional[tuple[CategoryEnum, float, str]]:
    """
    Returns (SUBSCRIPTION, 0.90, evidence string) or None.

    Algorithm:
    1. Filter history for expense records from the same merchant (case-insensitive substring match)
    2. If occurrences ≥ 2 and all historical amounts are within 10% of average,
       and the current amount is also within 10% of average — classify as subscription
    """
    if not counterparty or not history:
        return None

    normalized = counterparty.lower().strip()
    same_merchant = [
        t for t in history
        if normalized in t.counterparty.lower()
        and t.direction.value == "expense"
        and t.amount > 0
    ]

    if len(same_merchant) < 2:
        return None

    amounts = [t.amount for t in same_merchant]
    avg_amount = sum(amounts) / len(amounts)

    # Historical amounts must all be within 10% of the average
    if avg_amount == 0:
        return None
    all_close = all(abs(a - avg_amount) / avg_amount < 0.10 for a in amounts)

    # Current amount must also be within 10% of the historical average
    current_close = abs(amount - avg_amount) / avg_amount < 0.10 if avg_amount > 0 else False

    if all_close and current_close:
        return (
            CategoryEnum.SUBSCRIPTION,
            0.90,
            f"Subscription detected: '{counterparty}' appeared {len(same_merchant)} times in history, "
            f"avg amount ¥{avg_amount:.2f}, deviation <10%",
        )

    return None
