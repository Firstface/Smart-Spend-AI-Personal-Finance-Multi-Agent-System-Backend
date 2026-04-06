from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
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
    db: Session = Depends(get_db)
):
    """
    Retrieve existing budget plans for a specific user.
    """
    query = db.query(BudgetPlan).filter(BudgetPlan.user_id == user_id)
    if month:
        query = query.filter(BudgetPlan.plan_month == month)
    
    plans = query.all()
    return plans