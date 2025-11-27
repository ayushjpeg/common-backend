from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_api_key
from ..models.food import FoodImage, MealEntry
from ..models.media_asset import MediaAsset
from ..schemas.food import MealEntryCreate, MealEntryRead
from ..schemas.media import MediaAssetRead
from ..services.media_storage import get_media_storage

router = APIRouter(prefix="/food", tags=["food"], dependencies=[Depends(require_api_key)])


@router.get("/meals", response_model=list[MealEntryRead])
def list_meals(db: Session = Depends(get_db)):
    return db.query(MealEntry).order_by(MealEntry.consumed_at.desc()).all()


@router.post("/meals", response_model=MealEntryRead, status_code=status.HTTP_201_CREATED)
def create_meal(payload: MealEntryCreate, db: Session = Depends(get_db)):
    meal = MealEntry(**payload.model_dump())
    db.add(meal)
    db.commit()
    db.refresh(meal)
    return meal


@router.post("/meals/{meal_id}/images", response_model=MediaAssetRead)
async def upload_meal_image(meal_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    meal = db.get(MealEntry, meal_id)
    if not meal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found")

    storage = get_media_storage()
    dest_path = storage.save_upload("food", file)

    media = MediaAsset(
        owner_type="meal",
        owner_id=meal_id,
        file_path=str(dest_path),
        mime_type=file.content_type,
        metadata_json={"filename": file.filename},
    )
    db.add(media)
    db.flush()

    food_image = FoodImage(meal_id=meal_id, file_path=str(dest_path), media_id=media.id)
    db.add(food_image)
    db.commit()
    db.refresh(media)
    return media
