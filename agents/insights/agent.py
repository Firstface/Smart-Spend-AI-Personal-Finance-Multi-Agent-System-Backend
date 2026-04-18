"""
Follow-up & Insights Agent 主入口。

负责生成财务摘要、分析支出趋势、检测异常支出、汇总订阅等。
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from models.transaction import Transaction
from agents.insights.service import generate_monthly_summary
from agents.insights.analysis.trend import analyze_spending_trends
from agents.insights.analysis.anomaly import detect_unusual_spending
from agents.insights.analysis.subscription import aggregate_subscriptions
from agents.insights.recommendations.generator import generate_spending_recommendations
from schemas.insights import InsightsResult
from agents.insights.reflection import reflect_on_insights
from typing import List, Dict, Optional, Any
from agents.insights.llm.recommender import _get_llm, generate_ai_recommendations

logger = logging.getLogger("insights.agent")


async def check_llm_connection() -> Dict[str, Any]:
    """
    检查 LLM 连接状态
    
    Returns:
        Dict[str, any]: 包含 LLM 连接状态的字典
    """
    logger.info("检查 LLM 连接状态...")
    
    try:
        # 尝试获取 LLM 实例
        llm = _get_llm()
        logger.info("成功获取 LLM 实例")
        
        # 尝试生成简单的建议，测试 LLM 连接
        try:
            recommendations = await generate_ai_recommendations(
                total_expense=10000.0,
                average_monthly_spending=3333.33,
                top_categories="餐饮美食: 3000元 (30%), 交通出行: 1500元 (15%), 居住: 5000元 (50%)",
                recent_transactions="餐厅: 100元, 出租车: 30元, 超市: 200元"
            )
            
            if recommendations:
                logger.info(f"LLM 连接成功，生成了 {len(recommendations)} 条建议")
                return {
                    "status": "success",
                    "message": "LLM 连接成功",
                    "recommendations_count": len(recommendations),
                    "example_recommendation": recommendations[0].title if recommendations else None
                }
            else:
                logger.warning("LLM 连接成功，但未生成建议")
                return {
                    "status": "warning",
                    "message": "LLM 连接成功，但未生成建议",
                    "recommendations_count": 0
                }
        except Exception as e:
            logger.error(f"LLM 测试调用失败: {e}")
            return {
                "status": "error",
                "message": f"LLM 连接测试失败: {str(e)}"
            }
    except Exception as e:
        logger.error(f"获取 LLM 实例失败: {e}")
        return {
            "status": "error",
            "message": f"获取 LLM 实例失败: {str(e)}"
        }


async def generate_insights(
    user_id: str,
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    use_llm: bool = True
) -> InsightsResult:
    """
    生成综合财务洞察
    
    Args:
        user_id: 用户ID
        db: 数据库会话
        start_date: 开始日期（默认3个月前）
        end_date: 结束日期（默认今天）
        use_llm: 是否使用 LLM 生成智能建议（默认为 True）
    
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
    
    # 生成支出建议（使用 await 调用异步函数）
    logger.debug(f"开始生成支出建议，use_llm={use_llm}")
    recommendations = await generate_spending_recommendations(transactions, monthly_summary, use_llm=use_llm)
    logger.debug(f"支出建议生成完成，共 {len(recommendations)} 条建议")
    
    # 构建结果
    result = InsightsResult(
        monthly_summary=monthly_summary,
        spending_trends=spending_trends,
        unusual_spending=unusual_spending,
        subscriptions=subscriptions,
        recommendations=recommendations
    )
    
    # 对洞察进行反思和改进
    result = reflect_on_insights(result, len(transactions))
    
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