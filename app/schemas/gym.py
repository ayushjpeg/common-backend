from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkoutSessionBase(BaseModel):
    title: str
    description: str | None = None
    scheduled_at: datetime
    duration_minutes: float | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str = "planned"


class WorkoutSessionCreate(WorkoutSessionBase):
    pass


class WorkoutSessionRead(WorkoutSessionBase):
    id: str

    class Config:
        from_attributes = True
