from __future__ import annotations

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_api_key
from ..models.gym import GymDayAssignment, GymExercise, GymExerciseHistory
from ..schemas.gym import (
    GymBootstrapResponse,
    GymDayAssignmentRead,
    GymDayAssignmentUpdate,
    GymExerciseCreate,
    GymExerciseHistoryCreate,
    GymExerciseHistoryRead,
    GymExerciseRead,
    GymExerciseUpdate,
)
from ..services.gym_seed import get_default_muscle_targets

router = APIRouter(prefix="/gym", tags=["gym"], dependencies=[Depends(require_api_key)])


def _get_exercise_or_404(db: Session, exercise_id: str) -> GymExercise:
    exercise = db.get(GymExercise, exercise_id)
    if not exercise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found")
    return exercise


def _get_assignment_or_404(db: Session, assignment_id: str) -> GymDayAssignment:
    assignment = db.get(GymDayAssignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return assignment


def _get_history_or_404(db: Session, history_id: str) -> GymExerciseHistory:
    history = db.get(GymExerciseHistory, history_id)
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History entry not found")
    return history


def _exercise_to_read(exercise: GymExercise, latest: GymExerciseHistory | None) -> GymExerciseRead:
    payload = GymExerciseRead.model_validate(exercise)
    updates: dict = {}
    if latest:
        updates["last_session"] = latest.sets or []
        updates["last_performed_on"] = latest.recorded_at
    else:
        last_performed = (exercise.extra_metadata or {}).get("last_performed_on")
        if last_performed:
            try:
                updates["last_performed_on"] = datetime.fromisoformat(last_performed)
            except ValueError:
                updates["last_performed_on"] = last_performed
    if updates:
        payload = payload.model_copy(update=updates)
    return payload


@router.get("/bootstrap", response_model=GymBootstrapResponse)
def bootstrap_gym(db: Session = Depends(get_db)):
    assignments = (
        db.query(GymDayAssignment)
        .order_by(GymDayAssignment.day_key, GymDayAssignment.order_index)
        .all()
    )
    exercises = db.query(GymExercise).order_by(GymExercise.name).all()
    history_entries = (
        db.query(GymExerciseHistory)
        .order_by(GymExerciseHistory.recorded_at)
        .all()
    )

    latest_map: dict[str, GymExerciseHistory] = {}
    for entry in history_entries:
        existing = latest_map.get(entry.exercise_id)
        if not existing or entry.recorded_at >= existing.recorded_at:
            latest_map[entry.exercise_id] = entry

    exercise_payload = [_exercise_to_read(exercise, latest_map.get(exercise.id)) for exercise in exercises]
    assignment_payload = [GymDayAssignmentRead.model_validate(item) for item in assignments]
    history_payload = [GymExerciseHistoryRead.model_validate(item) for item in history_entries]

    return GymBootstrapResponse(
        exercises=exercise_payload,
        assignments=assignment_payload,
        history=history_payload,
        muscle_targets=get_default_muscle_targets(),
    )


@router.get("/exercises", response_model=list[GymExerciseRead])
def list_exercises(db: Session = Depends(get_db)):
    exercises = db.query(GymExercise).order_by(GymExercise.name).all()
    history_entries = (
        db.query(GymExerciseHistory)
        .order_by(GymExerciseHistory.recorded_at.desc())
        .all()
    )
    latest_map: dict[str, GymExerciseHistory] = {}
    for entry in history_entries:
        if entry.exercise_id not in latest_map:
            latest_map[entry.exercise_id] = entry
    return [_exercise_to_read(exercise, latest_map.get(exercise.id)) for exercise in exercises]


@router.post("/exercises", response_model=GymExerciseRead, status_code=status.HTTP_201_CREATED)
def create_exercise(payload: GymExerciseCreate, db: Session = Depends(get_db)):
    exercise_id = payload.id or str(uuid.uuid4())
    if db.get(GymExercise, exercise_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exercise already exists")

    exercise = GymExercise(
        id=exercise_id,
        **payload.model_dump(exclude={"id"}, exclude_none=True),
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return _exercise_to_read(exercise, None)


@router.patch("/exercises/{exercise_id}", response_model=GymExerciseRead)
def update_exercise(exercise_id: str, payload: GymExerciseUpdate, db: Session = Depends(get_db)):
    exercise = _get_exercise_or_404(db, exercise_id)
    update_data = payload.model_dump(exclude_none=True)

    if "extra_metadata" in update_data:
        merged = dict(exercise.extra_metadata or {})
        merged.update(update_data.pop("extra_metadata"))
        exercise.extra_metadata = merged

    for field, value in update_data.items():
        setattr(exercise, field, value)

    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    latest = (
        db.query(GymExerciseHistory)
        .filter(GymExerciseHistory.exercise_id == exercise.id)
        .order_by(GymExerciseHistory.recorded_at.desc())
        .first()
    )
    return _exercise_to_read(exercise, latest)


@router.delete("/exercises/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exercise(exercise_id: str, db: Session = Depends(get_db)):
    exercise = _get_exercise_or_404(db, exercise_id)
    db.delete(exercise)
    db.commit()


@router.get("/history/{exercise_id}", response_model=list[GymExerciseHistoryRead])
def list_history(exercise_id: str, db: Session = Depends(get_db)):
    _get_exercise_or_404(db, exercise_id)
    history = (
        db.query(GymExerciseHistory)
        .filter(GymExerciseHistory.exercise_id == exercise_id)
        .order_by(GymExerciseHistory.recorded_at.desc())
        .all()
    )
    return [GymExerciseHistoryRead.model_validate(entry) for entry in history]


@router.post("/history", response_model=GymExerciseHistoryRead, status_code=status.HTTP_201_CREATED)
def create_history_entry(payload: GymExerciseHistoryCreate, db: Session = Depends(get_db)):
    exercise = _get_exercise_or_404(db, payload.exercise_id)
    data = payload.model_dump(exclude_none=True)
    if not data.get("recorded_at"):
        data["recorded_at"] = datetime.utcnow()
    history_entry = GymExerciseHistory(**data)
    db.add(history_entry)

    meta = dict(exercise.extra_metadata or {})
    meta["last_performed_on"] = data["recorded_at"].isoformat() if isinstance(data["recorded_at"], datetime) else data["recorded_at"]
    exercise.extra_metadata = meta
    db.add(exercise)

    db.commit()
    db.refresh(history_entry)
    return GymExerciseHistoryRead.model_validate(history_entry)


@router.delete("/history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history_entry(history_id: str, db: Session = Depends(get_db)):
    entry = _get_history_or_404(db, history_id)
    exercise_id = entry.exercise_id
    db.delete(entry)
    db.commit()

    latest = (
        db.query(GymExerciseHistory)
        .filter(GymExerciseHistory.exercise_id == exercise_id)
        .order_by(GymExerciseHistory.recorded_at.desc())
        .first()
    )
    exercise = db.get(GymExercise, exercise_id)
    if exercise:
        meta = dict(exercise.extra_metadata or {})
        meta["last_performed_on"] = latest.recorded_at.isoformat() if latest else None
        exercise.extra_metadata = meta
        db.add(exercise)
        db.commit()


@router.patch("/assignments/{assignment_id}", response_model=GymDayAssignmentRead)
def update_assignment(assignment_id: str, payload: GymDayAssignmentUpdate, db: Session = Depends(get_db)):
    assignment = _get_assignment_or_404(db, assignment_id)
    exercise = _get_exercise_or_404(db, payload.selected_exercise_id)

    if assignment.options and payload.selected_exercise_id not in assignment.options:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exercise not allowed for this slot")

    assignment.selected_exercise_id = exercise.id
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return GymDayAssignmentRead.model_validate(assignment)
