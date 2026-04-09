from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user, require_api_key
from ..models.budget import BudgetCategory, BudgetEntry
from ..models.user import User
from ..schemas.budget import (
    DEFAULT_BUDGET_CATEGORIES,
    BudgetCategoryCreate,
    BudgetCategoryRead,
    BudgetCategorySummary,
    BudgetEntriesResponse,
    BudgetEntryCreate,
    BudgetEntryRead,
    BudgetEntryUpdate,
)

router = APIRouter(prefix="/budget", tags=["budget"], dependencies=[Depends(require_api_key)])


def _resolve_month(month: str | None) -> tuple[str, date, date]:
    if month:
        try:
            year, month_value = [int(part) for part in month.split("-", 1)]
            start = date(year, month_value, 1)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Month must use YYYY-MM format") from exc
    else:
        today = datetime.utcnow().date()
        start = date(today.year, today.month, 1)

    if start.month == 12:
        next_month = date(start.year + 1, 1, 1)
    else:
        next_month = date(start.year, start.month + 1, 1)
    end = next_month.fromordinal(next_month.toordinal() - 1)
    return start.strftime("%Y-%m"), start, end


def _load_entry(db: Session, entry_id: str, user_id: str) -> BudgetEntry:
    entry = db.query(BudgetEntry).filter(BudgetEntry.id == entry_id, BudgetEntry.user_id == user_id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget entry not found")
    return entry


def _normalize_category_name(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _list_categories(db: Session, user_id: str) -> list[BudgetCategory]:
    return (
        db.query(BudgetCategory)
        .filter(BudgetCategory.user_id == user_id)
        .order_by(BudgetCategory.created_at.asc(), BudgetCategory.name.asc())
        .all()
    )


def _get_category_by_name(db: Session, user_id: str, name: str) -> BudgetCategory | None:
    normalized = _normalize_category_name(name)
    if not normalized:
        return None
    return (
        db.query(BudgetCategory)
        .filter(BudgetCategory.user_id == user_id, func.lower(BudgetCategory.name) == normalized.lower())
        .first()
    )


def _ensure_default_categories(db: Session, user_id: str) -> list[BudgetCategory]:
    categories = _list_categories(db, user_id)
    if categories:
        return categories

    created = [BudgetCategory(user_id=user_id, name=name) for name in DEFAULT_BUDGET_CATEGORIES]
    db.add_all(created)
    db.commit()
    return _list_categories(db, user_id)


def _ensure_category(db: Session, user_id: str, name: str) -> BudgetCategory:
    normalized = _normalize_category_name(name)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category is required")

    existing = _get_category_by_name(db, user_id, normalized)
    if existing:
        return existing

    category = BudgetCategory(user_id=user_id, name=normalized)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def _build_response(entries: list[BudgetEntry], categories: list[BudgetCategory], month_key: str) -> BudgetEntriesResponse:
    category_names = [category.name for category in categories]
    summary_map = {category: {"total_amount": 0.0, "entry_count": 0} for category in category_names}
    total_spend = 0.0
    for entry in entries:
        total_spend += float(entry.amount)
        if entry.category not in summary_map:
            summary_map[entry.category] = {"total_amount": 0.0, "entry_count": 0}
        summary_map[entry.category]["total_amount"] += float(entry.amount)
        summary_map[entry.category]["entry_count"] += 1

    category_totals = [
        BudgetCategorySummary(
            category=category,
            total_amount=round(summary_map[category]["total_amount"], 2),
            entry_count=summary_map[category]["entry_count"],
        )
        for category in summary_map.keys()
    ]
    return BudgetEntriesResponse(
        month=month_key,
        total_spend=round(total_spend, 2),
        categories=[BudgetCategoryRead.model_validate(category) for category in categories],
        category_totals=category_totals,
        entries=[BudgetEntryRead.model_validate(entry) for entry in entries],
    )


@router.get("/categories", response_model=list[BudgetCategoryRead])
def list_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    categories = _ensure_default_categories(db, current_user.id)
    return [BudgetCategoryRead.model_validate(category) for category in categories]


@router.post("/categories", response_model=BudgetCategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: BudgetCategoryCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    category = _ensure_category(db, current_user.id, payload.name)
    return BudgetCategoryRead.model_validate(category)


@router.get("/entries", response_model=BudgetEntriesResponse)
def list_entries(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    month_key, month_start, month_end = _resolve_month(month)
    categories = _ensure_default_categories(db, current_user.id)
    entries = (
        db.query(BudgetEntry)
        .filter(
            BudgetEntry.user_id == current_user.id,
            BudgetEntry.spent_on >= month_start,
            BudgetEntry.spent_on <= month_end,
        )
        .order_by(BudgetEntry.spent_on.desc(), BudgetEntry.created_at.desc())
        .all()
    )
    return _build_response(entries, categories, month_key)


@router.post("/entries", response_model=BudgetEntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(payload: BudgetEntryCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    category = _ensure_category(db, current_user.id, payload.category)
    entry = BudgetEntry(user_id=current_user.id, category=category.name, **payload.model_dump(exclude={"category"}))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/entries/{entry_id}", response_model=BudgetEntryRead)
def update_entry(entry_id: str, payload: BudgetEntryUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    entry = _load_entry(db, entry_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "category" and value is not None:
            value = _ensure_category(db, current_user.id, value).name
        setattr(entry, field, value)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    entry = _load_entry(db, entry_id, current_user.id)
    db.delete(entry)
    db.commit()