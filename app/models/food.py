import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship

from ..core.database import Base


class MealEntry(Base):
    __tablename__ = "meal_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    calories = Column(Float, nullable=True)
    tags = Column(JSON, default=list)
    consumed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    meal_slot = Column(String(64), nullable=False, default="Breakfast")
    recipe = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    ingredients = Column(JSON, default=list)
    last_made = Column(Date, nullable=True)
    image_url = Column(String(512), nullable=True)

    images = relationship("FoodImage", back_populates="meal", cascade="all, delete-orphan")


class FoodImage(Base):
    __tablename__ = "food_images"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    meal_id = Column(String(36), ForeignKey("meal_entries.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(512), nullable=False)
    media_id = Column(String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    recorded_at = Column(Date, nullable=True)
    caption = Column(Text, nullable=True)

    meal = relationship("MealEntry", back_populates="images")
