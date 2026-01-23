from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TimeWindow(BaseModel):
    day: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    kind: str | None = None
    note: str | None = None


class RecurrenceWindow(BaseModel):
    start_after_days: int = Field(default=0, ge=0)
    end_before_days: int = Field(default=0, ge=0)

    def normalized(self) -> "RecurrenceWindow":
        end = self.end_before_days
        start = self.start_after_days
        if end < start:
            end = start
        return RecurrenceWindow(start_after_days=start, end_before_days=end)


class TaskRecurrence(BaseModel):
    mode: Literal["repeat", "one_time"] = Field(default="repeat")
    config: RecurrenceWindow = Field(default_factory=RecurrenceWindow)


class TaskTemplateBase(BaseModel):
    title: str
    description: str | None = None
    duration_minutes: int = 30
    priority: str = "medium"
    recurrence: TaskRecurrence = Field(default_factory=TaskRecurrence)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    frequency_min_days: int | None = Field(default=None, ge=0)
    frequency_max_days: int | None = Field(default=None, ge=0)
    preferred_windows: list[TimeWindow] = Field(default_factory=list)
    busy_windows: list[TimeWindow] = Field(default_factory=list)
    importance: Literal["must", "do_if_possible", "flex"] | None = None
    category: str | None = None


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
    frequency_min_days: int | None = Field(default=None, ge=0)
    frequency_max_days: int | None = Field(default=None, ge=0)
    preferred_windows: list[TimeWindow] | None = None
    busy_windows: list[TimeWindow] | None = None
    importance: Literal["must", "do_if_possible", "flex"] | None = None
    category: str | None = None


class TaskTemplateRead(TaskTemplateBase):
    id: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def _extract_meta(cls, values: dict[str, Any]) -> dict[str, Any]:
        meta = values.get("metadata_json") or {}
        for key in [
            "frequency_min_days",
            "frequency_max_days",
            "preferred_windows",
            "busy_windows",
            "importance",
            "category",
        ]:
            if key in meta and values.get(key) is None:
                values[key] = meta.get(key)
        return values

    @classmethod
    def model_validate(cls, obj: Any, *args, **kwargs):  # type: ignore[override]
        if isinstance(obj, dict):
            obj = cls._extract_meta(dict(obj))
        return super().model_validate(obj, *args, **kwargs)


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


class ScheduleRequest(BaseModel):
    week_start: date | None = None
    week_end: date | None = None
    user_busy: list[TimeWindow] = Field(default_factory=list)
    user_preferences: list[TimeWindow] = Field(default_factory=list)


class ScheduledTaskCandidate(BaseModel):
    task_id: str
    title: str
    duration_minutes: int
    priority: str
    classification: Literal["must", "do_if_possible", "skip"]
    window_start: date
    window_end: date
    start_after_days: int | None = None
    end_before_days: int | None = None
    last_completed_at: datetime | None = None
    preferred_windows: list[TimeWindow] = Field(default_factory=list)
    busy_windows: list[TimeWindow] = Field(default_factory=list)
    importance: str | None = None
    category: str | None = None


class SchedulePreviewResponse(BaseModel):
    week_start: date
    week_end: date
    prompt: str
    tasks: list[ScheduledTaskCandidate]


class ScheduleCommitRequest(BaseModel):
    week_start: date
    week_end: date
    plan: list[ScheduledTaskCandidate]
    ai_response: str | None = None


class ScheduleCommitResponse(BaseModel):
    message: str
    stored: bool = False
    plan: list[ScheduledTaskCandidate] = Field(default_factory=list)
    ai_response: str | None = None
