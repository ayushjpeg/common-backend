import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from ..core.database import Base


class GymExercise(Base):
    __tablename__ = "gym_exercises"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    equipment = Column(String(255), nullable=True)
    primary_muscle = Column(String(64), nullable=True)
    secondary_muscle = Column(String(64), nullable=True)
    muscle_groups = Column(JSON, nullable=False, default=list)
    rest_seconds = Column(Integer, nullable=True)
    target_notes = Column(Text, nullable=True)
    cues = Column(JSON, nullable=False, default=list)
    mistakes = Column(JSON, nullable=False, default=list)
    swap_suggestions = Column(JSON, nullable=False, default=list)
    extra_metadata = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    history = relationship("GymExerciseHistory", back_populates="exercise", cascade="all, delete-orphan")
    default_assignments = relationship(
        "GymDayAssignment",
        back_populates="default_exercise",
        cascade="all, delete",
        foreign_keys="GymDayAssignment.default_exercise_id",
    )
    selected_assignments = relationship(
        "GymDayAssignment",
        back_populates="selected_exercise",
        cascade="all, delete",
        foreign_keys="GymDayAssignment.selected_exercise_id",
    )


class GymDayAssignment(Base):
    __tablename__ = "gym_day_assignments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    day_key = Column(String(16), nullable=False, index=True)
    slot_id = Column(String(64), nullable=False)
    slot_name = Column(String(255), nullable=False)
    slot_subtitle = Column(String(255), nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    default_exercise_id = Column(String(64), ForeignKey("gym_exercises.id", ondelete="SET NULL"), nullable=True)
    selected_exercise_id = Column(String(64), ForeignKey("gym_exercises.id", ondelete="SET NULL"), nullable=True)
    options = Column(JSON, nullable=False, default=list)
    metadata = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    default_exercise = relationship("GymExercise", foreign_keys=[default_exercise_id], back_populates="default_assignments")
    selected_exercise = relationship("GymExercise", foreign_keys=[selected_exercise_id], back_populates="selected_assignments")


class GymExerciseHistory(Base):
    __tablename__ = "gym_exercise_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    exercise_id = Column(String(64), ForeignKey("gym_exercises.id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    day_key = Column(String(16), nullable=True)
    slot_id = Column(String(64), nullable=True)
    sets = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    metrics = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    exercise = relationship("GymExercise", back_populates="history")
