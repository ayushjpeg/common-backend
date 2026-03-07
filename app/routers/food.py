from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, selectinload

from ..core.database import get_db
from ..core.security import require_api_key
from ..models.food import FoodImage, MealEntry
from ..models.media_asset import MediaAsset
from ..schemas.food import FoodImageRead, MealEntryCreate, MealEntryRead, MealEntryUpdate, PhotoCreate
from ..services.media_storage import build_public_url, get_media_storage

router = APIRouter(prefix="/food", tags=["food"], dependencies=[Depends(require_api_key)])


def _serialize_photo(image: FoodImage) -> dict:
    return {
        "id": image.id,
        "meal_id": image.meal_id,
        "url": build_public_url(image.file_path),
        "file_path": image.file_path,
        "media_id": image.media_id,
        "uploaded_at": image.uploaded_at,
        "recorded_at": image.recorded_at,
        "caption": image.caption,
    }


def _serialize_meal(meal: MealEntry) -> MealEntryRead:
    def _photo_sort_key(img: dict):
        if img["recorded_at"]:
            return datetime.combine(img["recorded_at"], datetime.min.time())
        return img["uploaded_at"]

    photos = sorted([_serialize_photo(img) for img in meal.images or []], key=_photo_sort_key)
    cover = photos[-1]["url"] if photos else meal.image_url
    last_made = meal.last_made or (meal.consumed_at.date() if meal.consumed_at else None)
    payload = {
        "id": meal.id,
        "name": meal.title,
        "meal": meal.meal_slot,
        "recipe": meal.recipe,
        "notes": meal.notes,
        "last_made": last_made,
        "ingredients": meal.ingredients or [],
        "image_url": cover,
        "photos": photos,
        "created_at": meal.consumed_at or datetime.utcnow(),
    }
    return MealEntryRead.model_validate(payload)


def _load_meal(db: Session, meal_id: str) -> MealEntry:
    meal = (
        db.query(MealEntry)
        .options(selectinload(MealEntry.images))
        .filter(MealEntry.id == meal_id)
        .first()
    )
    if not meal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found")
    return meal


def _persist_photo(meal: MealEntry, payload: PhotoCreate, db: Session, mime_type_hint: str | None = None) -> FoodImage:
    if not payload.image_data_url and not payload.image_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide image_data_url or image_url")

    storage = get_media_storage()
    file_path: Path | str
    mime_type: str | None = None

    if payload.image_data_url:
        dest_path, mime_type = storage.save_data_url("food", payload.image_data_url)
        file_path = dest_path
    else:
        file_path = payload.image_url or ""

    file_path_str = str(file_path)
    is_local_path = not file_path_str.startswith(("http://", "https://", "data:"))

    media_id: str | None = None
    if is_local_path:
        media = MediaAsset(
            owner_type="meal",
            owner_id=meal.id,
            file_path=file_path_str,
            mime_type=mime_type or mime_type_hint,
            metadata_json={"caption": payload.caption} if payload.caption else {},
        )
        db.add(media)
        db.flush()
        media_id = media.id

    image = FoodImage(
        meal_id=meal.id,
        file_path=file_path_str,
        media_id=media_id,
        recorded_at=payload.recorded_at,
        caption=payload.caption,
    )

    meal.image_url = build_public_url(file_path_str)
    if payload.recorded_at:
        meal.last_made = payload.recorded_at

    db.add(image)
    db.commit()
    db.refresh(meal)
    db.refresh(image)
    return image


@router.get("/meals", response_model=list[MealEntryRead])
def list_meals(db: Session = Depends(get_db)):
    meals = (
        db.query(MealEntry)
        .options(selectinload(MealEntry.images))
        .order_by(MealEntry.last_made.desc().nullslast(), MealEntry.consumed_at.desc())
        .all()
    )
    return [_serialize_meal(meal) for meal in meals]


@router.post("/meals", response_model=MealEntryRead, status_code=status.HTTP_201_CREATED)
def create_meal(payload: MealEntryCreate, db: Session = Depends(get_db)):
    meal = MealEntry(
        title=payload.name,
        meal_slot=payload.meal,
        recipe=payload.recipe,
        notes=payload.notes,
        ingredients=payload.ingredients or [],
        last_made=payload.last_made,
        image_url=payload.image_url,
        consumed_at=datetime.utcnow(),
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)

    if payload.image_data_url or payload.image_url:
        photo_payload = PhotoCreate(
            image_data_url=payload.image_data_url,
            image_url=payload.image_url,
            recorded_at=payload.last_made,
            caption=None,
        )
        _persist_photo(meal, photo_payload, db)
        meal = _load_meal(db, meal.id)

    return _serialize_meal(meal)


@router.patch("/meals/{meal_id}", response_model=MealEntryRead)
def update_meal(meal_id: str, payload: MealEntryUpdate, db: Session = Depends(get_db)):
    meal = _load_meal(db, meal_id)

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        meal.title = updates["name"]
    if "meal" in updates:
        meal.meal_slot = updates["meal"]
    if "recipe" in updates:
        meal.recipe = updates["recipe"]
    if "notes" in updates:
        meal.notes = updates["notes"]
    if "ingredients" in updates and updates["ingredients"] is not None:
        meal.ingredients = updates["ingredients"]
    if "last_made" in updates:
        meal.last_made = updates["last_made"]
    if "image_url" in updates and updates["image_url"]:
        meal.image_url = updates["image_url"]

    db.commit()
    db.refresh(meal)

    if payload.image_data_url or payload.image_url:
        photo_payload = PhotoCreate(
            image_data_url=payload.image_data_url,
            image_url=payload.image_url,
            recorded_at=payload.last_made,
            caption=None,
        )
        _persist_photo(meal, photo_payload, db)
        meal = _load_meal(db, meal.id)

    return _serialize_meal(meal)


@router.delete("/meals/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(meal_id: str, db: Session = Depends(get_db)):
    meal = db.get(MealEntry, meal_id)
    if not meal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found")
    db.delete(meal)
    db.commit()


@router.post("/meals/{meal_id}/photos", response_model=MealEntryRead, status_code=status.HTTP_201_CREATED)
def add_photo(meal_id: str, payload: PhotoCreate = Body(...), db: Session = Depends(get_db)):
    meal = _load_meal(db, meal_id)
    _persist_photo(meal, payload, db)
    meal = _load_meal(db, meal.id)
    return _serialize_meal(meal)


@router.post("/meals/{meal_id}/images", response_model=MealEntryRead, status_code=status.HTTP_201_CREATED)
async def upload_meal_image(meal_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    meal = _load_meal(db, meal_id)

    storage = get_media_storage()
    dest_path = storage.save_upload("food", file)

    photo = PhotoCreate(
        image_url=str(dest_path),
        recorded_at=datetime.utcnow().date(),
        caption=file.filename,
    )
    _persist_photo(meal, photo, db, mime_type_hint=file.content_type)

    meal = _load_meal(db, meal.id)
    return _serialize_meal(meal)
