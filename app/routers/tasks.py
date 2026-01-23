from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_api_key
from ..models.task import TaskHistory, TaskTemplate
from ..schemas.task import (
    ScheduleCommitRequest,
    ScheduleCommitResponse,
    SchedulePreviewResponse,
    ScheduleRequest,
    ScheduledTaskCandidate,
    TaskHistoryCreate,
    TaskHistoryRead,
    TaskTemplateCreate,
    TaskTemplateRead,
    TaskTemplateUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_api_key)])


@router.get("/", response_model=list[TaskTemplateRead])
def list_tasks(include_archived: bool = False, db: Session = Depends(get_db)):
    query = db.query(TaskTemplate)
    if not include_archived:
        query = query.filter(TaskTemplate.is_archived.is_(False))
    return query.order_by(TaskTemplate.created_at.desc()).all()


@router.get("/history", response_model=list[TaskHistoryRead])
def list_all_history(limit: int = 250, db: Session = Depends(get_db)):
    records = (
        db.query(TaskHistory, TaskTemplate.title.label("task_title"))
        .join(TaskTemplate, TaskTemplate.id == TaskHistory.task_id)
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
    for key in [
        "frequency_min_days",
        "frequency_max_days",
        "preferred_windows",
        "busy_windows",
        "importance",
        "category",
    ]:
        value = getattr(payload, key, None)
        if value is not None:
            meta[key] = value
    return meta


@router.post("/", response_model=TaskTemplateRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskTemplateCreate = Body(..., embed=False), db: Session = Depends(get_db)):
    task = TaskTemplate(
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
def update_task(task_id: str, payload: TaskTemplateUpdate = Body(..., embed=False), db: Session = Depends(get_db)):
    task = db.get(TaskTemplate, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    updates = payload.model_dump(exclude_unset=True)
    metadata_patch = _merge_metadata(payload, updates.pop("metadata_json", task.metadata_json))

    for key in ["title", "description", "duration_minutes", "priority", "recurrence", "is_archived"]:
        if key in updates:
            setattr(task, key, updates[key])

    task.metadata_json = metadata_patch

    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(TaskTemplate, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    db.delete(task)
    db.commit()


@router.get("/{task_id}/history", response_model=list[TaskHistoryRead])
def list_history(task_id: str, db: Session = Depends(get_db)):
    task = db.get(TaskTemplate, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    records = (
        db.query(TaskHistory)
        .filter(TaskHistory.task_id == task_id)
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
def add_history(task_id: str, record: TaskHistoryCreate, db: Session = Depends(get_db)):
    task = db.get(TaskTemplate, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    history = TaskHistory(task_id=task_id, **record.model_dump())
    db.add(history)
    db.commit()
    db.refresh(history)
    payload = TaskHistoryRead.model_validate(history, from_attributes=True)
    payload.task_title = task.title
    return payload


def _get_last_completed_at(db: Session, task_id: str) -> date | None:
    record = (
        db.query(TaskHistory.completed_at)
        .filter(TaskHistory.task_id == task_id)
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


def _generate_expected_dates(task: TaskTemplate, week_start: date, week_end: date, last_done: date | None) -> list[date]:
    mode, start_after, end_before = _extract_recurrence(task)
    dates: list[date] = []
    today = date.today()
    base = last_done or today

    if mode == "repeat":
        step = max(1, start_after or 1)
        current = base + timedelta(days=start_after)
        while current <= week_end:
            if current >= week_start:
                dates.append(current)
            current = current + timedelta(days=step)
    else:  # one_time
        earliest = base + timedelta(days=start_after)
        latest = base + timedelta(days=end_before)
        candidate = max(earliest, week_start)
        if candidate <= week_end and candidate <= latest:
            dates.append(candidate)

    return dates


def _classify_task(task: TaskTemplate, last_done: date | None, week_start: date, week_end: date) -> str:
    mode, start_after, end_before = _extract_recurrence(task)
    today = date.today()

    if mode == "repeat":
        base = last_done or today
    else:  # one_time
        base = today

    earliest = base + timedelta(days=start_after)
    latest = base + timedelta(days=end_before)

    if week_end < earliest or week_start > latest:
        return "skip"
    if week_start >= earliest and week_end <= latest:
        return "must"
    return "do_if_possible"


def _build_prompt(week_start: date, week_end: date, tasks: list[ScheduledTaskCandidate], request: ScheduleRequest) -> str:
    lines: list[str] = []
    lines.append("You are scheduling tasks for the week.")
    lines.append(f"Week range: {week_start.isoformat()} to {week_end.isoformat()} (Saturday to Friday).")
    if request.user_busy:
        lines.append("Busy windows to avoid:")
        for window in request.user_busy:
            lines.append(f"- {window.day or 'any'} {window.start_time or ''}-{window.end_time or ''} ({window.note or 'busy'})")
    if request.user_preferences:
        lines.append("Preferred windows:")
        for window in request.user_preferences:
            lines.append(f"- {window.day or 'any'} {window.start_time or ''}-{window.end_time or ''} ({window.note or window.kind or 'preferred'})")
    lines.append("Tasks:")
    for task in tasks:
        if task.classification == "skip":
            continue
        note = "(must)" if task.classification == "must" else "(do if possible)"
        expected = f" expected on {', '.join([d.isoformat() for d in task.expected_dates])}" if task.expected_dates else ""
        lines.append(
            f"- {task.title} {note} | {task.duration_minutes} min | window {task.window_start.isoformat()} to {task.window_end.isoformat()} {expected}"
        )
    lines.append("Return a day/time suggestion for each non-skip task within the week.")
    lines.append("When recurrence mode is repeat, schedule multiple sessions across the week following the suggested dates above instead of stacking them on one day.")
    return "\n".join(lines)


@router.post("/schedule/preview", response_model=SchedulePreviewResponse)
def preview_schedule(request: ScheduleRequest, db: Session = Depends(get_db)):
    week_start, week_end = _resolve_week(request)
    tasks = db.query(TaskTemplate).filter(TaskTemplate.is_archived.is_(False)).all()

    candidates: list[ScheduledTaskCandidate] = []
    for task in tasks:
        last_done = _get_last_completed_at(db, task.id)
        classification = _classify_task(task, last_done, week_start, week_end)
        meta = task.metadata_json or {}
        expected_dates = _generate_expected_dates(task, week_start, week_end, last_done)
        candidate = ScheduledTaskCandidate(
            task_id=task.id,
            title=task.title,
            duration_minutes=task.duration_minutes,
            priority=task.priority,
            classification=classification,
            window_start=week_start,
            window_end=week_end,
            frequency_min_days=meta.get("frequency_min_days"),
            frequency_max_days=meta.get("frequency_max_days"),
            last_completed_at=last_done,
            preferred_windows=meta.get("preferred_windows") or [],
            busy_windows=meta.get("busy_windows") or [],
            importance=meta.get("importance"),
            category=meta.get("category"),
            expected_dates=expected_dates,
        )
        candidates.append(candidate)

    prompt = _build_prompt(week_start, week_end, candidates, request)

    return SchedulePreviewResponse(week_start=week_start, week_end=week_end, prompt=prompt, tasks=candidates)


@router.post("/schedule/commit", response_model=ScheduleCommitResponse)
def commit_schedule(request: ScheduleCommitRequest):
    # Placeholder: we do not persist a schedule yet; this captures the contract for frontends and AI.
    return ScheduleCommitResponse(
        message="Plan received; persistence not yet implemented",
        stored=False,
        plan=request.plan,
        ai_response=request.ai_response,
    )
