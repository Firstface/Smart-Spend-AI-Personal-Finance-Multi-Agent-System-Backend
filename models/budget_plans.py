import uuid
from sqlalchemy import Column, String, Numeric, DateTime, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from database import Base

class BudgetPlan(Base):
    """
    Planning Agent 负责的预算计划表。
    存储不同情景下的月度预算、储蓄目标及分类限额。
    """
    __tablename__ = "budget_plans"

    # 主键与关联
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)  # 与 transactions 表保持一致
    
    # 计划核心维度
    plan_month = Column(String(7), nullable=False)  # 格式如 "2024-03"
    scenario = Column(String(20), nullable=False)   # conservative | balanced | aggressive 
    
    # 金额字段 (使用 Numeric 保证财务计算精度)
    total_budget = Column(Numeric(12, 2), nullable=False)   # 总预算限额
    savings_target = Column(Numeric(12, 2), default=0.00)  # 储蓄目标 
    
    # 结构化数据
    # 存储各分类的具体限额，例如 {"餐饮": 2000, "交通": 500}
    category_limits = Column(JSONB, nullable=False) 
    # 存储核对清单或待办事项
    checklist = Column(JSONB) 
    
    # 解释性与版本控制
    evidence = Column(Text)  # 存储数字证据，解释预算设定的依据
    version = Column(Integer, default=1) # 计划版本号
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())