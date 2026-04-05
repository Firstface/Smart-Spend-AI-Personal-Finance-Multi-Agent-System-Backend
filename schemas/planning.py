from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
from decimal import Decimal
from uuid import UUID

class BudgetPlanCreate(BaseModel):
    user_id: UUID
    plan_month: str  # 格式 "2026-04"
    scenario: str    # conservative | balanced | aggressive
    total_budget: Decimal = Field(..., ge=0, decimal_places=2)
    savings_target: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2) # 保证小数能够精确计算
    category_limits: Dict[str, float]
    evidence: Optional[str] = None
    checklist: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
        # Ensure Decimal is handled as float/string in JSON output if needed
        json_encoders = {
            Decimal: lambda v: float(v)
        }