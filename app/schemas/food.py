from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Ingredient(BaseModel):
    id: str
    name: str
    amount: str


class MealEntryBase(BaseModel):
    name: str
    meal: str
    recipe: str | None = None
    notes: str | None = None
    last_made: date | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    image_url: str | None = None
    image_data_url: str | None = None

    @field_validator("ingredients")
    @classmethod
    def _normalize_ingredients(cls, value: list[Ingredient]) -> list[Ingredient]:
        return value or []


class MealEntryCreate(MealEntryBase):
    pass


class MealEntryUpdate(BaseModel):
    name: str | None = None
    meal: str | None = None
    recipe: str | None = None
    notes: str | None = None
    last_made: date | None = None
    ingredients: list[Ingredient] | None = None
    image_url: str | None = None
    image_data_url: str | None = None


class FoodImageRead(BaseModel):
    id: str
    meal_id: str
    url: str
    file_path: str
    media_id: str | None
    uploaded_at: datetime
    recorded_at: date | None = None
    caption: str | None = None

    class Config:
        from_attributes = True


class MealEntryRead(BaseModel):
    id: str
    name: str
    meal: str
    recipe: str | None
    notes: str | None
    last_made: date | None
    ingredients: list[Ingredient]
    image_url: str | None
    photos: list[FoodImageRead] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class PhotoCreate(BaseModel):
    image_url: str | None = None
    image_data_url: str | None = None
    recorded_at: date | None = None
    caption: str | None = None


class MediaUploadResponse(BaseModel):
    media_id: str
    file_path: str
    metadata: dict[str, Any]
