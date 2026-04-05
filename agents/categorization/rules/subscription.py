"""
订阅检测启发式（Layer 3）— confidence = 0.90。

基于历史交易检测周期性重复消费（订阅服务）。
条件：同一商家在历史中出现 ≥2 次，且金额偏差 < 10%。

课程对应：长期记忆（DB历史交易）+ 启发式规则，零LLM成本。
"""
from typing import Optional, List
from schemas.transaction import CategoryEnum, CategorizedTransaction


def detect_subscription(
    counterparty: str,
    amount: float,
    history: List[CategorizedTransaction],
) -> Optional[tuple[CategoryEnum, float, str]]:
    """
    返回 (SUBSCRIPTION, 0.90, 证据字符串) 或 None。

    算法：
    1. 筛选历史中同商家的支出记录（名称包含匹配，不区分大小写）
    2. 若出现次数 ≥ 2 且历史金额与当前金额偏差均 < 10%，判断为订阅
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

    # 历史金额偏差 < 10%（相对平均值）
    if avg_amount == 0:
        return None
    all_close = all(abs(a - avg_amount) / avg_amount < 0.10 for a in amounts)

    # 当前金额也与历史均值偏差 < 10%
    current_close = abs(amount - avg_amount) / avg_amount < 0.10 if avg_amount > 0 else False

    if all_close and current_close:
        return (
            CategoryEnum.SUBSCRIPTION,
            0.90,
            f"订阅检测: '{counterparty}' 历史出现 {len(same_merchant)} 次，"
            f"金额约 ¥{avg_amount:.2f}，偏差 <10%",
        )

    return None
