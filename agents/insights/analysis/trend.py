"""
趋势分析模块。

负责分析支出趋势。
"""
from typing import List, Dict
from datetime import datetime
from collections import defaultdict

from models.transaction import Transaction
from agents.insights.schemas import SpendingTrend


def analyze_spending_trends(
    transactions: List[Transaction],
    start_date: datetime,
    end_date: datetime
) -> List[SpendingTrend]:
    """
    分析支出趋势
    
    Args:
        transactions: 交易列表
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        List[SpendingTrend]: 趋势列表
    """
    # 按月份和类别分组
    monthly_category_data = defaultdict(lambda: defaultdict(float))
    for txn in transactions:
        if txn.category:
            month_key = txn.transaction_time.strftime("%Y-%m")
            monthly_category_data[month_key][txn.category] += txn.amount
    
    # 计算每个类别的趋势
    category_trends = defaultdict(list)
    for month, categories in sorted(monthly_category_data.items()):
        for category, amount in categories.items():
            category_trends[category].append((month, amount))
    
    # 生成趋势分析
    trends = []
    for category, data in category_trends.items():
        if len(data) > 1:
            # 计算增长率
            first_amount = data[0][1]
            last_amount = data[-1][1]
            growth_rate = ((last_amount - first_amount) / first_amount * 100) if first_amount > 0 else 0
            
            trends.append(SpendingTrend(
                category=category,
                data_points=data,
                growth_rate=growth_rate
            ))
    
    return sorted(trends, key=lambda x: abs(x.growth_rate), reverse=True)[:5]  # 前5大变化趋势