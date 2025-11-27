from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_api_key
from ..models.gym import WorkoutSession
from ..schemas.gym import WorkoutSessionCreate, WorkoutSessionRead

router = APIRouter(prefix="/gym", tags=["gym"], dependencies=[Depends(require_api_key)])


@router.get("/sessions", response_model=list[WorkoutSessionRead])
def list_sessions(db: Session = Depends(get_db)):
    return db.query(WorkoutSession).order_by(WorkoutSession.scheduled_at.desc()).all()


@router.post("/sessions", response_model=WorkoutSessionRead, status_code=status.HTTP_201_CREATED)
def create_session(payload: WorkoutSessionCreate, db: Session = Depends(get_db)):
    session = WorkoutSession(**payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    session = db.get(WorkoutSession, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    db.delete(session)
    db.commit()
