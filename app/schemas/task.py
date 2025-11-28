from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskRecurrence(BaseModel):
    mode: str = Field(default="gap")
    config: dict[str, Any] = Field(default_factory=dict)


class TaskTemplateBase(BaseModel):
    title: str
    description: str | None = None
    duration_minutes: int = 30
    priority: str = "medium"
    recurrence: TaskRecurrence = Field(default_factory=TaskRecurrence)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TaskTemplateCreate(TaskTemplateBase):
    pass


class TaskTemplateUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    duration_minutes: int | None = None
    priority: str | None = None
    recurrence: TaskRecurrence | None = None
    metadata_json: dict[str, Any] | None = None
    is_archived: bool | None = None


class TaskTemplateRead(TaskTemplateBase):
    id: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskHistoryRead(BaseModel):
    id: str
    task_id: str
    completed_at: datetime
    duration_minutes: int
    note: str | None = None
    status: str
    task_title: str | None = None

    class Config:
        from_attributes = True


class TaskHistoryCreate(BaseModel):
    completed_at: datetime
    duration_minutes: int
    note: str | None = None
    status: str = "completed"
