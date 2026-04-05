"""
Follow-up & Insights Agent 服务层。

包含生成各种财务洞察的核心业务逻辑。
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from models.transaction import Transaction
from agents.insights.schemas import MonthlySummary, SpendingRecommendation, CategorySummary
from agents.insights.analysis.trend import analyze_spending_trends
from agents.insights.analysis.anomaly import detect_unusual_spending
from agents.insights.analysis.subscription import aggregate_subscriptions
from agents.insights.recommendations.generator import generate_spending_recommendations


def generate_monthly_summary(
    transactions: List[Transaction],
    start_date: datetime,
    end_date: datetime
) -> MonthlySummary:
    """
    生成月度财务摘要
    
    Args:
        transactions: 交易列表
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        MonthlySummary: 月度摘要
    """
    # 按月份分组
    monthly_data = defaultdict(list)
    for txn in transactions:
        month_key = txn.transaction_time.strftime("%Y-%m")
        monthly_data[month_key].append(txn)
    
    # 计算每月总支出
    monthly_totals = {}
    for month, txns in monthly_data.items():
        total = sum(txn.amount for txn in txns)
        monthly_totals[month] = total
    
    # 计算分类支出
    category_totals = defaultdict(float)
    for txn in transactions:
        if txn.category:
            category_totals[txn.category] += txn.amount
    
    # 计算总支出
    total_expense = sum(category_totals.values())
    
    # 生成分类摘要
    category_summaries = []
    for category, amount in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
        percentage = (amount / total_expense * 100) if total_expense > 0 else 0
        category_summaries.append(CategorySummary(
            category=category,
            amount=amount,
            percentage=percentage
        ))
    
    return MonthlySummary(
        total_expense=total_expense,
        monthly_totals=monthly_totals,
        top_categories=category_summaries[:5],  # 前5大支出类别
        average_monthly_spending=total_expense / len(monthly_data) if monthly_data else 0
    )