"""
趋势分析模块。

负责分析支出趋势。
"""
from typing import List, Dict, Tuple
from datetime import datetime
from collections import defaultdict
import logging

from models.transaction import Transaction
from schemas.insights import SpendingTrend

logger = logging.getLogger("insights.analysis.trend")


from agents.insights.utils import cached_analysis


@cached_analysis()
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
            
            # 计算季节性模式
            seasonal_pattern = _detect_seasonal_pattern(data)
            
            # 计算移动平均线
            moving_average = _calculate_moving_average(data)
            
            trends.append(SpendingTrend(
                category=category,
                data_points=data,
                growth_rate=growth_rate,
                seasonal_pattern=seasonal_pattern,
                moving_average=moving_average
            ))
    
    # 按增长率绝对值排序，取前5大变化趋势
    sorted_trends = sorted(trends, key=lambda x: abs(x.growth_rate), reverse=True)[:5]
    logger.info(f"生成了 {len(sorted_trends)} 个主要支出趋势")
    return sorted_trends


def _detect_seasonal_pattern(data_points: List[Tuple[str, float]]) -> str:
    """
    检测季节性模式
    
    Args:
        data_points: 数据点列表，格式为 (月份, 金额)
    
    Returns:
        str: 季节性模式描述
    """
    if len(data_points) < 3:
        return "数据不足"
    
    # 提取月份和金额
    months = [point[0] for point in data_points]
    amounts = [point[1] for point in data_points]
    
    # 计算月度变化
    monthly_changes = []
    for i in range(1, len(amounts)):
        change = (amounts[i] - amounts[i-1]) / amounts[i-1] * 100 if amounts[i-1] > 0 else 0
        monthly_changes.append(change)
    
    # 分析模式
    if len(monthly_changes) >= 3:
        avg_change = sum(monthly_changes) / len(monthly_changes)
        
        if abs(avg_change) < 5:
            return "稳定"
        elif avg_change > 10:
            return "快速增长"
        elif avg_change > 0:
            return "缓慢增长"
        elif avg_change < -10:
            return "快速下降"
        else:
            return "缓慢下降"
    
    return "无明显模式"


def _calculate_moving_average(data_points: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    """
    计算移动平均线
    
    Args:
        data_points: 数据点列表，格式为 (月份, 金额)
    
    Returns:
        List[Tuple[str, float]]: 移动平均线数据点
    """
    if len(data_points) < 3:
        return data_points
    
    moving_averages = []
    amounts = [point[1] for point in data_points]
    months = [point[0] for point in data_points]
    
    # 计算3个月移动平均
    for i in range(2, len(amounts)):
        avg = (amounts[i-2] + amounts[i-1] + amounts[i]) / 3
        moving_averages.append((months[i], avg))
    
    return moving_averages