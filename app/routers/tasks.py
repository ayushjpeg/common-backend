from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user, require_api_key
from ..models.user import User
from ..models.task import TaskHistory, TaskTemplate
from ..schemas.task import (
    PlannerDay,
    PlannerResponse,
    PlannerTaskCard,
    ScheduleCommitRequest,
    ScheduleCommitResponse,
    SchedulePreviewResponse,
    ScheduleRequest,
    ScheduledTaskCandidate,
    ScheduledTaskSlot,
    TaskActionRequest,
    TaskActionResponse,
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


def _task_meta(task: TaskTemplate) -> dict:
    return dict(task.metadata_json or {})


def _task_window(task: TaskTemplate) -> str:
    return str(_task_meta(task).get("window") or "any")


def _task_notes_enabled(task: TaskTemplate) -> bool:
    return bool(_task_meta(task).get("notesEnabled", True))


def _task_autop(task: TaskTemplate) -> bool:
    return bool(_task_meta(task).get("autop", False))


def _task_assigned_weekdays(task: TaskTemplate) -> list[int]:
    value = _task_meta(task).get("assigned_weekdays") or []
    return [int(item) for item in value]


def _task_trigger(task: TaskTemplate) -> tuple[str | None, int]:
    meta = _task_meta(task)
    trigger_task_id = meta.get("trigger_task_id")
    trigger_after_days = max(0, int(meta.get("trigger_after_days", 0) or 0))
    return trigger_task_id, trigger_after_days


def _task_scheduled_slots(task: TaskTemplate) -> list[tuple[str, datetime]]:
    parsed_slots: list[tuple[str, datetime]] = []
    for raw in _task_meta(task).get("scheduled_slots") or []:
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        parsed_slots.append((str(raw), parsed))
    parsed_slots.sort(key=lambda item: item[1])
    return parsed_slots


def _completion_days_by_task(history: list[TaskHistory]) -> dict[str, set[date]]:
    completion_days: dict[str, set[date]] = {}
    for entry in history:
        completion_days.setdefault(entry.task_id, set()).add(entry.completed_at.date())
    return completion_days


def _latest_completion_by_task(tasks: list[TaskTemplate], history: list[TaskHistory]) -> dict[str, datetime]:
    latest: dict[str, datetime] = {}

    for task in tasks:
        last_completed_at = _task_meta(task).get("lastCompletedAt")
        if not last_completed_at:
            continue
        try:
            parsed = datetime.fromisoformat(str(last_completed_at).replace("Z", "+00:00"))
        except ValueError:
            continue
        latest[task.id] = parsed

    for entry in history:
        existing = latest.get(entry.task_id)
        if existing is None or entry.completed_at > existing:
            latest[entry.task_id] = entry.completed_at

    return latest


def _build_task_card(
    task: TaskTemplate,
    display_date: date,
    *,
    status: str,
    card_type: str,
    priority_label: str,
    due_date: date | None = None,
    scheduled_slot: str | None = None,
    scheduled_slots_to_clear: list[str] | None = None,
    scheduled_time: str | None = None,
    part: str | None = None,
) -> PlannerTaskCard:
    return PlannerTaskCard(
        id=f"{task.id}-{display_date.isoformat()}-{part or card_type}",
        task_id=task.id,
        category=task.category,
        title=task.title,
        description=task.description,
        duration=task.duration_minutes,
        chunk_minutes=task.duration_minutes,
        priority="high" if status == "overdue" else task.priority,
        priority_label=priority_label,
        autop=_task_autop(task),
        status=status,
        type=card_type,
        part=part,
        due_date=due_date or display_date,
        scheduled_slot=scheduled_slot,
        scheduled_slots_to_clear=scheduled_slots_to_clear or ([] if scheduled_slot is None else [scheduled_slot]),
        scheduled_time=scheduled_time,
        window=_task_window(task),
        notes_enabled=_task_notes_enabled(task),
    )


def _sort_day_tasks(tasks: list[PlannerTaskCard]) -> list[PlannerTaskCard]:
    status_order = {"overdue": 0, "scheduled": 1, "due": 2, "floating": 3}
    window_order = {"morning": 0, "afternoon": 1, "evening": 2, "any": 3}
    priority_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        tasks,
        key=lambda task: (
            status_order.get(task.status, 4),
            window_order.get(task.window, 4),
            priority_order.get(task.priority, 3),
            task.scheduled_time or "99:99",
            task.title.lower(),
        ),
    )


