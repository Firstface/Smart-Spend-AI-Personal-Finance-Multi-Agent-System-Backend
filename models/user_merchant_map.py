"""
User-specific merchant → category mapping (learned from human corrections).

Written every time a user corrects a classification in the review queue.
Acts as a personalised Layer 0 override with higher priority than the
global MERCHANT_MAP, closing the agent's learning loop.

Course reference:
- Long-term Memory (Day2) — persisted learning from user feedback
- Human-Reflection Pattern (Day2) — user corrections feed back into the system
"""
import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from database import Base


class UserMerchantMap(Base):
    __tablename__ = "user_merchant_map"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    merchant_key = Column(String(255), nullable=False)   # lowercase, normalised
    category = Column(String(50), nullable=False)
    confidence = Column(Float, default=1.0)
    learn_count = Column(Integer, default=1)             # number of times corrected

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "merchant_key", name="uq_user_merchant"),
    )
