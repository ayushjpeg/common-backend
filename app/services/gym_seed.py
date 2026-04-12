from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..data.gym_defaults import DEFAULT_EXERCISES, DEFAULT_MUSCLE_TARGETS, DEFAULT_NOTES, WEEK_TEMPLATE
from ..models.gym import GymExercise, GymExerciseHistory


def _build_assignment_metadata(day_key: str, config: dict) -> dict:
    metadata: dict = {
        "description": config.get("description"),
        "theme": config.get("theme"),
        "label": config.get("label"),
        "cardio": bool(config.get("cardio")),
    }
    if config.get("cardio_plan"):
        metadata["cardio_plan"] = config["cardio_plan"]
    if config.get("muscles"):
        metadata["muscles"] = config["muscles"]
    if config.get("focus"):
        metadata["focus"] = config.get("focus")
    metadata["day_key"] = day_key
    return metadata


def _scoped_exercise_id(user_id: str, exercise_id: str) -> str:
    digest = hashlib.sha1(f"{user_id}:{exercise_id}".encode("utf-8")).hexdigest()[:12]
    return f"u{digest}_{exercise_id}"[:64]


def _cleanup_seeded_gym_history(db: Session, user_id: str) -> None:
    history_entries = (
        db.query(GymExerciseHistory)
        .filter(GymExerciseHistory.user_id == user_id)
        .all()
    )
    seeded_entries = [entry for entry in history_entries if (entry.metrics or {}).get("seed")]

    if seeded_entries:
        for entry in seeded_entries:
            db.delete(entry)
        db.flush()

    latest_history_by_exercise: dict[str, GymExerciseHistory] = {}
    remaining_history = [entry for entry in history_entries if not (entry.metrics or {}).get("seed")]
    for entry in remaining_history:
        existing = latest_history_by_exercise.get(entry.exercise_id)
        if not existing or entry.recorded_at >= existing.recorded_at:
            latest_history_by_exercise[entry.exercise_id] = entry

    exercises = db.query(GymExercise).filter(GymExercise.user_id == user_id).all()
    changed = False
    for exercise in exercises:
        latest = latest_history_by_exercise.get(exercise.id)
        metadata = dict(exercise.extra_metadata or {})
        next_last_performed = latest.recorded_at.isoformat() if latest else None
        if metadata.get("last_performed_on") != next_last_performed:
            metadata["last_performed_on"] = next_last_performed
            exercise.extra_metadata = metadata
            db.add(exercise)
            changed = True

    if seeded_entries or changed:
        db.commit()


def ensure_user_gym_defaults(db: Session, user_id: str) -> None:
    has_exercises = db.query(GymExercise.id).filter(GymExercise.user_id == user_id).first()
    if has_exercises:
        _cleanup_seeded_gym_history(db, user_id)
        return

    scoped_ids: dict[str, str] = {}
    for exercise_id, payload in DEFAULT_EXERCISES.items():
        scoped_id = _scoped_exercise_id(user_id, exercise_id)
        scoped_ids[exercise_id] = scoped_id
        exercise = GymExercise(
            id=scoped_id,
            user_id=user_id,
            name=payload["name"],
            equipment=payload.get("equipment"),
            primary_muscle=payload.get("primary_muscle"),
            secondary_muscle=payload.get("secondary_muscle"),
            muscle_groups=payload.get("muscle_groups", []),
            rest_seconds=payload.get("rest_seconds"),
            target_notes=payload.get("target_notes"),
            cues=payload.get("cues", []),
            mistakes=payload.get("mistakes", []),
            swap_suggestions=payload.get("swap_suggestions", []),
            extra_metadata={
                "notes": DEFAULT_NOTES.get(exercise_id, ""),
                "last_performed_on": None,
                "cardio": payload.get("metadata", {}).get("cardio", False),
                "day_key": payload.get("metadata", {}).get("day_key"),
                "template_key": exercise_id,
            },
        )
        db.add(exercise)
    db.flush()

    db.commit()


def _seed_exercises(db: Session) -> None:
    return


def seed_gym_defaults() -> None:
    return


def get_default_muscle_targets() -> dict[str, dict[str, int]]:
    return DEFAULT_MUSCLE_TARGETS
