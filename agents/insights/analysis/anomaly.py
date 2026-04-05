"""
异常检测模块。

负责检测异常支出。
"""
from typing import List
import statistics
from collections import defaultdict

from models.transaction import Transaction
from agents.insights.schemas import UnusualSpending


def detect_unusual_spending(transactions: List[Transaction]) -> List[UnusualSpending]:
    """
    检测异常支出
    
    Args:
        transactions: 交易列表
    
    Returns:
        List[UnusualSpending]: 异常支出列表
    """
    # 按类别分组
    category_transactions = defaultdict(list)
    for txn in transactions:
        if txn.category:
            category_transactions[txn.category].append(txn)
    
    unusual_spendings = []
    
    # 分析每个类别的异常支出
    for category, txns in category_transactions.items():
        amounts = [txn.amount for txn in txns]
        if len(amounts) >= 3:  # 至少需要3个数据点
            mean = statistics.mean(amounts)
            stdev = statistics.stdev(amounts) if len(amounts) > 1 else 0
            
            # 检测异常值（超过2个标准差）
            for txn in txns:
                if stdev > 0 and abs(txn.amount - mean) > 2 * stdev:
                    unusual_spendings.append(UnusualSpending(
                        transaction_id=str(txn.id),
                        date=txn.transaction_time,
                        amount=txn.amount,
                        category=category,
                        counterparty=txn.counterparty,
                        deviation=(txn.amount - mean) / stdev if stdev > 0 else 0
                    ))
    
    return sorted(unusual_spendings, key=lambda x: abs(x.deviation), reverse=True)[:5]  # 前5大异常支出