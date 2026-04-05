"""
review_queue 表 ORM 模型。
存储低置信度交易的人工审查队列。
"""
import uuid
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from database import Base


class ReviewItem(Base):
    __tablename__ = "review_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"))
    user_id = Column(String(255), nullable=False)
    suggested_category = Column(String(50), nullable=False)
    suggested_subcategory = Column(String(50))
    confidence = Column(Float, nullable=False)
    evidence = Column(Text)
    status = Column(String(20), default="pending")   # pending | confirmed | corrected
    corrected_category = Column(String(50))
    reviewed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
