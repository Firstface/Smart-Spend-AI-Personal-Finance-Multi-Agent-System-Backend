"""
订阅分析模块。

负责识别和汇总订阅服务。
"""
from typing import List, Dict
from collections import defaultdict
import logging
from datetime import datetime, timedelta

from models.transaction import Transaction
from schemas.insights import SubscriptionSummary

logger = logging.getLogger("insights.analysis.subscription")


from agents.insights.utils import cached_analysis


@cached_analysis()
def aggregate_subscriptions(transactions: List[Transaction]) -> SubscriptionSummary:
    """
    汇总订阅服务
    
    Args:
        transactions: 交易列表
    
    Returns:
        SubscriptionSummary: 订阅摘要
    """
    # 识别订阅交易
    subscription_txns = _identify_subscription_transactions(transactions)
    
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
            # 计算实际月份数
            months = len(set(txn.transaction_time.strftime("%Y-%m") for txn in txns))
            monthly_amount = total_amount / months if months > 0 else total_amount
            total_monthly_subscription += monthly_amount
            
            subscription_details.append({
                "merchant": merchant,
                "monthly_amount": monthly_amount,
                "last_charge_date": max(txn.transaction_time for txn in txns),
                "charge_frequency": _calculate_charge_frequency(txns)
            })
    
    try:
        result = SubscriptionSummary(
            total_monthly_subscription=total_monthly_subscription,
            subscriptions=subscription_details
        )
        logger.info(f"汇总订阅成功，月均订阅支出: {total_monthly_subscription:.2f}元")
        return result
    except Exception as e:
        logger.error(f"汇总订阅失败: {e}")
        return SubscriptionSummary(
            total_monthly_subscription=0,
            subscriptions=[]
        )


def _identify_subscription_transactions(transactions: List[Transaction]) -> List[Transaction]:
    """
    识别订阅交易
    
    Args:
        transactions: 交易列表
    
    Returns:
        List[Transaction]: 识别出的订阅交易
    """
    subscription_txns = []
    
    # 1. 直接通过类别识别
    category_subscriptions = [txn for txn in transactions if txn.category == "订阅服务"]
    subscription_txns.extend(category_subscriptions)
    
    # 2. 通过交易模式识别
    pattern_subscriptions = _detect_subscription_patterns(transactions)
    subscription_txns.extend(pattern_subscriptions)
    
    # 去重
    seen_ids = set()
    unique_subscriptions = []
    for txn in subscription_txns:
        if txn.id not in seen_ids:
            seen_ids.add(txn.id)
            unique_subscriptions.append(txn)
    
    logger.info(f"识别出 {len(unique_subscriptions)} 笔订阅交易")
    return unique_subscriptions


def _detect_subscription_patterns(transactions: List[Transaction]) -> List[Transaction]:
    """
    通过交易模式检测订阅
    
    Args:
        transactions: 交易列表
    
    Returns:
        List[Transaction]: 基于模式识别的订阅交易
    """
    # 按商家分组
    merchant_transactions = defaultdict(list)
    for txn in transactions:
        merchant_transactions[txn.counterparty].append(txn)
    
    subscription_patterns = []
    
    for merchant, txns in merchant_transactions.items():
        if len(txns) >= 3:  # 至少3次交易
            # 按时间排序
            sorted_txns = sorted(txns, key=lambda x: x.transaction_time)
            
            # 检查交易间隔是否规律
            intervals = []
            for i in range(1, len(sorted_txns)):
                interval = (sorted_txns[i].transaction_time - sorted_txns[i-1].transaction_time).days
                intervals.append(interval)
            
            # 检查金额是否相似
            amounts = [txn.amount for txn in sorted_txns]
            amount_variation = max(amounts) - min(amounts) if amounts else 0
            avg_amount = sum(amounts) / len(amounts) if amounts else 0
            variation_ratio = amount_variation / avg_amount if avg_amount > 0 else 0
            
            # 规则：间隔相对规律且金额变化小
            if len(intervals) >= 2:
                avg_interval = sum(intervals) / len(intervals)
                interval_variation = max(intervals) - min(intervals)
                interval_variation_ratio = interval_variation / avg_interval if avg_interval > 0 else 0
                
                # 间隔变化小于50%，金额变化小于20%
                if interval_variation_ratio < 0.5 and variation_ratio < 0.2:
                    subscription_patterns.extend(txns)
    
    return subscription_patterns


def _calculate_charge_frequency(transactions: List[Transaction]) -> str:
    """
    计算订阅收费频率
    
    Args:
        transactions: 交易列表
    
    Returns:
        str: 收费频率描述
    """
    if len(transactions) < 2:
        return "未知"
    
    sorted_txns = sorted(transactions, key=lambda x: x.transaction_time)
    intervals = []
    for i in range(1, len(sorted_txns)):
        interval = (sorted_txns[i].transaction_time - sorted_txns[i-1].transaction_time).days
        intervals.append(interval)
    
    avg_interval = sum(intervals) / len(intervals)
    
    if avg_interval < 7:
        return "每周"
    elif avg_interval < 35:
        return "每月"
    elif avg_interval < 120:
        return "每季度"
    else:
        return "每年"