def _build_planner(tasks: list[TaskTemplate], history: list[TaskHistory], start_date: date, days: int) -> PlannerResponse:
    latest_done_by_task = _latest_completion_by_task(tasks, history)
    completion_days = _completion_days_by_task(history)
    today = date.today()
    planner_days: list[PlannerDay] = []

    for offset in range(days):
        current_date = start_date + timedelta(days=offset)
        day_tasks: list[PlannerTaskCard] = []

        for task in tasks:
            task_category = task.category or "occasional"
            handled_days = completion_days.get(task.id, set())

            if task_category == "daily":
                if current_date not in handled_days:
                    day_tasks.append(
                        _build_task_card(
                            task,
                            current_date,
                            status="due",
                            card_type="daily",
                            priority_label="Daily task",
                        )
                    )
                continue

            if task_category in {"long_term_task", "long_term_goal"}:
                if current_date.weekday() not in [((value - 1) % 7) for value in _task_assigned_weekdays(task)]:
                    continue
                if current_date in handled_days:
                    continue
                day_tasks.append(
                    _build_task_card(
                        task,
                        current_date,
                        status="due",
                        card_type=task_category,
                        priority_label="Long-term goal" if task_category == "long_term_goal" else "Long-term task",
                    )
                )
                continue

            trigger_task_id, trigger_after_days = _task_trigger(task)
            if _is_dependency_scheduled(task) and trigger_task_id:
                trigger_completed_at = latest_done_by_task.get(trigger_task_id)
                if trigger_completed_at is None:
                    continue
                due_date = trigger_completed_at.date() + timedelta(days=trigger_after_days)
                task_completed_at = latest_done_by_task.get(task.id)
                if task_completed_at is not None and task_completed_at.date() >= due_date:
                    continue
                display_date = max(due_date, today)
                if current_date != display_date:
                    continue
                day_tasks.append(
                    _build_task_card(
                        task,
                        current_date,
                        status="overdue" if current_date > due_date else "due",
                        card_type="after_completion",
                        priority_label="After completion",
                        due_date=due_date,
                    )
                )
                continue

            slots = [
                (raw, parsed)
                for raw, parsed in _task_scheduled_slots(task)
                if latest_done_by_task.get(task.id) is None or latest_done_by_task[task.id].date() < parsed.date()
            ]
            overdue_slots = [(raw, parsed) for raw, parsed in slots if parsed.date() < today]
            current_day_slots = [(raw, parsed) for raw, parsed in slots if parsed.date() == current_date]

            if current_date == today and overdue_slots:
                primary_raw, primary_parsed = overdue_slots[0]
                merged_slots = [raw for raw, _ in overdue_slots]
                if current_day_slots:
                    merged_slots.extend(raw for raw, _ in current_day_slots)
                day_tasks.append(
                    _build_task_card(
                        task,
                        current_date,
                        status="overdue",
                        card_type="scheduled",
                        priority_label="Scheduled slot",
                        due_date=primary_parsed.date(),
                        scheduled_slot=primary_raw,
                        scheduled_slots_to_clear=merged_slots,
                        scheduled_time=primary_parsed.strftime("%H:%M"),
                        part="carryover",
                    )
                )
                continue

            if current_date < today:
                continue

            for slot_index, (raw, parsed) in enumerate(current_day_slots):
                day_tasks.append(
                    _build_task_card(
                        task,
                        current_date,
                        status="due",
                        card_type="scheduled",
                        priority_label="Scheduled slot",
                        due_date=current_date,
                        scheduled_slot=raw,
                        scheduled_slots_to_clear=[raw],
                        scheduled_time=parsed.strftime("%H:%M"),
                        part=f"Slot {slot_index + 1}" if len(current_day_slots) > 1 else None,
                    )
                )

        sorted_tasks = _sort_day_tasks(day_tasks)
        planner_days.append(
            PlannerDay(
                date=current_date,
                label=current_date.strftime("%A, %b ") + str(current_date.day),
                short_label=current_date.strftime("%a %d"),
                tasks=sorted_tasks,
                total_minutes=sum(task.duration for task in sorted_tasks),
            )
        )

    end_date = start_date + timedelta(days=max(days - 1, 0))
    return PlannerResponse(start=start_date, end=end_date, days=planner_days)


