from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_api_key
from ..models.task import TaskHistory, TaskTemplate
from ..schemas.task import (
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


@router.post("/", response_model=TaskTemplateRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskTemplateCreate, db: Session = Depends(get_db)):
    task = TaskTemplate(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskTemplateRead)
def update_task(task_id: str, payload: TaskTemplateUpdate, db: Session = Depends(get_db)):
    task = db.get(TaskTemplate, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
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
