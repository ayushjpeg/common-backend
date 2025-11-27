import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, JSON, String, Text

from ..core.database import Base


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scheduled_at = Column(DateTime, nullable=False)
    duration_minutes = Column(Float, nullable=True)
    metrics = Column(JSON, default=dict)
    status = Column(String(32), nullable=False, default="planned")
