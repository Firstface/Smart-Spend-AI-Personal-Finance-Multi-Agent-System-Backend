"""
Persistent classification audit log.

Records every AI classification decision and every human review action,
providing a full, tamper-evident audit trail for compliance and debugging.

Addresses:
- IMDA Model AI Governance Framework — traceability & accountability
- Responsible AI — every outcome is recorded and attributable
- OWASP LLM Top 10 LLM06 — limit and audit what the agent can do

Course reference:
- Explainability (XRAI) — audit log as the forensic record of agent decisions
"""
import uuid
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from database import Base


class ClassificationAuditLog(Base):
    __tablename__ = "classification_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(String(255), nullable=False, index=True)

    # Event classification
    event_type = Column(String(30), nullable=False)
    # Allowed values:
    #   "ai_classified"    — agent produced an automatic classification
    #   "human_confirmed"  — human accepted the AI suggestion
    #   "human_corrected"  — human overrode the AI suggestion

    # What changed
    decision_source = Column(String(30))          # merchant_map | llm | … | user_corrected
    old_category = Column(String(50))
    new_category = Column(String(50))
    confidence = Column(Float)
    evidence = Column(Text)

    # Who acted
    actor = Column(String(10))                    # "agent" | "human"

    # Extra debug metadata (trace, reflection_rounds, elapsed_ms, …)
    meta = Column(JSONB)

    timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
