from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_api_key
from ..models.setting import AppSetting
from ..models.task import TaskHistory, TaskTemplate
from ..schemas.task import (
    PromptConfig,
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


def _classify_task(task: TaskTemplate, last_done: date | None, week_start: date, week_end: date) -> str:
    mode, start_after, end_before = _extract_recurrence(task)
    today = date.today()

    if mode == "repeat":
        base = last_done or today
    else:  # one_time
        base = today

    earliest = base + timedelta(days=start_after)
    latest = base + timedelta(days=end_before)
    # If the target week overlaps the allowed window, treat as must.
    if week_end >= earliest and week_start <= latest:
        return "must"
    return "skip"


def _build_prompt(week_start: date, week_end: date, tasks: list[ScheduledTaskCandidate], request: ScheduleRequest) -> str:
    lines: list[str] = []
    lines.append("You are scheduling tasks for the upcoming week only. Do not place anything outside this range.")
    lines.append(f"Week range: {week_start.isoformat()} to {week_end.isoformat()} (Saturday to Friday).")
    lines.append("Recurrence rules:")
    lines.append(
        "- repeat: derive every occurrence that fits in this week by chaining the window from the last completion (or today if none). Each occurrence must be >= start_after_days and <= end_before_days after the previous one. Keep chaining until you pass the week end."
    )
    lines.append("- one_time: place exactly once within its allowed window; if no overlap with the week, skip and explain.")
    lines.append(
        "If a task's allowed window does not intersect this week, skip it and state `skipped: reason`. Prefer preferred windows (e.g., mornings) and avoid busy windows when picking exact times."
    )

    if request.user_busy:
        lines.append("Busy windows to avoid:")
        for window in request.user_busy:
            lines.append(f"- {window.day or 'any'} {window.start_time or ''}-{window.end_time or ''} ({window.note or 'busy'})")
    if request.user_preferences:
        lines.append("Preferred windows:")
        for window in request.user_preferences:
            lines.append(f"- {window.day or 'any'} {window.start_time or ''}-{window.end_time or ''} ({window.note or window.kind or 'preferred'})")

    lines.append("Tasks to consider (only schedule if the allowed window intersects this week):")
    for task in tasks:
        if task.classification == "skip":
            continue
        note = "must" if task.classification == "must" else "do_if_possible"
        start_after = task.start_after_days if task.start_after_days is not None else 0
        end_before = task.end_before_days if task.end_before_days is not None else start_after
        preferred = f" | preferred window: {task.preferred_window}" if task.preferred_window else ""
        descr = f" | description: {task.description}" if task.description else ""
        lines.append(
            f"- {task.title} [{note} | mode={task.mode}] | {task.duration_minutes} min | schedule window {task.window_start.isoformat()} to {task.window_end.isoformat()} | allowed {start_after}-{end_before} days after last completion ({task.last_completed_at or 'never'}) | priority {task.priority}{preferred}{descr}"
        )

    lines.append(
        "Return a concise plan with concrete day/time for each scheduled task inside this week. Distribute repeat tasks per their chained windows, respect busy windows, keep times inside preferred dayparts when given, and avoid clustering everything on one day."
    )
    lines.append("If you skip a task, state `skipped: <reason>` so the user understands why.")
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

    # Prompt is now owned/edited by frontend and stored separately; return empty to avoid confusion.
    return SchedulePreviewResponse(week_start=week_start, week_end=week_end, prompt="", tasks=candidates)


@router.post("/schedule/commit", response_model=ScheduleCommitResponse)
def commit_schedule(request: ScheduleCommitRequest):
    # Placeholder: we do not persist a schedule yet; this captures the contract for frontends and AI.
    return ScheduleCommitResponse(
        message="Plan received; persistence not yet implemented",
        stored=False,
        plan=request.plan,
        ai_response=request.ai_response,
    )


def _get_setting(db: Session, key: str) -> str:
    record = db.get(AppSetting, key)
    return record.value if record else ""


def _set_setting(db: Session, key: str, value: str) -> str:
    record = db.get(AppSetting, key)
    if record:
        record.value = value
    else:
        record = AppSetting(key=key, value=value)
        db.add(record)
    db.commit()
    db.refresh(record)
    return record.value


@router.get("/prompt", response_model=PromptConfig)
def get_prompt(db: Session = Depends(get_db)):
    value = _get_setting(db, "tasks_prompt")
    return PromptConfig(prompt=value)


@router.put("/prompt", response_model=PromptConfig)
def set_prompt(payload: PromptConfig, db: Session = Depends(get_db)):
    value = _set_setting(db, "tasks_prompt", payload.prompt)
    return PromptConfig(prompt=value)
