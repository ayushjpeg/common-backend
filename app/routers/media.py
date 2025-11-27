from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_api_key
from ..models.media_asset import MediaAsset
from ..schemas.media import MediaAssetRead

router = APIRouter(prefix="/media", tags=["media"], dependencies=[Depends(require_api_key)])


@router.get("/", response_model=list[MediaAssetRead])
def list_media(owner_type: str | None = None, owner_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(MediaAsset)
    if owner_type:
        query = query.filter(MediaAsset.owner_type == owner_type)
    if owner_id:
        query = query.filter(MediaAsset.owner_id == owner_id)
    return query.order_by(MediaAsset.created_at.desc()).all()
