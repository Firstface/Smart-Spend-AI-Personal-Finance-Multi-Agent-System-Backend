"""
Pydantic data models — contracts for all data flow.
This is the interface definition between the Categorization Agent and other agents.
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ====== Unified Category System ======
# Design rationale: Merges Alipay's 15 built-in categories into 10 top-level categories.
# Course reference: IMDA Operations — standardized taxonomy ensures fairness,
# not based on demographic attributes.
class CategoryEnum(str, Enum):
    FOOD = "餐饮美食"
    TRANSPORT = "交通出行"
    HOUSING = "居住"
    SHOPPING = "购物"
    ENTERTAINMENT = "娱乐休闲"
    HEALTH = "医疗健康"
    EDUCATION = "教育"
    SUBSCRIPTION = "订阅服务"
    DAILY_NECESSITIES = "日用百货"
    OTHER = "其他"


class DirectionEnum(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"
    NEUTRAL = "neutral"


class DecisionSourceEnum(str, Enum):
    MERCHANT_MAP = "merchant_map"
    KEYWORD_RULE = "keyword_rule"
    SUBSCRIPTION = "subscription"
    SIMILARITY = "similarity"
    LLM = "llm"
    LLM_REFLECTED = "llm_reflected"
    USER_CORRECTED = "user_corrected"


class ReviewStatusEnum(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"


# ====== Input Models ======
class TransactionRaw(BaseModel):
    """Raw transaction record parsed from CSV/Excel."""
    source: str                                   # wechat | alipay | manual
    transaction_time: datetime
    transaction_type: Optional[str] = None        # WeChat: merchant purchase / transfer / etc.
    counterparty: str                             # transaction counterparty
    counterparty_account: Optional[str] = None    # counterparty account (Alipay only)
    goods_description: Optional[str] = None       # goods description
    direction: DirectionEnum
    amount: float
    currency: str = "CNY"
    payment_method: Optional[str] = None
    status: Optional[str] = None
    order_id: Optional[str] = None
    merchant_order_id: Optional[str] = None
    original_category: Optional[str] = None       # Alipay built-in category
    remark: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v < 0:
            raise ValueError("Amount cannot be negative")
        return round(v, 2)


# ====== Output Models ======
class CategorizedTransaction(BaseModel):
    """Categorized transaction record — written to database."""
    id: Optional[str] = None
    source: str
    transaction_time: datetime
    counterparty: str
    goods_description: Optional[str] = None
    direction: DirectionEnum
    amount: float
    currency: str
    payment_method: Optional[str] = None
    original_category: Optional[str] = None
    # Classification result
    category: CategoryEnum
    subcategory: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str                                 # Explainability: why this category was chosen
    decision_source: DecisionSourceEnum
    needs_review: bool = False

    model_config = {"from_attributes": True}


class ClassificationResult(BaseModel):
    """Complete result returned by the Categorization Agent."""
    categorized: List[CategorizedTransaction]
    review_queue: List[CategorizedTransaction]
    stats: dict
    # stats example:
    # {
    #   "total": 342, "expense": 315, "income": 27,
    #   "auto_classified": 310, "needs_review": 22, "llm_fallback": 10,
    #   "by_source": {"merchant_map": 180, "keyword_rule": 95, ...}
    # }


class ReviewRequest(BaseModel):
    """User review request."""
    action: str = Field(pattern="^(confirm|correct)$")
    corrected_category: Optional[CategoryEnum] = None

    @model_validator(mode="after")
    def correct_needs_category(self):
        if self.action == "correct" and self.corrected_category is None:
            raise ValueError("Correction action requires a new category")
        return self


# ====== Auth Models ======
class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=100)
    email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    email: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    token: str
    user: UserOut
