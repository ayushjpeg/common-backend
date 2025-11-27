import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from ..core.database import Base


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=30)
    priority = Column(String(32), nullable=False, default="medium")
    recurrence = Column(JSON, nullable=False, default=dict)
    metadata_json = Column(JSON, nullable=False, default=dict)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    history = relationship("TaskHistory", back_populates="task", cascade="all, delete-orphan")


class TaskHistory(Base):
    __tablename__ = "task_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("task_templates.id", ondelete="CASCADE"), nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    note = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="completed")

    task = relationship("TaskTemplate", back_populates="history")