def _clear_task_slots(meta: dict, action_date: date, scheduled_slot: str | None, scheduled_slots_to_clear: list[str]) -> dict:
    slots = [str(value) for value in meta.get("scheduled_slots") or []]
    to_clear = {str(value) for value in scheduled_slots_to_clear if value}
    if scheduled_slot:
        to_clear.add(str(scheduled_slot))

    if to_clear:
        remaining = [value for value in slots if value not in to_clear]
    else:
        remaining = []
        for value in slots:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                remaining.append(value)
                continue
            if parsed.date() != action_date:
                remaining.append(value)

    remaining.sort()
    meta["scheduled_slots"] = remaining
    meta["nextDueDate"] = remaining[0][:10] if remaining else None
    return meta


def _record_task_action(task: TaskTemplate, payload: TaskActionRequest, user_id: str) -> tuple[TaskTemplate, TaskHistory | None]:
    meta = dict(task.metadata_json or {})
    history_record: TaskHistory | None = None
    action_day = payload.action_date.date()

    if payload.action in {"complete", "skip"}:
        if (task.category or "occasional") == "occasional":
            meta = _clear_task_slots(meta, action_day, payload.scheduled_slot, payload.scheduled_slots_to_clear)

        if payload.status in {"completed", "progress"}:
            meta["lastCompletedAt"] = payload.action_date.isoformat()

        history_record = TaskHistory(
            task_id=task.id,
            user_id=user_id,
            completed_at=payload.action_date,
            duration_minutes=payload.duration_minutes or task.duration_minutes,
            note=payload.note,
            status=payload.status,
        )

    elif payload.action in {"snooze", "reschedule"}:
        if (task.category or "occasional") != "occasional":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only occasional tasks can be moved")
        target_date = payload.target_date or (action_day + timedelta(days=1))
        meta = _clear_task_slots(meta, action_day, payload.scheduled_slot, payload.scheduled_slots_to_clear)
        source_dt = None
        if payload.scheduled_slot:
            try:
                source_dt = datetime.fromisoformat(payload.scheduled_slot.replace("Z", "+00:00"))
            except ValueError:
                source_dt = None
        if source_dt is None:
            source_dt = datetime.combine(action_day, time(9, 0))
        next_slot = datetime.combine(target_date, source_dt.timetz().replace(tzinfo=None))
        scheduled_slots = [str(value) for value in meta.get("scheduled_slots") or []]
        scheduled_slots.append(next_slot.isoformat())
        scheduled_slots.sort()
        meta["scheduled_slots"] = scheduled_slots
        meta["nextDueDate"] = target_date.isoformat()

    task.metadata_json = meta
    return task, history_record


@router.get("/planner", response_model=PlannerResponse)
def get_planner(start_date: date | None = None, days: int = 7, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    safe_days = max(1, min(days, 31))
    resolved_start = start_date or date.today()
    tasks = (
        db.query(TaskTemplate)
        .filter(TaskTemplate.user_id == current_user.id, TaskTemplate.is_archived.is_(False))
        .order_by(TaskTemplate.created_at.desc())
        .all()
    )
    history = (
        db.query(TaskHistory)
        .filter(TaskHistory.user_id == current_user.id)
        .order_by(TaskHistory.completed_at.desc())
        .all()
    )
    return _build_planner(tasks, history, resolved_start, safe_days)


@router.post("/{task_id}/action", response_model=TaskActionResponse)
def apply_task_action(task_id: str, payload: TaskActionRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(TaskTemplate).filter(TaskTemplate.id == task_id, TaskTemplate.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task, history_record = _record_task_action(task, payload, current_user.id)
    if history_record is not None:
        db.add(history_record)
    db.add(task)
    db.commit()
    db.refresh(task)
    if history_record is not None:
        db.refresh(history_record)

    history_payload = None
    if history_record is not None:
        history_payload = TaskHistoryRead.model_validate(history_record, from_attributes=True)
        history_payload.task_title = task.title

    task_payload = TaskTemplateRead.model_validate(task, from_attributes=True)
    return TaskActionResponse(task=task_payload, history=history_payload)


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
