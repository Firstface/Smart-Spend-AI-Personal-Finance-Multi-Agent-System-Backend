"""
异常检测模块。

负责检测异常支出。
"""
from typing import List
import statistics
from collections import defaultdict
import logging

from models.transaction import Transaction
from schemas.insights import UnusualSpending

logger = logging.getLogger("insights.analysis.anomaly")


from agents.insights.utils import cached_analysis


@cached_analysis()
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
    
    # 额外的异常检测：基于交易频率
    unusual_spendings.extend(_detect_frequency_anomalies(transactions))
    
    # 去重并排序
    unique_unusual = _deduplicate_unusual_spendings(unusual_spendings)
    return sorted(unique_unusual, key=lambda x: abs(x.deviation), reverse=True)[:5]  # 前5大异常支出


def _detect_frequency_anomalies(transactions: List[Transaction]) -> List[UnusualSpending]:
    """
    基于交易频率检测异常
    
    Args:
        transactions: 交易列表
    
    Returns:
        List[UnusualSpending]: 基于频率的异常支出列表
    """
    # 按商家分组
    merchant_transactions = defaultdict(list)
    for txn in transactions:
        merchant_transactions[txn.counterparty].append(txn)
    
    frequency_anomalies = []
    
    for merchant, txns in merchant_transactions.items():
        if len(txns) > 5:  # 交易次数较多的商家
            # 计算交易间隔
            txns.sort(key=lambda x: x.transaction_time)
            intervals = []
            for i in range(1, len(txns)):
                interval = (txns[i].transaction_time - txns[i-1].transaction_time).days
                intervals.append(interval)
            
            if len(intervals) >= 3:
                mean_interval = statistics.mean(intervals)
                stdev_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0
                
                # 检测异常间隔
                for i, interval in enumerate(intervals):
                    if stdev_interval > 0 and abs(interval - mean_interval) > 2 * stdev_interval:
                        # 标记为异常的交易
                        txn = txns[i]
                        frequency_anomalies.append(UnusualSpending(
                            transaction_id=str(txn.id),
                            date=txn.transaction_time,
                            amount=txn.amount,
                            category=txn.category,
                            counterparty=merchant,
                            deviation=abs(interval - mean_interval) / stdev_interval if stdev_interval > 0 else 0
                        ))
    
    return frequency_anomalies


def _deduplicate_unusual_spendings(unusual_spendings: List[UnusualSpending]) -> List[UnusualSpending]:
    """
    去重异常支出
    
    Args:
        unusual_spendings: 异常支出列表
    
    Returns:
        List[UnusualSpending]: 去重后的异常支出列表
    """
    seen_ids = set()
    unique_spendings = []
    
    for spending in unusual_spendings:
        if spending.transaction_id not in seen_ids:
            seen_ids.add(spending.transaction_id)
            unique_spendings.append(spending)
    
    return unique_spendings