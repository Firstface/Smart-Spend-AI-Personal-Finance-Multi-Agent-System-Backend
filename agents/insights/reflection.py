"""
Follow-up & Insights Agent 自反思模块。

负责评估和改进财务洞察的质量，通过自反思机制提高分析准确性。
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime

from schemas.insights import InsightsResult, SpendingRecommendation
from agents.insights.config import REFLECTION_MAX_ROUNDS, REFLECTION_TEMPERATURE

logger = logging.getLogger("insights.reflection")


def reflect_on_insights(
    insights: InsightsResult,
    transactions_count: int
) -> InsightsResult:
    """
    对生成的洞察进行自反思，评估质量并进行改进。
    
    Args:
        insights: 生成的洞察结果
        transactions_count: 分析的交易数量
    
    Returns:
        InsightsResult: 经过反思改进的洞察结果
    """
    logger.info(f"开始反思洞察结果，分析了 {transactions_count} 笔交易")
    
    # 评估洞察质量
    quality_score = _evaluate_insights_quality(insights, transactions_count)
    logger.info(f"洞察质量评分: {quality_score:.2f}/10")
    
    # 改进建议
    improved_recommendations = _improve_recommendations(insights.recommendations)
    insights.recommendations = improved_recommendations
    
    # 评估异常检测质量
    if len(insights.unusual_spending) > 0:
        logger.info(f"检测到 {len(insights.unusual_spending)} 笔异常支出")
    
    # 评估订阅分析质量
    if insights.subscriptions.total_monthly_subscription > 0:
        logger.info(f"月均订阅支出: {insights.subscriptions.total_monthly_subscription:.2f}元")
    
    logger.info("洞察反思完成")
    return insights


def _evaluate_insights_quality(
    insights: InsightsResult,
    transactions_count: int
) -> float:
    """
    评估洞察质量的函数。
    
    Args:
        insights: 生成的洞察结果
        transactions_count: 分析的交易数量
    
    Returns:
        float: 质量评分（0-10）
    """
    score = 0.0
    
    # 1. 评估月度摘要质量
    if insights.monthly_summary.total_expense > 0:
        score += 2.0
    if len(insights.monthly_summary.monthly_totals) > 0:
        score += 1.0
    if len(insights.monthly_summary.top_categories) > 0:
        score += 1.0
    
    # 2. 评估趋势分析质量
    if len(insights.spending_trends) > 0:
        score += 2.0
    
    # 3. 评估异常检测质量
    if len(insights.unusual_spending) > 0:
        score += 1.0
    
    # 4. 评估订阅分析质量
    if insights.subscriptions.total_monthly_subscription > 0:
        score += 1.0
    
    # 5. 评估建议质量
    if len(insights.recommendations) > 0:
        score += 2.0
    
    # 6. 基于交易数量调整评分
    if transactions_count < 10:
        score *= 0.7  # 交易数量较少，降低评分
    elif transactions_count < 50:
        score *= 0.9  # 交易数量适中，略微降低评分
    
    return min(score, 10.0)


def _improve_recommendations(
    recommendations: List[SpendingRecommendation]
) -> List[SpendingRecommendation]:
    """
    改进建议质量的函数。
    
    Args:
        recommendations: 原始建议列表
    
    Returns:
        List[SpendingRecommendation]: 改进后的建议列表
    """
    improved_recommendations = []
    
    # 去重
    seen_titles = set()
    for rec in recommendations:
        if rec.title not in seen_titles:
            seen_titles.add(rec.title)
            improved_recommendations.append(rec)
    
    # 按优先级排序
    priority_order = {"high": 0, "medium": 1, "low": 2}
    improved_recommendations.sort(key=lambda x: priority_order.get(x.priority, 2))
    
    # 限制建议数量
    max_recommendations = 5
    if len(improved_recommendations) > max_recommendations:
        improved_recommendations = improved_recommendations[:max_recommendations]
    
    return improved_recommendations


def generate_insights_metadata(
    insights: InsightsResult,
    processing_time: float
) -> Dict:
    """
    生成洞察元数据，用于跟踪和分析洞察质量。
    
    Args:
        insights: 生成的洞察结果
        processing_time: 处理时间（秒）
    
    Returns:
        Dict: 洞察元数据
    """
    metadata = {
        "generated_at": datetime.now().isoformat(),
        "processing_time": processing_time,
        "insights_count": {
            "trends": len(insights.spending_trends),
            "unusual_spendings": len(insights.unusual_spending),
            "subscriptions": len(insights.subscriptions.subscriptions),
            "recommendations": len(insights.recommendations)
        },
        "total_expense": insights.monthly_summary.total_expense,
        "average_monthly_spending": insights.monthly_summary.average_monthly_spending
    }
    
    return metadata