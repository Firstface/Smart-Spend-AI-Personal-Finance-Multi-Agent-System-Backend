"""
Follow-up & Insights Agent 数据模型。

定义所有洞察相关的数据结构。
"""
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime


class CategorySummary(BaseModel):
    """分类摘要"""
    category: str
    amount: float
    percentage: float


class MonthlySummary(BaseModel):
    """月度财务摘要"""
    total_expense: float
    monthly_totals: Dict[str, float]  # 月份 -> 总支出
    top_categories: List[CategorySummary]
    average_monthly_spending: float


class SpendingTrend(BaseModel):
    """支出趋势"""
    category: str
    data_points: List[tuple]  # (月份, 金额)
    growth_rate: float  # 增长率（%）


class UnusualSpending(BaseModel):
    """异常支出"""
    transaction_id: str
    date: datetime
    amount: float
    category: str
    counterparty: str
    deviation: float  # 偏离程度（标准差）


class SubscriptionSummary(BaseModel):
    """订阅摘要"""
    total_monthly_subscription: float
    subscriptions: List[Dict]  # 包含merchant, monthly_amount, last_charge_date


class SpendingRecommendation(BaseModel):
    """支出建议"""
    type: str
    title: str
    description: str
    priority: str  # high, medium, low


class InsightsResult(BaseModel):
    """洞察结果"""
    monthly_summary: MonthlySummary
    spending_trends: List[SpendingTrend]
    unusual_spending: List[UnusualSpending]
    subscriptions: SubscriptionSummary
    recommendations: List[SpendingRecommendation]


class InsightsRequest(BaseModel):
    """洞察请求"""
    user_id: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None