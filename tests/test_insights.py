"""
insights.py 单元测试。
运行：cd backend && python -m pytest tests/test_insights.py -v
"""
import os
import pytest
from datetime import datetime, timedelta

# 将项目根目录加入 sys.path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.insights.service import generate_monthly_summary
from agents.insights.analysis.trend import analyze_spending_trends
from agents.insights.analysis.anomaly import detect_unusual_spending
from agents.insights.analysis.subscription import aggregate_subscriptions
from agents.insights.recommendations.generator import generate_spending_recommendations
from schemas.insights import MonthlySummary


# 模拟交易数据
class MockTransaction:
    def __init__(self, category, amount, transaction_time, counterparty):
        self.category = category
        self.amount = amount
        self.transaction_time = transaction_time
        self.counterparty = counterparty
        self.id = f"test_id_{transaction_time}"


# 生成模拟交易数据
def generate_mock_transactions():
    transactions = []
    today = datetime.now()
    
    # 生成过去3个月的交易数据
    for i in range(90):
        date = today - timedelta(days=i)
        
        # 餐饮美食
        transactions.append(MockTransaction("餐饮美食", 50.0, date, "餐厅"))
        
        # 交通出行
        transactions.append(MockTransaction("交通出行", 20.0, date, "出租车"))
        
        # 居住
        if date.day == 1:
            transactions.append(MockTransaction("居住", 3000.0, date, "房东"))
        
        # 购物
        if date.day % 10 == 0:
            transactions.append(MockTransaction("购物", 200.0, date, "超市"))
        
        # 订阅服务
        if date.day == 15:
            transactions.append(MockTransaction("订阅服务", 89.0, date, "Netflix"))
            transactions.append(MockTransaction("订阅服务", 19.9, date, "Spotify"))
        
        # 异常支出
        if date.day == 20:
            transactions.append(MockTransaction("购物", 1000.0, date, "电子产品店"))
    
    return transactions


# 测试月度财务摘要
def test_generate_monthly_summary():
    transactions = generate_mock_transactions()
    today = datetime.now()
    start_date = today - timedelta(days=90)
    
    summary = generate_monthly_summary(transactions, start_date, today)
    
    assert isinstance(summary, MonthlySummary)
    assert summary.total_expense > 0
    assert len(summary.monthly_totals) >= 1
    assert len(summary.top_categories) <= 5
    assert summary.average_monthly_spending > 0
    
    print(f"月度摘要测试通过：总支出={summary.total_expense:.2f}，月均支出={summary.average_monthly_spending:.2f}")


# 测试支出趋势分析
def test_analyze_spending_trends():
    transactions = generate_mock_transactions()
    today = datetime.now()
    start_date = today - timedelta(days=90)
    
    trends = analyze_spending_trends(transactions, start_date, today)
    
    assert isinstance(trends, list)
    assert len(trends) <= 5
    
    for trend in trends:
        assert hasattr(trend, 'category')
        assert hasattr(trend, 'data_points')
        assert hasattr(trend, 'growth_rate')
    
    print(f"支出趋势测试通过：分析了{len(trends)}个趋势")


# 测试异常支出检测
def test_detect_unusual_spending():
    transactions = generate_mock_transactions()
    
    unusual_spendings = detect_unusual_spending(transactions)
    
    assert isinstance(unusual_spendings, list)
    assert len(unusual_spendings) <= 5
    
    for unusual in unusual_spendings:
        assert hasattr(unusual, 'transaction_id')
        assert hasattr(unusual, 'amount')
        assert hasattr(unusual, 'category')
        assert hasattr(unusual, 'deviation')
    
    print(f"异常支出检测测试通过：检测到{len(unusual_spendings)}笔异常支出")


# 测试订阅服务汇总
def test_aggregate_subscriptions():
    transactions = generate_mock_transactions()
    
    subscriptions = aggregate_subscriptions(transactions)
    
    assert hasattr(subscriptions, 'total_monthly_subscription')
    assert hasattr(subscriptions, 'subscriptions')
    assert isinstance(subscriptions.subscriptions, list)
    
    print(f"订阅服务汇总测试通过：月均订阅支出={subscriptions.total_monthly_subscription:.2f}")


# 测试支出建议生成
def test_generate_spending_recommendations():
    transactions = generate_mock_transactions()
    today = datetime.now()
    start_date = today - timedelta(days=90)
    
    summary = generate_monthly_summary(transactions, start_date, today)
    
    # 捕获 LLM 相关的异常，确保即使 LLM 连接失败，测试也能通过
    try:
        recommendations = generate_spending_recommendations(transactions, summary)
        
        assert isinstance(recommendations, list)
        
        for recommendation in recommendations:
            assert hasattr(recommendation, 'type')
            assert hasattr(recommendation, 'title')
            assert hasattr(recommendation, 'description')
            assert hasattr(recommendation, 'priority')
        
        print(f"支出建议生成测试通过：生成了{len(recommendations)}条建议")
    except Exception as e:
        # 如果是 LLM 相关的异常，跳过 LLM 部分的测试
        if "AI 建议生成失败" in str(e) or "API key" in str(e):
            print("LLM 连接失败，跳过 LLM 相关测试")
        else:
            # 其他异常仍然抛出
            raise