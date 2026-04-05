"""
Pydantic 数据模型 — 所有数据流转的契约。
这是分类Agent与其他Agent对接的接口定义。
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ====== 统一分类体系 ======
# 设计依据：融合支付宝自带的15种分类，合并归纳为10个顶层类别
# 课程对应：IMDA运营管理 — 标准化的分类体系确保公平性，不基于人口统计属性
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


# ====== 输入模型 ======
class TransactionRaw(BaseModel):
    """从 CSV/Excel 解析出的原始交易记录"""
    source: str                                   # wechat | alipay | manual
    transaction_time: datetime
    transaction_type: Optional[str] = None        # 微信：商户消费/转账等
    counterparty: str                             # 交易对方
    counterparty_account: Optional[str] = None    # 对方账号（支付宝有）
    goods_description: Optional[str] = None       # 商品说明
    direction: DirectionEnum
    amount: float
    currency: str = "CNY"
    payment_method: Optional[str] = None
    status: Optional[str] = None
    order_id: Optional[str] = None
    merchant_order_id: Optional[str] = None
    original_category: Optional[str] = None       # 支付宝自带分类
    remark: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v < 0:
            raise ValueError("金额不能为负数")
        return round(v, 2)


# ====== 输出模型 ======
class CategorizedTransaction(BaseModel):
    """分类完成的交易记录 — 写入数据库"""
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
    # 分类结果
    category: CategoryEnum
    subcategory: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str                                 # 可解释性：为什么这样分类
    decision_source: DecisionSourceEnum
    needs_review: bool = False

    model_config = {"from_attributes": True}


class ClassificationResult(BaseModel):
    """分类Agent对外返回的完整结果"""
    categorized: List[CategorizedTransaction]
    review_queue: List[CategorizedTransaction]
    stats: dict
    # stats 示例:
    # {
    #   "total": 342, "expense": 315, "income": 27,
    #   "auto_classified": 310, "needs_review": 22, "llm_fallback": 10,
    #   "by_source": {"merchant_map": 180, "keyword_rule": 95, ...}
    # }


class ReviewRequest(BaseModel):
    """用户审查请求"""
    action: str = Field(pattern="^(confirm|correct)$")
    corrected_category: Optional[CategoryEnum] = None

    @model_validator(mode="after")
    def correct_needs_category(self):
        if self.action == "correct" and self.corrected_category is None:
            raise ValueError("纠正操作必须提供新分类")
        return self


# ====== Auth 模型 ======
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
