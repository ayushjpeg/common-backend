from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MealEntryBase(BaseModel):
    title: str
    description: str | None = None
    calories: float | None = None
    tags: list[str] = Field(default_factory=list)
    consumed_at: datetime | None = None


class MealEntryCreate(MealEntryBase):
    pass


class MealEntryRead(MealEntryBase):
    id: str
    consumed_at: datetime

    class Config:
        from_attributes = True


class FoodImageRead(BaseModel):
    id: str
    meal_id: str
    file_path: str
    media_id: str | None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class MediaUploadResponse(BaseModel):
    media_id: str
    file_path: str
    metadata: dict[str, Any]
