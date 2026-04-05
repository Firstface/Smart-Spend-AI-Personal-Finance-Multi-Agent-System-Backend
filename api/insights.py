"""
Follow-up & Insights Agent API 路由。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from agents.insights.agent import generate_insights
from agents.insights.schemas import InsightsRequest, InsightsResult

router = APIRouter(
    prefix="/insights",
    tags=["insights"],
)


@router.post("/generate", response_model=InsightsResult)
async def generate_user_insights(
    req: InsightsRequest,
    db: Session = Depends(get_db)
):
    """
    生成用户财务洞察
    
    Args:
        req: 洞察请求
        db: 数据库会话
    
    Returns:
        InsightsResult: 洞察结果
    """
    result = await generate_insights(
        user_id=req.user_id,
        db=db,
        start_date=req.start_date,
        end_date=req.end_date
    )
    return result


@router.get("/health")
def health_check():
    """
    健康检查
    """
    return {"status": "ok", "service": "smart-spend-insights-agent"}