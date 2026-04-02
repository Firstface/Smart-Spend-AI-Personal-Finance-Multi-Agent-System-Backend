"""
transactions 表 ORM 模型。
存储所有交易原始数据和分类结果。
"""
import uuid
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)  # 兼容 demo-user 字符串和 UUID
    source = Column(String(20), nullable=False)        # wechat | alipay | manual
    transaction_time = Column(DateTime(timezone=True), nullable=False)
    transaction_type = Column(String(50))
    counterparty = Column(String(255), nullable=False)
    counterparty_account = Column(String(255))
    goods_description = Column(Text)
    direction = Column(String(20), nullable=False)     # expense | income | neutral
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="CNY")
    payment_method = Column(String(100))
    status = Column(String(50))
    order_id = Column(String(100))
    merchant_order_id = Column(String(100))
    original_category = Column(String(50))
    remark = Column(Text)
    # 分类结果
    category = Column(String(50))
    subcategory = Column(String(50))
    confidence = Column(Float)
    evidence = Column(Text)
    decision_source = Column(String(30))
    needs_review = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
