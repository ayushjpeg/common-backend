from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..data.gym_defaults import DEFAULT_EXERCISES, DEFAULT_HISTORY, DEFAULT_MUSCLE_TARGETS, DEFAULT_NOTES, WEEK_TEMPLATE
from ..models.gym import GymDayAssignment, GymExercise, GymExerciseHistory


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


def ensure_user_gym_defaults(db: Session, user_id: str) -> None:
    has_exercises = db.query(GymExercise.id).filter(GymExercise.user_id == user_id).first()
    if has_exercises:
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
                "last_performed_on": payload.get("last_performed_on"),
                "cardio": payload.get("metadata", {}).get("cardio", False),
                "day_key": payload.get("metadata", {}).get("day_key"),
                "template_key": exercise_id,
            },
        )
        db.add(exercise)
    db.flush()

    for day_key, config in WEEK_TEMPLATE.items():
        metadata = _build_assignment_metadata(day_key, config)
        exercise_rows = config.get("exercise_order", [])
        if config.get("cardio") and not exercise_rows:
            exercise_rows = [
                {
                    "slot_id": f"{day_key}-cardio",
                    "name": config.get("theme", "Cardio"),
                    "subtitle": config.get("cardio_plan", {}).get("suggestions"),
                    "default_exercise": f"cardio_{day_key}",
                    "options": [f"cardio_{day_key}"],
                }
            ]

        for order_index, slot in enumerate(exercise_rows):
            default_key = slot.get("default_exercise")
            default_id = scoped_ids.get(default_key, default_key)
            option_ids = [scoped_ids.get(option_id, option_id) for option_id in slot.get("options", [])]
            assignment = GymDayAssignment(
                user_id=user_id,
                day_key=day_key,
                slot_id=slot["slot_id"],
                slot_name=slot["name"],
                slot_subtitle=slot.get("subtitle"),
                order_index=order_index,
                default_exercise_id=default_id,
                selected_exercise_id=default_id,
                options=option_ids,
                slot_metadata=metadata,
            )
            db.add(assignment)
    db.flush()

    for exercise_id, entries in DEFAULT_HISTORY.items():
        scoped_id = scoped_ids.get(exercise_id)
        if not scoped_id:
            continue
        for entry in entries:
            sets = entry.get("sets") or []
            if not sets:
                continue
            history = GymExerciseHistory(
                user_id=user_id,
                exercise_id=scoped_id,
                recorded_at=datetime.fromisoformat(entry.get("date")),
                day_key=entry.get("day_key"),
                slot_id=entry.get("slot_id"),
                sets=sets,
                notes=entry.get("notes"),
                metrics={"seed": True},
            )
            db.add(history)
    db.commit()


def _seed_exercises(db: Session) -> None:
    return


def seed_gym_defaults() -> None:
    return


def get_default_muscle_targets() -> dict[str, dict[str, int]]:
    return DEFAULT_MUSCLE_TARGETS
