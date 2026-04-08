import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, String, Text

from ..core.database import Base


class BudgetEntry(Base):
    __tablename__ = "budget_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    note = Column(Text, nullable=True)
    spent_on = Column(Date, nullable=False, default=date.today, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)