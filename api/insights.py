"""
Follow-up & Insights Agent API 路由。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from agents.insights.agent import generate_insights, check_llm_connection
from schemas.insights import InsightsRequest, InsightsResult

router = APIRouter(
    prefix="/insights",
    tags=["insights"],
)


@router.post("/generate", response_model=InsightsResult)
async def generate_insights_endpoint(
    request: InsightsRequest,
    use_llm: bool = Query(True, description="是否使用 LLM 生成智能建议"),
    db: Session = Depends(get_db)
):
    """
    生成财务洞察
    
    Args:
        request: 洞察请求
        use_llm: 是否使用 LLM 生成智能建议（默认为 True）
        db: 数据库会话
    
    Returns:
        InsightsResult: 财务洞察结果
    """
    result = await generate_insights(
        user_id=request.user_id,
        db=db,
        start_date=request.start_date,
        end_date=request.end_date,
        use_llm=use_llm
    )
    return result


@router.get("/health")
def health_check():
    """
    健康检查
    """
    return {"status": "ok", "service": "smart-spend-insights-agent"}


@router.get("/llm/health")
async def check_llm_health():
    """
    检查 LLM 连接状态
    """
    result = await check_llm_connection()
    return result