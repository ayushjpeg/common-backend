from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExerciseSwapSuggestion(BaseModel):
    name: str
    detail: str | None = None


class GymSetEntry(BaseModel):
    set: int
    weight: float | str | None = None
    reps: int


class GymExerciseBase(BaseModel):
    name: str
    equipment: str | None = None
    primary_muscle: str | None = None
    secondary_muscle: str | None = None
    muscle_groups: list[str] = Field(default_factory=list)
    rest_seconds: int | None = None
    target_notes: str | None = None
    cues: list[str] = Field(default_factory=list)
    mistakes: list[str] = Field(default_factory=list)
    swap_suggestions: list[ExerciseSwapSuggestion] = Field(default_factory=list)
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class GymExerciseCreate(GymExerciseBase):
    id: str | None = None


class GymExerciseUpdate(BaseModel):
    name: str | None = None
    equipment: str | None = None
    primary_muscle: str | None = None
    secondary_muscle: str | None = None
    muscle_groups: list[str] | None = None
    rest_seconds: int | None = None
    target_notes: str | None = None
    cues: list[str] | None = None
    mistakes: list[str] | None = None
    swap_suggestions: list[ExerciseSwapSuggestion] | None = None
    extra_metadata: dict[str, Any] | None = None
    is_active: bool | None = None


class GymExerciseRead(GymExerciseBase):
    id: str
    last_session: list[GymSetEntry] = Field(default_factory=list)
    last_performed_on: datetime | None = None

    class Config:
        from_attributes = True


class GymExerciseHistoryBase(BaseModel):
    exercise_id: str
    recorded_at: datetime | None = None
    day_key: str | None = None
    slot_id: str | None = None
    sets: list[GymSetEntry] = Field(default_factory=list)
    notes: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class GymExerciseHistoryCreate(GymExerciseHistoryBase):
    pass


class GymExerciseHistoryRead(GymExerciseHistoryBase):
    id: str

    class Config:
        from_attributes = True


class GymDayAssignmentBase(BaseModel):
    day_key: str
    slot_id: str
    slot_name: str
    slot_subtitle: str | None = None
    order_index: int
    default_exercise_id: str | None = None
    selected_exercise_id: str | None = None
    options: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, alias="slot_metadata")

    class Config:
        populate_by_name = True


class GymDayAssignmentRead(GymDayAssignmentBase):
    id: str

    class Config:
        from_attributes = True
        populate_by_name = True


class GymDayAssignmentUpdate(BaseModel):
    selected_exercise_id: str


class GymBootstrapResponse(BaseModel):
    exercises: list[GymExerciseRead]
    assignments: list[GymDayAssignmentRead]
    history: list[GymExerciseHistoryRead]
    muscle_targets: dict[str, dict[str, int]]
