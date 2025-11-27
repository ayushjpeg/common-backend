from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_api_key
from ..models.cctv import CCTVRecording, CCTVStream
from ..models.media_asset import MediaAsset
from ..schemas.cctv import CCTVRecordingRead, CCTVStreamCreate, CCTVStreamRead
from ..services.media_storage import get_media_storage

router = APIRouter(prefix="/cctv", tags=["cctv"], dependencies=[Depends(require_api_key)])


@router.get("/streams", response_model=list[CCTVStreamRead])
def list_streams(db: Session = Depends(get_db)):
    return db.query(CCTVStream).order_by(CCTVStream.created_at.desc()).all()


@router.post("/streams", response_model=CCTVStreamRead, status_code=status.HTTP_201_CREATED)
def create_stream(payload: CCTVStreamCreate, db: Session = Depends(get_db)):
    stream = CCTVStream(**payload.model_dump())
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream


@router.post("/streams/{stream_id}/recordings", response_model=CCTVRecordingRead, status_code=status.HTTP_201_CREATED)
async def upload_recording(stream_id: str, file: UploadFile = File(...), duration_seconds: int | None = None, db: Session = Depends(get_db)):
    stream = db.get(CCTVStream, stream_id)
    if not stream:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream not found")

    storage = get_media_storage()
    dest_path = storage.save_upload("cctv", file)

    media = MediaAsset(
        owner_type="cctv_stream",
        owner_id=stream_id,
        file_path=str(dest_path),
        mime_type=file.content_type,
        metadata={"filename": file.filename},
    )
    db.add(media)
    db.flush()

    recording = CCTVRecording(stream_id=stream_id, file_path=str(dest_path), duration_seconds=duration_seconds)
    db.add(recording)
    db.commit()
    db.refresh(recording)
    return recording


@router.get("/recordings", response_model=list[CCTVRecordingRead])
def list_recordings(stream_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(CCTVRecording).order_by(CCTVRecording.recorded_at.desc())
    if stream_id:
        query = query.filter(CCTVRecording.stream_id == stream_id)
    return query.all()
