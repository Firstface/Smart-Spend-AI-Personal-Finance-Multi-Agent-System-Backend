"""
订阅分析模块。

负责识别和汇总订阅服务。
"""
from typing import List, Dict
from collections import defaultdict

from models.transaction import Transaction
from agents.insights.schemas import SubscriptionSummary


def aggregate_subscriptions(transactions: List[Transaction]) -> SubscriptionSummary:
    """
    汇总订阅服务
    
    Args:
        transactions: 交易列表
    
    Returns:
        SubscriptionSummary: 订阅摘要
    """
    # 筛选订阅类别
    subscription_txns = [txn for txn in transactions if txn.category == "订阅服务"]
    
    # 按商家分组
    merchant_subscriptions = defaultdict(list)
    for txn in subscription_txns:
        merchant_subscriptions[txn.counterparty].append(txn)
    
    # 计算每个订阅的月均支出
    subscription_details = []
    total_monthly_subscription = 0
    
    for merchant, txns in merchant_subscriptions.items():
        # 计算月均支出
        if txns:
            total_amount = sum(txn.amount for txn in txns)
            # 假设最近3个月的数据
            months = len(set(txn.transaction_time.strftime("%Y-%m") for txn in txns))
            monthly_amount = total_amount / months if months > 0 else total_amount
            total_monthly_subscription += monthly_amount
            
            subscription_details.append({
                "merchant": merchant,
                "monthly_amount": monthly_amount,
                "last_charge_date": max(txn.transaction_time for txn in txns)
            })
    
    return SubscriptionSummary(
        total_monthly_subscription=total_monthly_subscription,
        subscriptions=subscription_details
    )