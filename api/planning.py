from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from database import get_db
from schemas.planning import BudgetPlanCreate
from models.budget_plans import BudgetPlan
from agents.planning.service import PlanningService

# Use English for routing and naming conventions
router = APIRouter(prefix="/api/planning", tags=["Planning Agent"])

# Initialize the service
planning_service = PlanningService()

@router.post("/generate", response_model=List[BudgetPlanCreate], status_code=status.HTTP_201_CREATED)
async def generate_monthly_plans(
    user_id: str, 
    month: str, 
    db: Session = Depends(get_db)
):
    """
    Trigger the Planning Agent to generate 3 budget scenarios 
    based on the user's spending history and financial goals.
    """
    # 1. Trigger the Agent Logic
    # This will call LLM, validate via Pydantic, and save to Neon DB
    plans = planning_service.generate_budget_plans(db, user_id, month)
    
    if not plans:
        raise HTTPException(
            status_code=500, 
            detail="Failed to generate budget plans. Please check Agent logs."
        )
    
    return [BudgetPlanCreate.model_validate(plan) for plan in plans]


@router.get("/my-plans/{user_id}", response_model=List[BudgetPlanCreate])
async def get_user_plans(
    user_id: str, 
    month: str = None, 
    latest_only: bool = True, # 默认为 True
    db: Session = Depends(get_db)
):
    plans = planning_service.get_plans(db, user_id, month, latest_only)

    return plans

@router.post("/refine", response_model=List[BudgetPlanCreate])
async def refine_plans(
    user_id: str, 
    month: str, 
    feedback: str, 
    db: Session = Depends(get_db)
):
    plans = planning_service.refine_budget_plans(db, user_id, month, feedback)
    
    if not plans:
        raise HTTPException(
            status_code=500, 
            detail="Failed to refine budget plans. Please check Agent logs."
        )
    
    return [BudgetPlanCreate.model_validate(p) for p in plans]