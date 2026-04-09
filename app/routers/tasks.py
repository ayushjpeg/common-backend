from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user, require_api_key
from ..models.user import User
from ..models.task import TaskHistory, TaskTemplate
from ..schemas.task import (
    ScheduleCommitRequest,
    ScheduleCommitResponse,
    SchedulePreviewResponse,
    ScheduleRequest,
    ScheduledTaskCandidate,
    ScheduledTaskSlot,
    TaskHistoryCreate,
    TaskHistoryRead,
    TaskTemplateCreate,
    TaskTemplateRead,
    TaskTemplateUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_api_key)])


def _normalize_metadata_value(key: str, value):
    if key == "assigned_weekdays" and value is not None:
        return [int(item) for item in value]
    if key == "trigger_after_days" and value is not None:
        return int(value)
    return value


@router.get("/", response_model=list[TaskTemplateRead])
def list_tasks(include_archived: bool = False, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(TaskTemplate).filter(TaskTemplate.user_id == current_user.id)
    if not include_archived:
        query = query.filter(TaskTemplate.is_archived.is_(False))
    return query.order_by(TaskTemplate.created_at.desc()).all()


@router.get("/history", response_model=list[TaskHistoryRead])
def list_all_history(limit: int = 250, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records = (
        db.query(TaskHistory, TaskTemplate.title.label("task_title"))
        .join(TaskTemplate, TaskTemplate.id == TaskHistory.task_id)
        .filter(TaskHistory.user_id == current_user.id, TaskTemplate.user_id == current_user.id)
        .order_by(TaskHistory.completed_at.desc())
        .limit(limit)
        .all()
    )
    history: list[TaskHistoryRead] = []
    for record, task_title in records:
        payload = TaskHistoryRead.model_validate(record, from_attributes=True)
        payload.task_title = task_title
        history.append(payload)
    return history


def _merge_metadata(payload: TaskTemplateCreate | TaskTemplateUpdate, base: dict | None = None) -> dict:
    meta = dict(base or {})
    provided_fields = getattr(payload, "model_fields_set", set())
    for key in [
        "frequency_min_days",
        "frequency_max_days",
        "preferred_windows",
        "busy_windows",
        "importance",
        "assigned_weekdays",
        "trigger_task_id",
        "trigger_after_days",
    ]:
        if key not in provided_fields:
            continue
        value = getattr(payload, key, None)
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = _normalize_metadata_value(key, value)
    return meta


def _is_dependency_scheduled(task: TaskTemplate) -> bool:
    recurrence = task.recurrence or {}
    if (recurrence.get("mode") or "repeat") != "after_completion":
        return False
    meta = task.metadata_json or {}
    return bool(meta.get("trigger_task_id"))


@router.post("/", response_model=TaskTemplateRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskTemplateCreate = Body(..., embed=False), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = TaskTemplate(
        user_id=current_user.id,
        category=payload.category,
        title=payload.title,
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        priority=payload.priority,
        recurrence=payload.recurrence.model_dump(),
        metadata_json=_merge_metadata(payload, payload.metadata_json),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskTemplateRead)
def update_task(task_id: str, payload: TaskTemplateUpdate = Body(..., embed=False), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(TaskTemplate).filter(TaskTemplate.id == task_id, TaskTemplate.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    updates = payload.model_dump(exclude_unset=True)
    metadata_patch = _merge_metadata(payload, updates.pop("metadata_json", task.metadata_json))

    for key in ["title", "description", "duration_minutes", "priority", "recurrence", "is_archived"]:
        if key in updates:
            setattr(task, key, updates[key])

    if "category" in updates:
        task.category = updates["category"]

    task.metadata_json = metadata_patch

    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(TaskTemplate).filter(TaskTemplate.id == task_id, TaskTemplate.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    db.delete(task)
    db.commit()


@router.get("/{task_id}/history", response_model=list[TaskHistoryRead])
def list_history(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(TaskTemplate).filter(TaskTemplate.id == task_id, TaskTemplate.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    records = (
        db.query(TaskHistory)
        .filter(TaskHistory.task_id == task_id, TaskHistory.user_id == current_user.id)
        .order_by(TaskHistory.completed_at.desc())
        .all()
    )
    response: list[TaskHistoryRead] = []
    for record in records:
        payload = TaskHistoryRead.model_validate(record, from_attributes=True)
        payload.task_title = task.title
        response.append(payload)
    return response


@router.post("/{task_id}/history", response_model=TaskHistoryRead, status_code=status.HTTP_201_CREATED)
def add_history(task_id: str, record: TaskHistoryCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(TaskTemplate).filter(TaskTemplate.id == task_id, TaskTemplate.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    history = TaskHistory(task_id=task_id, user_id=current_user.id, **record.model_dump())
    db.add(history)
    db.commit()
    db.refresh(history)
    payload = TaskHistoryRead.model_validate(history, from_attributes=True)
    payload.task_title = task.title
    return payload


def _get_last_completed_at(db: Session, task_id: str, user_id: str) -> date | None:
    record = (
        db.query(TaskHistory.completed_at)
        .filter(TaskHistory.task_id == task_id, TaskHistory.user_id == user_id)
        .order_by(TaskHistory.completed_at.desc())
        .first()
    )
    return record[0].date() if record else None


def _resolve_week(request: ScheduleRequest) -> tuple[date, date]:
    today = date.today()
    week_start = request.week_start or today + timedelta(days=(5 - today.weekday()) % 7)
    week_end = request.week_end or week_start + timedelta(days=6)
    return week_start, week_end


def _extract_recurrence(task: TaskTemplate) -> tuple[str, int, int]:
    recurrence = task.recurrence or {}
    mode = recurrence.get("mode") or "repeat"
    cfg = recurrence.get("config") or {}
    start_after = max(0, int(cfg.get("start_after_days", 0) or 0))
    end_before = max(0, int(cfg.get("end_before_days", start_after) or start_after))
    if end_before < start_after:
        end_before = start_after
    return mode, start_after, end_before


def _classify_task(task: TaskTemplate, last_done: date | None, week_start: date, week_end: date) -> str:
    mode, start_after, end_before = _extract_recurrence(task)
    today = date.today()

    if mode == "repeat":
        base = last_done or today
    else:
        base = today

    earliest = base + timedelta(days=start_after)
    latest = base + timedelta(days=end_before)

    if week_end >= earliest and week_start <= latest:
        return "must"
    return "skip"


@router.post("/schedule/preview", response_model=SchedulePreviewResponse)
def preview_schedule(request: ScheduleRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    week_start, week_end = _resolve_week(request)
    tasks = (
        db.query(TaskTemplate)
        .filter(
            TaskTemplate.user_id == current_user.id,
            TaskTemplate.is_archived.is_(False),
            TaskTemplate.category == "occasional",
        )
        .all()
    )
    tasks = [task for task in tasks if not _is_dependency_scheduled(task)]

    candidates: list[ScheduledTaskCandidate] = []
    for task in tasks:
        last_done = _get_last_completed_at(db, task.id, current_user.id)
        classification = _classify_task(task, last_done, week_start, week_end)
        meta = task.metadata_json or {}
        mode, start_after, end_before = _extract_recurrence(task)
        candidate = ScheduledTaskCandidate(
            task_id=task.id,
            title=task.title,
            duration_minutes=task.duration_minutes,
            priority=task.priority,
            classification=classification,
            window_start=week_start,
            window_end=week_end,
            mode=mode,
            start_after_days=start_after,
            end_before_days=end_before,
            last_completed_at=last_done,
            description=task.description,
            preferred_window=meta.get("window") or meta.get("preferred_window"),
        )
        candidates.append(candidate)

    return SchedulePreviewResponse(week_start=week_start, week_end=week_end, tasks=candidates)


@router.post("/schedule/commit", response_model=ScheduleCommitResponse)
def commit_schedule(request: ScheduleCommitRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task_ids = [slot.task_id for slot in request.plan]
    unique_task_ids = set(task_ids)

    if unique_task_ids:
        known = (
            db.query(TaskTemplate)
            .filter(
                TaskTemplate.user_id == current_user.id,
                TaskTemplate.category == "occasional",
                TaskTemplate.id.in_(unique_task_ids),
            )
            .all()
        )
        known = [task for task in known if not _is_dependency_scheduled(task)]
        found_ids = {task.id for task in known}
        missing = unique_task_ids - found_ids
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown or non-occasional task ids: {', '.join(sorted(missing))}")

    # Build incoming week plan by task id.
    slots_by_task: dict[str, list[str]] = {task_id: [] for task_id in unique_task_ids}
    for slot in request.plan:
        dt_value = datetime.combine(slot.scheduled_date, slot.scheduled_time or time(0, 0))
        slots_by_task.setdefault(slot.task_id, []).append(dt_value.isoformat())

    for values in slots_by_task.values():
        values.sort()

    # Apply week-scoped overwrite: remove only slots in [week_start, week_end], preserve other weeks.
    tasks = (
        db.query(TaskTemplate)
        .filter(
            TaskTemplate.user_id == current_user.id,
            TaskTemplate.is_archived.is_(False),
            TaskTemplate.category == "occasional",
        )
        .all()
    )
    changed = False

    for task in tasks:
        meta = dict(task.metadata_json or {})
        slots = meta.get("scheduled_slots") or []

        keep_outside_week: list[str] = []
        for value in slots:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                # Preserve malformed values instead of dropping user data unexpectedly.
                keep_outside_week.append(value)
                continue

            if request.week_start <= parsed.date() <= request.week_end:
                continue
            keep_outside_week.append(value)

        merged = [*keep_outside_week, *(slots_by_task.get(task.id, []))]
        merged.sort()

        if merged != slots:
            meta["scheduled_slots"] = merged
            task.metadata_json = meta
            changed = True

    if changed:
        db.commit()

    return ScheduleCommitResponse(
        message="Plan cleared" if not request.plan else "Plan stored",
        stored=True,
        plan=request.plan,
    )
