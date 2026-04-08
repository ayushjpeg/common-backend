from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


BUDGET_CATEGORIES = ["Investments", "Rusty", "Household", "Extra"]


def _normalize_category(value: str) -> str:
    normalized = (value or "").strip().lower()
    alias_map = {
        "investment": "Investments",
        "investments": "Investments",
        "investement": "Investments",
        "investements": "Investments",
        "rusty": "Rusty",
        "household": "Household",
        "extra": "Extra",
    }
    if normalized not in alias_map:
        raise ValueError(f"Category must be one of: {', '.join(BUDGET_CATEGORIES)}")
    return alias_map[normalized]


class BudgetEntryBase(BaseModel):
    category: str
    title: str = Field(min_length=1, max_length=255)
    amount: float = Field(gt=0)
    note: str | None = None
    spent_on: date

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str) -> str:
        return _normalize_category(value)


class BudgetEntryCreate(BudgetEntryBase):
    pass


class BudgetEntryUpdate(BaseModel):
    category: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    amount: float | None = Field(default=None, gt=0)
    note: str | None = None
    spent_on: date | None = None

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_category(value)


class BudgetEntryRead(BaseModel):
    id: str
    category: str
    title: str
    amount: float
    note: str | None = None
    spent_on: date
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BudgetCategorySummary(BaseModel):
    category: str
    total_amount: float
    entry_count: int


class BudgetEntriesResponse(BaseModel):
    month: str
    total_spend: float
    category_totals: list[BudgetCategorySummary]
    entries: list[BudgetEntryRead]