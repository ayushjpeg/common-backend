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

_MUSCLE_SYNONYMS = {
    "shoulders": ("delt", "shoulder"),
    "chest": ("pec", "chest"),
    "quads": ("quad",),
    "hamstrings": ("hamstring",),
    "glutes": ("glute",),
    "abs": ("ab", "core"),
    "lats": ("lat",),
    "traps": ("trap",),
    "biceps": ("bicep", "biceps", "bi"),
    "triceps": ("tricep", "triceps", "tri"),
    "calves": ("calf", "gastrocnemius", "soleus"),
    "forearms": ("forearm", "brach", "wrist flexor", "wrist extensor"),
    "upper back": ("upper back", "upperback", "mid back", "midback"),
    "lower back": ("lower back", "lowerback", "lumbar"),
    "full body": ("full body", "fullbody", "total body"),
}


def _normalize_muscle(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    if not text:
        return ""
    for canonical, tokens in _MUSCLE_SYNONYMS.items():
        if any(token in text for token in tokens):
            return canonical
    return text


def _collect_muscle_tokens(exercise: GymExercise | None) -> set[str]:
    tokens: set[str] = set()
    if not exercise:
        return tokens
    sources = [
        exercise.primary_muscle,
        exercise.secondary_muscle,
    ]
    sources.extend(exercise.muscle_groups or [])
    for source in sources:
        normalized = _normalize_muscle(source)
        if normalized:
            tokens.add(normalized)
    return tokens


def _collect_slot_tokens(slot_metadata: dict | None) -> set[str]:
    tokens: set[str] = set()
    if not slot_metadata:
        return tokens
    muscles = slot_metadata.get("muscles") if isinstance(slot_metadata, dict) else None
    if isinstance(muscles, dict):
        sources = muscles.keys()
    elif isinstance(muscles, (list, tuple, set)):
        sources = muscles
    else:
        sources = []
    for source in sources:
        normalized = _normalize_muscle(str(source))
        if normalized:
            tokens.add(normalized)
    return tokens


def _rank_substitute_candidates(
    reference: GymExercise,
    candidates: list[GymExercise],
    target_tokens: set[str] | None,
) -> list[GymExercise]:
    ref_primary = _normalize_muscle(reference.primary_muscle)
    ref_secondary = _normalize_muscle(reference.secondary_muscle)
    tokens_to_match = set(target_tokens or [])
    ranked: list[tuple[float, str, GymExercise]] = []
    for candidate in candidates:
        if not candidate or not candidate.is_active:
            continue
        candidate_tokens = _collect_muscle_tokens(candidate)
        if tokens_to_match and candidate.id != reference.id and not (tokens_to_match & candidate_tokens):
            continue
        primary = _normalize_muscle(candidate.primary_muscle)
        secondary = _normalize_muscle(candidate.secondary_muscle)
        score: float
        if candidate.id == reference.id:
            score = 0.0
        elif primary == ref_primary:
            score = 1.0
        elif secondary == ref_primary:
            score = 1.5
        elif ref_secondary and (primary == ref_secondary or secondary == ref_secondary):
            score = 2.0
        else:
            score = 3.0
        ranked.append((score, candidate.name.lower(), candidate))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked]


def _append_explicit_options(
    ranked: list[GymExercise],
    option_ids: list[str] | None,
    db: Session,
) -> list[GymExercise]:
    if not option_ids:
        return ranked
    existing_ids = {candidate.id for candidate in ranked}
    for option_id in option_ids:
        if not option_id or option_id in existing_ids:
            continue
        exercise = db.get(GymExercise, option_id)
        if not exercise or not exercise.is_active:
            continue
        ranked.append(exercise)
        existing_ids.add(exercise.id)
    return ranked


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

    assignment.selected_exercise_id = exercise.id
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return GymDayAssignmentRead.model_validate(assignment)


@router.post("/assignments/{assignment_id}/substitute", response_model=GymDayAssignmentRead)
def substitute_assignment(assignment_id: str, db: Session = Depends(get_db)):
    assignment = _get_assignment_or_404(db, assignment_id)
    base_exercise_id = assignment.selected_exercise_id or assignment.default_exercise_id
    if not base_exercise_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignment has no exercise to substitute")

    reference_exercise = _get_exercise_or_404(db, base_exercise_id)
    target_tokens = _collect_muscle_tokens(reference_exercise)
    slot_tokens = _collect_slot_tokens(assignment.slot_metadata)
    if slot_tokens:
        target_tokens |= slot_tokens
    active_exercises = (
        db.query(GymExercise)
        .filter(GymExercise.is_active.is_(True))
        .order_by(GymExercise.name)
        .all()
    )

    ranked = _rank_substitute_candidates(reference_exercise, active_exercises, target_tokens)
    ranked = _append_explicit_options(ranked, assignment.options, db)

    ordered_ids: list[str] = []
    seen_ids: set[str] = set()
    for exercise in ranked:
        if exercise.id not in seen_ids:
            ordered_ids.append(exercise.id)
            seen_ids.add(exercise.id)

    current_exercise_id = assignment.selected_exercise_id or reference_exercise.id
    if current_exercise_id not in seen_ids:
        ordered_ids.insert(0, current_exercise_id)
        seen_ids.add(current_exercise_id)

    if len(ordered_ids) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No substitute exercises found for this slot")

    current_index = ordered_ids.index(current_exercise_id)
    next_exercise_id = ordered_ids[(current_index + 1) % len(ordered_ids)]
    if next_exercise_id == current_exercise_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No substitute exercises found for this slot")

    assignment.selected_exercise_id = next_exercise_id
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return GymDayAssignmentRead.model_validate(assignment)
