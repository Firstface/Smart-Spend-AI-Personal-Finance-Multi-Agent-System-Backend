"""
建议生成模块。

负责生成支出建议。
"""
from typing import List
import logging

from models.transaction import Transaction
from schemas.insights import SpendingRecommendation, MonthlySummary
from agents.insights.analysis.anomaly import detect_unusual_spending
from agents.insights.llm.recommender import generate_ai_recommendations


from agents.insights.utils import cached_analysis

logger = logging.getLogger("insights.recommendations")


@cached_analysis()
async def generate_spending_recommendations(
    transactions: List[Transaction],
    monthly_summary: MonthlySummary,
    use_llm: bool = True
) -> List[SpendingRecommendation]:
    """
    生成支出建议
    
    Args:
        transactions: 交易列表
        monthly_summary: 月度摘要
        use_llm: 是否使用 LLM 生成智能建议（默认为 True）
    
    Returns:
        List[SpendingRecommendation]: 建议列表
    """
    try:
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
        
        # 生成 AI 智能建议（如果启用）
        if use_llm:
            ai_recommendations = await _get_ai_recommendations(transactions, monthly_summary)
            recommendations.extend(ai_recommendations)
        else:
            logger.info("LLM 功能已禁用，仅使用规则-based 建议")
        
        logger.info(f"生成了 {len(recommendations)} 条支出建议")
        return recommendations
    except Exception as e:
        logger.error(f"生成支出建议失败: {e}")
        return []


async def _get_ai_recommendations(
    transactions: List[Transaction],
    monthly_summary: MonthlySummary
) -> List[SpendingRecommendation]:
    """
    获取 AI 生成的智能建议
    
    Args:
        transactions: 交易列表
        monthly_summary: 月度摘要
    
    Returns:
        List[SpendingRecommendation]: AI 生成的建议列表
    """
    # 构建输入数据
    top_categories_str = "\n".join([f"  - {cat.category}: {cat.amount:.2f}元 ({cat.percentage:.1f}%)" 
                                  for cat in monthly_summary.top_categories])
    
    recent_transactions_str = "\n".join([f"  - {txn.counterparty}: {txn.amount:.2f}元 ({txn.category})" 
                                         for txn in transactions[-10:]])
    
    logger.debug(f"准备调用 LLM 生成建议")
    logger.debug(f"月度摘要: 总支出={monthly_summary.total_expense:.2f}, 月均支出={monthly_summary.average_monthly_spending:.2f}")
    
    # 异步调用 LLM 生成建议
    try:
        ai_recommendations = await generate_ai_recommendations(
            total_expense=monthly_summary.total_expense,
            average_monthly_spending=monthly_summary.average_monthly_spending,
            top_categories=top_categories_str,
            recent_transactions=recent_transactions_str
        )
        logger.info(f"AI 生成了 {len(ai_recommendations)} 条智能建议")
        logger.debug(f"AI 建议详情: {[rec.title for rec in ai_recommendations]}")
        return ai_recommendations
    except ImportError as e:
        # 处理 LLM 相关模块导入失败
        logger.warning(f"LLM 模块导入失败: {e}，跳过 AI 建议生成")
        logger.debug(f"导入错误详情: {str(e)}")
        return []
    except Exception as e:
        # 处理其他 LLM 调用失败
        logger.error(f"AI 建议生成失败: {e}，跳过 AI 建议生成")
        logger.debug(f"LLM 调用错误详情: {str(e)}")
        return []