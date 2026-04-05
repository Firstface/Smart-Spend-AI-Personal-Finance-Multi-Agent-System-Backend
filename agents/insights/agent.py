"""
Follow-up & Insights Agent 主入口。

负责生成财务摘要、分析支出趋势、检测异常支出、汇总订阅等。
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from models.transaction import Transaction
from agents.insights.service import generate_monthly_summary
from agents.insights.analysis.trend import analyze_spending_trends
from agents.insights.analysis.anomaly import detect_unusual_spending
from agents.insights.analysis.subscription import aggregate_subscriptions
from agents.insights.recommendations.generator import generate_spending_recommendations
from agents.insights.schemas import MonthlySummary, SpendingTrend, UnusualSpending, SubscriptionSummary, \
    SpendingRecommendation, InsightsResult

SubscriptionSummary, SpendingRecommendation, InsightsResult

logger = logging.getLogger("insights.agent")


async def generate_insights(
    user_id: str,
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> InsightsResult:
    """
    生成综合财务洞察
    
    Args:
        user_id: 用户ID
        db: 数据库会话
        start_date: 开始日期（默认3个月前）
        end_date: 结束日期（默认今天）
    
    Returns:
        InsightsResult: 包含所有洞察的结果对象
    """
    # 默认时间范围：过去3个月
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=90)
    
    logger.info(f"Generating insights for user {user_id} from {start_date} to {end_date}")
    
    # 加载用户交易数据
    transactions = _load_transactions(db, user_id, start_date, end_date)
    logger.info(f"Loaded {len(transactions)} transactions for analysis")
    
    # 生成各种洞察
    monthly_summary = generate_monthly_summary(transactions, start_date, end_date)
    spending_trends = analyze_spending_trends(transactions, start_date, end_date)
    unusual_spending = detect_unusual_spending(transactions)
    subscriptions = aggregate_subscriptions(transactions)
    recommendations = generate_spending_recommendations(transactions, monthly_summary)
    
    # 构建结果
    result = InsightsResult(
        monthly_summary=monthly_summary,
        spending_trends=spending_trends,
        unusual_spending=unusual_spending,
        subscriptions=subscriptions,
        recommendations=recommendations
    )
    
    logger.info(f"Insights generated successfully for user {user_id}")
    return result


def _load_transactions(
    db: Session,
    user_id: str,
    start_date: datetime,
    end_date: datetime
) -> List[Transaction]:
    """
    从数据库加载用户交易数据
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        List[Transaction]: 交易列表
    """
    return db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_time >= start_date,
        Transaction.transaction_time <= end_date,
        Transaction.direction == "expense",  # 只分析支出
        Transaction.needs_review == False,  # 只分析已确认的交易
        Transaction.category.isnot(None)  # 只分析已分类的交易
    ).order_by(Transaction.transaction_time).all()