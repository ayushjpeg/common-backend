import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from ..core.database import Base


class MealEntry(Base):
    __tablename__ = "meal_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    calories = Column(Float, nullable=True)
    tags = Column(JSON, default=list)
    consumed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    images = relationship("FoodImage", back_populates="meal", cascade="all, delete-orphan")


class FoodImage(Base):
    __tablename__ = "food_images"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meal_id = Column(String(36), ForeignKey("meal_entries.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(512), nullable=False)
    media_id = Column(String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    meal = relationship("MealEntry", back_populates="images")
