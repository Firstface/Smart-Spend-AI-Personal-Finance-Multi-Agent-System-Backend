"""
建议生成模块。

负责生成支出建议。
"""
from typing import List

from models.transaction import Transaction
from agents.insights.schemas import SpendingRecommendation, MonthlySummary
from agents.insights.analysis.anomaly import detect_unusual_spending


def generate_spending_recommendations(
    transactions: List[Transaction],
    monthly_summary: MonthlySummary
) -> List[SpendingRecommendation]:
    """
    生成支出建议
    
    Args:
        transactions: 交易列表
        monthly_summary: 月度摘要
    
    Returns:
        List[SpendingRecommendation]: 建议列表
    """
    recommendations = []
    
    # 基于总支出的建议
    if monthly_summary.average_monthly_spending > 5000:
        recommendations.append(SpendingRecommendation(
            type="总支出控制",
            title="减少总支出",
            description=f"您的月均支出为{monthly_summary.average_monthly_spending:.2f}元，建议适当控制总支出。",
            priority="high"
        ))
    
    # 基于分类的建议
    if monthly_summary.top_categories:
        top_category = monthly_summary.top_categories[0]
        if top_category.percentage > 30:
            recommendations.append(SpendingRecommendation(
                type="类别控制",
                title=f"减少{top_category.category}支出",
                description=f"{top_category.category}占您总支出的{top_category.percentage:.1f}%，建议适当控制该类别的支出。",
                priority="medium"
            ))
    
    # 基于订阅的建议
    subscription_txns = [txn for txn in transactions if txn.category == "订阅服务"]
    if len(subscription_txns) > 5:
        recommendations.append(SpendingRecommendation(
            type="订阅管理",
            title="优化订阅服务",
            description="您订阅了多个服务，建议检查是否有不必要的订阅。",
            priority="medium"
        ))
    
    # 基于异常支出的建议
    unusual_count = len(detect_unusual_spending(transactions))
    if unusual_count > 0:
        recommendations.append(SpendingRecommendation(
            type="异常支出",
            title="关注异常支出",
            description=f"检测到{unusual_count}笔异常支出，建议关注这些交易。",
            priority="low"
        ))
    
    return recommendations